import secrets

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils.text import get_text_list
from django.utils.translation import gettext as _

from pmc.models import EventResult, Playgroup, PlaygroupMember, PmcProfile
from tourney.models import Player
from user_profile.management.commands.merge_users import (
    find_user_relations, get_relation_queryset,
)
from user_profile.models import UserProfile

REMOVED_USERNAME_PREFIX = 'MysteryArchon-'

DELETED_RELATIONS = {
    ('auth.User_groups', 'user'),
    ('auth.User_user_permissions', 'user'),
    ('account.EmailAddress', 'user'),
    ('socialaccount.SocialAccount', 'user'),
    ('pmc.PinnedAward', 'user'),
    ('pmc.PlaygroupJoinRequest', 'user'),
    ('transporter_platform.PodPlayer', 'user'),
    ('tourney.TournamentAdmin', 'user'),
}

REPLACED_RELATIONS = {
    ('user_profile.UserProfile', 'user'),
    ('pmc.PmcProfile', 'user'),
}

SCRUBBED_RELATIONS = {
    ('pmc.PlaygroupMember', 'user'),
    ('pmc.EventResult', 'user'),
    ('tourney.Player', 'user'),
}

KEPT_RELATIONS = {
    ('admin.LogEntry', 'user'),
    ('ghostform.Form', 'owner'),
    ('ghostform.Response', 'user'),
    ('lineups.Lineup', 'owner'),
    ('pmc.AwardCredit', 'user'),
    ('pmc.BoxLeague', 'created_by'),
    ('pmc.Ladder', 'created_by'),
    ('pmc.MatchResult', 'recorded_by'),
    ('pmc.MatchResult', 'voided_by'),
    ('pmc.PlayerRank', 'user'),
    ('pmc.PlaygroupVenue', 'added_by'),
    ('pmc.UserAchievementTier', 'user'),
    ('pmc.UserBadge', 'user'),
    ('pmc.UserTrophy', 'user'),
    ('pmc.Venue', 'created_by'),
    ('posts.Post', 'author'),
    ('timekeeper.CountdownTimer', 'owner'),
    ('tourney.Tournament', 'owner'),
    ('tourney.TournamentActionLog', 'user'),
    ('trade_secrets.PlayResult', 'updated_by'),
    ('trade_secrets.Session', 'guest'),
    ('trade_secrets.Session', 'host'),
    ('trade_secrets.SessionTemplate', 'owner'),
    ('trade_secrets.StepSubmission', 'submitted_by'),
}

HANDLED_RELATIONS = (
    DELETED_RELATIONS | REPLACED_RELATIONS | SCRUBBED_RELATIONS | KEPT_RELATIONS)


class AccountRemovalBlocked(Exception):
    def __init__(self, reasons):
        super().__init__(' '.join(reasons))
        self.reasons = reasons


def find_unhandled_user_relations(handled_relations=HANDLED_RELATIONS):
    return sorted(find_user_relations() - handled_relations)


def find_playgroups_only_administered_by(user):
    other_playgroup_admins = PlaygroupMember.objects.filter(
        playgroup=OuterRef('pk'), is_staff=True).exclude(user=user)
    return Playgroup.objects.filter(
        members__user=user, members__is_staff=True,
    ).exclude(Exists(other_playgroup_admins)).order_by('name')


def find_account_removal_blockers(user):
    blockers = []
    if user.is_staff or user.is_superuser:
        blockers.append(_(
            "Accounts with access to the admin site can't be deleted here. "
            'Remove staff and superuser access in the admin first, '
            'or ask another admin to do it.'))
    sole_admin_playgroup_names = list(
        find_playgroups_only_administered_by(user).values_list('name', flat=True))
    if sole_admin_playgroup_names:
        blockers.append(_(
            "You're the only admin of %(playgroups)s. "
            'Make another member an admin of each first.'
        ) % {'playgroups': get_text_list(sole_admin_playgroup_names, _('and'))})
    return blockers


def generate_removed_username():
    while True:
        username = f'{REMOVED_USERNAME_PREFIX}{secrets.token_hex(3)}'
        if not User.objects.filter(username__iexact=username).exists():
            return username


def anonymize_user_identity(user):
    user.username = generate_removed_username()
    user.email = ''
    user.first_name = ''
    user.last_name = ''
    user.is_active = False
    user.set_unusable_password()
    user.save()


def delete_personal_records(user):
    for relation in DELETED_RELATIONS:
        get_relation_queryset(relation, user).delete()


def replace_profiles_with_blank_ones(user):
    UserProfile.objects.filter(user=user).delete()
    UserProfile.objects.create(user=user)
    PmcProfile.objects.filter(user=user).delete()
    PmcProfile.objects.create(user=user)


def scrub_identifying_details(user):
    PlaygroupMember.objects.filter(user=user).update(nickname=None, is_staff=False)
    EventResult.objects.filter(user=user).update(uploaded_deck_link=None)
    Player.objects.filter(user=user).update(nickname=None)
    LogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(User),
        object_id=str(user.pk),
    ).update(object_repr=user.username)


def remove_user_account(user):
    blockers = find_account_removal_blockers(user)
    if blockers:
        raise AccountRemovalBlocked(blockers)
    with transaction.atomic():
        anonymize_user_identity(user)
        delete_personal_records(user)
        replace_profiles_with_blank_ones(user)
        scrub_identifying_details(user)
