from django.core.exceptions import PermissionDenied
from pmc import ladder_notifications
from pmc.discord_webhooks import discord_timestamp, escape_markdown
from pmc.models import Feature, Ladder, LadderChallenge, LadderRuleViolation, PlaygroupMember
from ..accounts import account_not_linked_message, get_site_user_for_discord_id
from ..registry import Command, COMMAND_TYPE_CHAT_INPUT, OPTION_TYPE_SUB_COMMAND, OPTION_TYPE_STRING, choice
from ..responses import RESPONSE_TYPE_CHANNEL_MESSAGE, ephemeral_message, autocomplete_choices
from ..text import truncate

COMMAND_NAME = 'ladder'
SUBCOMMAND_CHALLENGE = 'challenge'
SUBCOMMAND_RESULT = 'result'
OPTION_LADDER = 'ladder'
OPTION_OPPONENT = 'opponent'
OPTION_CHALLENGE = 'challenge'
OPTION_OUTCOME = 'outcome'

OUTCOME_WON = 'won'
OUTCOME_LOST = 'lost'
OUTCOME_TIE = 'tie'

MAX_CHOICES = 25
MAX_CHOICE_NAME_LENGTH = 100
PUBLIC_MESSAGE_FIELDS = ('content', 'embeds', 'allowed_mentions')

LADDER_NOT_FOUND_MESSAGE = 'I couldn\'t find that ladder. Pick one of your ladders from the list.'
OPPONENT_NOT_FOUND_MESSAGE = 'I couldn\'t find that player. Pick an opponent from the list.'
CHALLENGE_NOT_FOUND_MESSAGE = 'I couldn\'t find that open challenge. Pick one of yours from the list.'
OUTCOME_NOT_FOUND_MESSAGE = 'Pick how the game went from the list.'
NOT_ALLOWED_MESSAGE ='You aren\'t allowed to record that result.'
CHALLENGE_ISSUED_MESSAGE = 'Challenge issued to {defender} on {ladder}. The result is due {respond_by}.'
RESULT_RECORDED_MESSAGE = 'Result recorded on {ladder}.'

HELP_TEXT = (
    'Your Discord account must be linked to your Sloppy Labwork account. '
    'Pick a ladder first, then the player or challenge. '
    'Results can only be recorded here for open challenges; record other games on KeyChain. '
    'If the ladder posts to a Discord channel, I\'ll confirm privately; otherwise I\'ll post in this channel.'
)

ladder_option = {
    'name': OPTION_LADDER,
    'description': 'Ladder',
    'type': OPTION_TYPE_STRING,
    'required': True,
    'autocomplete': True,
}

definition = {
    'name': COMMAND_NAME,
    'type': COMMAND_TYPE_CHAT_INPUT,
    'description': 'Take part in KeyChain ladders',
    'options': [
        {
            'name': SUBCOMMAND_CHALLENGE,
            'description': 'Challenge a player above you',
            'type': OPTION_TYPE_SUB_COMMAND,
            'options': [
                ladder_option,
                {
                    'name': OPTION_OPPONENT,
                    'description': 'Player to challenge',
                    'type': OPTION_TYPE_STRING,
                    'required': True,
                    'autocomplete': True,
                },
            ],
        },
        {
            'name': SUBCOMMAND_RESULT,
            'description': 'Record the result of an open challenge',
            'type': OPTION_TYPE_SUB_COMMAND,
            'options': [
                ladder_option,
                {
                    'name': OPTION_CHALLENGE,
                    'description': 'Open challenge',
                    'type': OPTION_TYPE_STRING,
                    'required': True,
                    'autocomplete': True,
                },
                {
                    'name': OPTION_OUTCOME,
                    'description': 'How did it go?',
                    'type': OPTION_TYPE_STRING,
                    'required': True,
                    'autocomplete': True,
                },
            ],
        },
    ],
}


def find_ladders_with_challenges_enabled(user):
    ladders = Ladder.objects.filter(
        entries__member__user=user, challenges_enabled=True
    ).select_related('playgroup').distinct().order_by('name', 'pk')
    return [ladder for ladder in ladders if ladder.playgroup.has_feature(Feature.Keys.LADDERS)]


def find_ladder(user, ladder_value):
    if not str(ladder_value or '').isdigit():
        return None
    return next(
        (ladder for ladder in find_ladders_with_challenges_enabled(user) if ladder.pk == int(ladder_value)),
        None,
    )


def get_ladder_member(ladder, user):
    return PlaygroupMember.objects.get(playgroup=ladder.playgroup, user=user)


def find_open_challenges_involving(ladder, member):
    return [
        challenge for challenge in ladder.get_open_challenges()
        if challenge.match.involves(member) and not challenge.is_overdue()
    ]


def get_opponent(challenge, member):
    if challenge.match.player_one_id == member.pk:
        return challenge.match.player_two
    return challenge.match.player_one


def describe_ladder(ladder):
    return truncate(f'{ladder.name} · {ladder.playgroup.name}', MAX_CHOICE_NAME_LENGTH)


def describe_open_challenge(challenge, member):
    due_on = challenge.respond_by.strftime('%b %d')
    return truncate(f'vs {get_opponent(challenge, member)} · due {due_on}', MAX_CHOICE_NAME_LENGTH)


def matches_query(text, query):
    return query.lower() in text.lower()


def focused_query(interaction):
    return str((interaction.focused_option or {}).get('value', ''))


def public_post(webhook_message):
    return {
        'type': RESPONSE_TYPE_CHANNEL_MESSAGE,
        'data': {field: webhook_message[field] for field in PUBLIC_MESSAGE_FIELDS if field in webhook_message},
    }


