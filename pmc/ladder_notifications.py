import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from . import discord_webhooks

logger = logging.getLogger(__name__)

CHALLENGE_ISSUED_COLOR = 0xFFB400
RESULT_RECORDED_COLOR = 0x2BC98A
TEST_MESSAGE_COLOR = 0x8FD3FA


def run_safely(notification, *args):
    try:
        notification(*args)
    except Exception:
        logger.exception('Ladder notification %s failed', notification.__name__)


def notify_after_commit(notification, *args):
    transaction.on_commit(lambda: run_safely(notification, *args))


def keychain_url(view_name, **kwargs):
    base_url = getattr(settings, 'PMC_SITE_URL', '').rstrip('/')
    if not base_url:
        return None
    return base_url + reverse(view_name, urlconf='pmc.urls', kwargs=kwargs)


def ladder_url(ladder):
    return keychain_url('pmc-pg-ladder-detail', slug=ladder.playgroup.slug, ladder_id=ladder.pk)


def discord_id_for(member):
    profile = getattr(member.user, 'profile', None)
    return getattr(profile, 'discord_id', None)


def notify_challenge_issued(challenge_id, challenger_rank, defender_rank):
    challenge = load_challenge(challenge_id)
    email_challenged_player(challenge, challenger_rank, defender_rank)
    discord_webhooks.post_message_in_background(
        challenge.ladder.discord_webhook_url,
        challenge_issued_message(challenge, challenger_rank, defender_rank),
    )


def notify_result_recorded(challenge_id, challenger_new_rank):
    challenge = load_challenge(challenge_id)
    discord_webhooks.post_message_in_background(
        challenge.ladder.discord_webhook_url,
        result_recorded_message(challenge, challenger_new_rank),
    )


def send_test_message(ladder):
    embed = ladder_embed(
        ladder,
        title=_('KeyChain is connected to %(ladder)s') % {'ladder': ladder.name},
        description=_('Challenges and results for this ladder will be posted here.'),
        color=TEST_MESSAGE_COLOR,
    )
    return discord_webhooks.post_message(
        ladder.discord_webhook_url, discord_webhooks.build_message(embed))


def load_challenge(challenge_id):
    from .models import LadderChallenge
    return LadderChallenge.objects.select_related(
        'ladder__playgroup',
        'match__player_one__user__profile',
        'match__player_two__user__profile',
        'match__result__winner',
    ).get(pk=challenge_id)


def email_challenged_player(challenge, challenger_rank, defender_rank):
    from .models import LadderEntry
    defender = challenge.defender
    wants_email = LadderEntry.objects.filter(
        ladder=challenge.ladder, member=defender, email_on_challenge=True).exists()
    if not wants_email or not defender.user.email:
        return
    try:
        send_mail(
            subject=_('%(challenger)s challenged you on %(ladder)s') % {
                'challenger': challenge.challenger, 'ladder': challenge.ladder.name},
            message=_('%(challenger)s (#%(challenger_rank)s) challenged you (#%(defender_rank)s) on %(ladder)s. Record the result by %(respond_by)s.') % {
                'challenger': challenge.challenger,
                'challenger_rank': challenger_rank,
                'defender_rank': defender_rank,
                'ladder': challenge.ladder.name,
                'respond_by': timezone.localtime(challenge.respond_by).strftime('%b %d'),
            },
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[defender.user.email],
            fail_silently=True,
            html_message=loader.render_to_string('pmc/email-ladder-challenge.html', {
                'challenge': challenge,
                'challenger_rank': challenger_rank,
                'defender_rank': defender_rank,
                'ladder_url': ladder_url(challenge.ladder),
            }),
        )
    except Exception:
        logger.exception('Could not send the ladder challenge email for challenge %s', challenge.pk)


def ladder_embed(ladder, title, description, color, fields=()):
    embed = {
        'title': discord_webhooks.truncate(title, discord_webhooks.EMBED_TITLE_LIMIT),
        'description': discord_webhooks.truncate(description, discord_webhooks.EMBED_DESCRIPTION_LIMIT),
        'color': color,
        'fields': [
            {
                'name': name,
                'value': discord_webhooks.truncate(value, discord_webhooks.EMBED_FIELD_VALUE_LIMIT),
                'inline': True,
            }
            for name, value in fields
        ],
        'footer': {'text': discord_webhooks.truncate(ladder.playgroup.name, discord_webhooks.EMBED_FOOTER_LIMIT)},
        'timestamp': timezone.now().isoformat(),
    }
    url = ladder_url(ladder)
    if url:
        embed['url'] = url
    return embed


def with_ladder_link(description, ladder):
    url = ladder_url(ladder)
    if not url:
        return description
    return '%s\n\n[%s](%s)' % (description, _('View the ladder'), url)


def challenge_issued_message(challenge, challenger_rank, defender_rank):
    escape = discord_webhooks.escape_markdown
    embed = ladder_embed(
        challenge.ladder,
        title=_('⚔️ New challenge on %(ladder)s') % {'ladder': challenge.ladder.name},
        description=with_ladder_link(_('**%(challenger)s** (#%(challenger_rank)s) challenged **%(defender)s** (#%(defender_rank)s)') % {
            'challenger': escape(challenge.challenger),
            'challenger_rank': challenger_rank,
            'defender': escape(challenge.defender),
            'defender_rank': defender_rank,
        }, challenge.ladder),
        color=CHALLENGE_ISSUED_COLOR,
        fields=[(_('Result due'), discord_webhooks.discord_timestamp(challenge.respond_by))],
    )
    return discord_webhooks.build_message(embed, [discord_id_for(challenge.defender)])


def result_description(challenge):
    escape = discord_webhooks.escape_markdown
    result = challenge.match.result
    if result.is_tie():
        return _('**%(first)s** and **%(second)s** tied') % {
            'first': escape(challenge.challenger), 'second': escape(challenge.defender)}
    names = {'winner': escape(result.winner), 'loser': escape(result.get_loser())}
    if result.is_forfeit:
        return _('**%(winner)s** won by forfeit over **%(loser)s**') % names
    return _('**%(winner)s** beat **%(loser)s**') % names


def result_recorded_message(challenge, challenger_new_rank):
    fields = []
    if challenger_new_rank is not None:
        fields.append((_('Ladder'), _('%(name)s moves up to #%(rank)s') % {
            'name': discord_webhooks.escape_markdown(challenge.challenger), 'rank': challenger_new_rank}))
    if not challenge.was_issued:
        fields.append((_('Challenge'), _('Played without a challenge')))
    embed = ladder_embed(
        challenge.ladder,
        title=_('🏁 Result on %(ladder)s') % {'ladder': challenge.ladder.name},
        description=with_ladder_link(result_description(challenge), challenge.ladder),
        color=RESULT_RECORDED_COLOR,
        fields=fields,
    )
    return discord_webhooks.build_message(embed)