def announce(ladder, private_confirmation, build_webhook_message):
    if ladder.discord_webhook_url:
        return ephemeral_message(private_confirmation)
    return public_post(build_webhook_message())


def issue_challenge(user, ladder, opponent_value):
    member = get_ladder_member(ladder, user)
    defender = PlaygroupMember.objects.filter(
        pk=opponent_value, playgroup=ladder.playgroup).first() if str(opponent_value).isdigit() else None
    if defender is None:
        return ephemeral_message(OPPONENT_NOT_FOUND_MESSAGE)
    try:
        challenge = ladder.issue_challenge(member, defender)
    except LadderRuleViolation as violation:
        return ephemeral_message(str(violation))
    private_confirmation = CHALLENGE_ISSUED_MESSAGE.format(
        defender=escape_markdown(defender),
        ladder=escape_markdown(ladder.name),
        respond_by=discord_timestamp(challenge.respond_by),
    )
    return announce(ladder, private_confirmation, lambda: ladder_notifications.challenge_issued_message(
        ladder_notifications.load_challenge(challenge.pk),
        ladder.get_rank_of(member),
        ladder.get_rank_of(defender),
    ))


def outcome_labels_for(ladder):
    labels = {OUTCOME_WON: 'I won', OUTCOME_LOST: 'My opponent won'}
    if ladder.allow_ties:
        labels[OUTCOME_TIE] = 'Tie'
    return labels


def winner_for(outcome, member, opponent):
    return {
        OUTCOME_WON: member,
        OUTCOME_LOST: opponent,
        OUTCOME_TIE: None,
    }[outcome]


def record_result(user, ladder, challenge_value, outcome):
    member = get_ladder_member(ladder, user)
    challenge = next(
        (challenge for challenge in find_open_challenges_involving(ladder, member)
         if str(challenge.pk) == str(challenge_value)),
        None,
    )
    if challenge is None:
        return ephemeral_message(CHALLENGE_NOT_FOUND_MESSAGE)
    if outcome not in outcome_labels_for(ladder):
        return ephemeral_message(OUTCOME_NOT_FOUND_MESSAGE)
    winner = winner_for(outcome, member, get_opponent(challenge, member))
    try:
        challenger_new_rank = ladder.record_result(challenge, winner, user)
    except PermissionDenied:
        return ephemeral_message(NOT_ALLOWED_MESSAGE)
    except LadderRuleViolation as violation:
        return ephemeral_message(str(violation))
    private_confirmation = RESULT_RECORDED_MESSAGE.format(ladder=escape_markdown(ladder.name))
    return announce(ladder, private_confirmation, lambda: ladder_notifications.result_recorded_message(
        ladder_notifications.load_challenge(challenge.pk), challenger_new_rank))


def handle(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    if not user.is_authenticated:
        return ephemeral_message(account_not_linked_message())
    ladder = find_ladder(user, interaction.option(OPTION_LADDER))
    if ladder is None:
        return ephemeral_message(LADDER_NOT_FOUND_MESSAGE)
    if interaction.subcommand_name == SUBCOMMAND_RESULT:
        return record_result(
            user, ladder, interaction.option(OPTION_CHALLENGE), interaction.option(OPTION_OUTCOME))
    return issue_challenge(user, ladder, interaction.option(OPTION_OPPONENT))


def ladder_choices(user, query, subcommand_name):
    ladders = find_ladders_with_challenges_enabled(user)
    if subcommand_name == SUBCOMMAND_RESULT:
        ladders = [
            ladder for ladder in ladders
            if find_open_challenges_involving(ladder, get_ladder_member(ladder, user))
        ]
    return [
        choice(describe_ladder(ladder), str(ladder.pk))
        for ladder in ladders if matches_query(describe_ladder(ladder), query)
    ]


def opponent_choices(user, ladder, query):
    standings = ladder.get_standings_for(get_ladder_member(ladder, user))
    return [
        choice(truncate(f'#{standing.rank} {standing.entry.member}', MAX_CHOICE_NAME_LENGTH),
               str(standing.entry.member_id))
        for standing in standings
        if standing.can_be_challenged and matches_query(str(standing.entry.member), query)
    ]


def open_challenge_choices(user, ladder, query):
    member = get_ladder_member(ladder, user)
    return [
        choice(describe_open_challenge(challenge, member), str(challenge.pk))
        for challenge in find_open_challenges_involving(ladder, member)
        if matches_query(str(get_opponent(challenge, member)), query)
    ]


def autocomplete(interaction):
    user = get_site_user_for_discord_id(interaction.user_id)
    if not user.is_authenticated:
        return autocomplete_choices([])
    focused_name = (interaction.focused_option or {}).get('name')
    query = focused_query(interaction)
    if focused_name == OPTION_LADDER:
        return autocomplete_choices(ladder_choices(user, query, interaction.subcommand_name)[:MAX_CHOICES])
    ladder = find_ladder(user, interaction.option(OPTION_LADDER))
    if ladder is None:
        return autocomplete_choices([])
    if focused_name == OPTION_CHALLENGE:
        return autocomplete_choices(open_challenge_choices(user, ladder, query)[:MAX_CHOICES])
    if focused_name == OPTION_OUTCOME:
        return autocomplete_choices([
            choice(outcome_label, outcome)
            for outcome, outcome_label in outcome_labels_for(ladder).items()
            if matches_query(outcome_label, query)
        ])
    return autocomplete_choices(opponent_choices(user, ladder, query)[:MAX_CHOICES])


command = Command(
    definition,
    handle,
    autocomplete=autocomplete,
    help_text=HELP_TEXT,
)
