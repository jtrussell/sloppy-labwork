from django.apps import apps
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from pmc.models import AwardBase

REPOINTED_RELATIONS = {
    ('admin.LogEntry', 'user'),
    ('socialaccount.SocialAccount', 'user'),
    ('register.DeckRegistration', 'user'),
    ('register.DeckRegistration', 'verified_by'),
    ('posts.Post', 'author'),
    ('tournaments.Tournament', 'owner'),
    ('tournaments.TournamentRegistration', 'player'),
    ('pmc.PlaygroupJoinRequest', 'user'),
    ('pmc.Venue', 'created_by'),
    ('pmc.PlaygroupVenue', 'added_by'),
    ('pmc.AwardCredit', 'user'),
    ('pmc.EventResult', 'user'),
    ('tourney.Tournament', 'owner'),
    ('tourney.Player', 'user'),
    ('tourney.TournamentActionLog', 'user'),
    ('timekeeper.CountdownTimer', 'owner'),
    ('lineups.Lineup', 'owner'),
    ('ghostform.Form', 'owner'),
    ('ghostform.Response', 'user'),
}

MERGED_RELATIONS = {
    ('pmc.PlaygroupMember', 'user'),
    ('pmc.PlayerRank', 'user'),
    ('pmc.UserBadge', 'user'),
    ('pmc.UserTrophy', 'user'),
    ('tourney.TournamentAdmin', 'user'),
    ('transporter_platform.PodPlayer', 'user'),
}

DISCARDED_RELATIONS = {
    ('auth.User_groups', 'user'),
    ('auth.User_user_permissions', 'user'),
    ('account.EmailAddress', 'user'),
    ('user_profile.UserProfile', 'user'),
    ('pmc.PmcProfile', 'user'),
    ('pmc.UserAchievementTier', 'user'),
    ('pmc.PinnedAward', 'user'),
}

CONFLICTING_RELATIONS = {
    ('pmc.EventResult', 'user'): 'event',
    ('tourney.Player', 'user'): 'tournament',
}

HANDLED_RELATIONS = REPOINTED_RELATIONS | MERGED_RELATIONS | DISCARDED_RELATIONS


def find_user_relations():
    return {
        (field.related_model._meta.label, field.field.name)
        for field in User._meta.get_fields(include_hidden=True)
        if field.auto_created and not field.concrete
    }


def find_unhandled_user_relations(handled_relations=HANDLED_RELATIONS):
    return sorted(find_user_relations() - handled_relations)


def get_relation_queryset(relation, user):
    model_label, field_name = relation
    return apps.get_model(model_label).objects.filter(**{field_name: user})


def find_conflicts(primary, secondary):
    conflicts = []
    for relation, shared_field_name in CONFLICTING_RELATIONS.items():
        primary_shared_ids = get_relation_queryset(relation, primary).values(
            f'{shared_field_name}_id')
        conflicting_rows = get_relation_queryset(relation, secondary).filter(
            **{f'{shared_field_name}_id__in': primary_shared_ids})
        for row in conflicting_rows.select_related(shared_field_name):
            conflicts.append(
                f'{relation[0]}: both users are in {shared_field_name} '
                f'{getattr(row, f"{shared_field_name}_id")} ({getattr(row, shared_field_name)})')
    return conflicts


def merge_playgroup_memberships(primary, secondary):
    PlaygroupMember = apps.get_model('pmc.PlaygroupMember')
    primary_memberships = {
        membership.playgroup_id: membership
        for membership in PlaygroupMember.objects.filter(user=primary)
    }
    for membership in PlaygroupMember.objects.filter(user=secondary):
        primary_membership = primary_memberships.get(membership.playgroup_id)
        if primary_membership is None:
            membership.user = primary
            membership.save(update_fields=['user'])
            continue
        if membership.is_staff and not primary_membership.is_staff:
            primary_membership.is_staff = True
            primary_membership.save(update_fields=['is_staff'])
        membership.delete()


def merge_player_ranks(primary, secondary):
    PlayerRank = apps.get_model('pmc.PlayerRank')

    def ranking_key(player_rank):
        return (player_rank.leaderboard_id, player_rank.playgroup_id, player_rank.period_id)

    primary_ranks = {
        ranking_key(player_rank): player_rank
        for player_rank in PlayerRank.objects.filter(user=primary)
    }
    for player_rank in PlayerRank.objects.filter(user=secondary):
        primary_rank = primary_ranks.get(ranking_key(player_rank))
        if primary_rank is not None and primary_rank.rank <= player_rank.rank:
            player_rank.delete()
            continue
        if primary_rank is not None:
            primary_rank.delete()
        player_rank.user = primary
        player_rank.save(update_fields=['user'])


def merge_user_badges(primary, secondary):
    UserBadge = apps.get_model('pmc.UserBadge')
    primary_badges = {
        user_badge.badge_id: user_badge
        for user_badge in UserBadge.objects.filter(user=primary)
    }
    for user_badge in UserBadge.objects.filter(user=secondary):
        primary_badge = primary_badges.get(user_badge.badge_id)
        if primary_badge is None:
            UserBadge.objects.filter(pk=user_badge.pk).update(user=primary)
            continue
        if user_badge.date_awarded < primary_badge.date_awarded:
            UserBadge.objects.filter(pk=primary_badge.pk).update(
                date_awarded=user_badge.date_awarded)
        user_badge.delete()


def merge_manual_user_trophies(primary, secondary):
    UserTrophy = apps.get_model('pmc.UserTrophy')
    UserTrophy.objects.filter(user=secondary).exclude(
        trophy__criteria=AwardBase.CriteriaTypeOptions.manually_awarded).delete()
    primary_trophies = {
        user_trophy.trophy_id: user_trophy
        for user_trophy in UserTrophy.objects.filter(user=primary)
    }
    for user_trophy in UserTrophy.objects.filter(user=secondary):
        primary_trophy = primary_trophies.get(user_trophy.trophy_id)
        if primary_trophy is None:
            UserTrophy.objects.filter(pk=user_trophy.pk).update(user=primary)
            continue
        UserTrophy.objects.filter(pk=primary_trophy.pk).update(
            amount=max(primary_trophy.amount, user_trophy.amount),
            date_awarded=min(primary_trophy.date_awarded, user_trophy.date_awarded),
        )
        user_trophy.delete()


def merge_tournament_admin_roles(primary, secondary):
    TournamentAdmin = apps.get_model('tourney.TournamentAdmin')
    primary_admin_tournament_ids = TournamentAdmin.objects.filter(
        user=primary).values('tournament_id')
    TournamentAdmin.objects.filter(user=secondary).filter(
        Q(tournament__owner=primary) | Q(tournament_id__in=primary_admin_tournament_ids)
    ).delete()
    TournamentAdmin.objects.filter(user=secondary).update(user=primary)


def merge_pod_player(primary, secondary):
    PodPlayer = apps.get_model('transporter_platform.PodPlayer')
    if not PodPlayer.objects.filter(user=primary).exists():
        PodPlayer.objects.filter(user=secondary).update(user=primary)


MERGE_STEPS = [
    merge_playgroup_memberships,
    merge_player_ranks,
    merge_user_badges,
    merge_manual_user_trophies,
    merge_tournament_admin_roles,
    merge_pod_player,
]


def merge_users(primary, secondary):
    for merge_step in MERGE_STEPS:
        merge_step(primary, secondary)
    for relation in sorted(REPOINTED_RELATIONS):
        _, field_name = relation
        get_relation_queryset(relation, secondary).update(**{field_name: primary})
    secondary.delete()


class Command(BaseCommand):
    help = 'Merge a secondary user account into a primary account, then delete the secondary'

    def add_arguments(self, parser):
        parser.add_argument('--primary', type=int, required=True,
                            help='ID of the user to keep')
        parser.add_argument('--secondary', type=int, required=True,
                            help='ID of the user to merge in and delete')
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write changes to the database (default is a dry run)',
        )

    def handle(self, *args, **options):
        if options['primary'] == options['secondary']:
            raise CommandError('Primary and secondary must be different users.')

        unhandled_relations = find_unhandled_user_relations()
        if unhandled_relations:
            raise CommandError(
                'No merge rule for these User relations: '
                + ', '.join(f'{label}.{field}' for label, field in unhandled_relations))

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                'DRY RUN MODE - No changes will be made'))
            primary, secondary = self.load_users(options)
            self.report(primary, secondary)
            self.report_conflicts(find_conflicts(primary, secondary))
            return

        with transaction.atomic():
            primary, secondary = self.load_users(options, for_update=True)
            self.report(primary, secondary)
            conflicts = find_conflicts(primary, secondary)
            if conflicts:
                self.report_conflicts(conflicts)
                raise CommandError('Resolve the conflicts above before merging.')
            merge_users(primary, secondary)

        self.stdout.write(self.style.SUCCESS(
            f'Merged user {options["secondary"]} into {primary.pk} ({primary.username})'))

    def load_users(self, options, for_update=False):
        users = User.objects.all()
        if for_update:
            users = users.select_for_update()
        users_by_id = users.in_bulk([options['primary'], options['secondary']])
        missing_ids = [
            user_id for user_id in (options['primary'], options['secondary'])
            if user_id not in users_by_id
        ]
        if missing_ids:
            raise CommandError(
                f'No user with ID: {", ".join(str(user_id) for user_id in missing_ids)}')
        return users_by_id[options['primary']], users_by_id[options['secondary']]

    def report(self, primary, secondary):
        self.stdout.write(
            f'Primary: {primary.pk} ({primary.username}, {primary.email})')
        self.stdout.write(
            f'Secondary: {secondary.pk} ({secondary.username}, {secondary.email})')
        self.report_relation_counts(secondary)
        self.report_dropped_email_addresses(secondary)
        self.report_access(secondary)
        self.report_shared_social_providers(primary, secondary)
        self.report_discarded_profile_fields(secondary)
        self.report_discarded_pod_player(primary, secondary)

    def report_relation_counts(self, secondary):
        for action, relations in (
            ('move', REPOINTED_RELATIONS),
            ('merge', MERGED_RELATIONS),
            ('delete', DISCARDED_RELATIONS),
        ):
            for relation in sorted(relations):
                row_count = get_relation_queryset(relation, secondary).count()
                if row_count:
                    self.stdout.write(
                        f'  {action}: {relation[0]}.{relation[1]} ({row_count})')

    def report_dropped_email_addresses(self, secondary):
        EmailAddress = apps.get_model('account.EmailAddress')
        for email_address in EmailAddress.objects.filter(user=secondary):
            self.stdout.write(self.style.WARNING(
                f'Dropping email address (becomes available for signup): {email_address.email}'))

    def report_access(self, secondary):
        if secondary.is_staff or secondary.is_superuser:
            self.stdout.write(self.style.WARNING(
                f'Secondary has is_staff={secondary.is_staff}, '
                f'is_superuser={secondary.is_superuser} (not copied)'))
        for group in secondary.groups.all():
            self.stdout.write(self.style.WARNING(
                f'Secondary group not copied: {group.name}'))
        for permission in secondary.user_permissions.all():
            self.stdout.write(self.style.WARNING(
                f'Secondary permission not copied: {permission.content_type.app_label}.{permission.codename}'))

    def report_shared_social_providers(self, primary, secondary):
        SocialAccount = apps.get_model('socialaccount.SocialAccount')
        primary_providers = set(SocialAccount.objects.filter(
            user=primary).values_list('provider', flat=True))
        secondary_providers = set(SocialAccount.objects.filter(
            user=secondary).values_list('provider', flat=True))
        for provider in sorted(primary_providers & secondary_providers):
            self.stdout.write(self.style.WARNING(
                f'Both users have a {provider} account; primary will have two'))

    def report_discarded_profile_fields(self, secondary):
        profile_relations = [('user_profile.UserProfile', 'user'), ('pmc.PmcProfile', 'user')]
        for relation in profile_relations:
            profile = get_relation_queryset(relation, secondary).first()
            if profile is None:
                continue
            for field in profile._meta.concrete_fields:
                if field.primary_key or field.name == 'user':
                    continue
                value = getattr(profile, field.attname)
                if value not in (None, '', field.get_default()):
                    self.stdout.write(
                        f'  Discarding {profile._meta.label}.{field.name}: {value}')

    def report_discarded_pod_player(self, primary, secondary):
        PodPlayer = apps.get_model('transporter_platform.PodPlayer')
        PastMatch = apps.get_model('transporter_platform.PastMatch')
        secondary_pod_player = PodPlayer.objects.filter(user=secondary).first()
        if secondary_pod_player is None or not PodPlayer.objects.filter(user=primary).exists():
            return
        past_match_count = PastMatch.objects.filter(
            Q(player=secondary_pod_player) | Q(opponent=secondary_pod_player)
        ).count()
        self.stdout.write(self.style.WARNING(
            f'Both users have a PodPlayer; deleting the secondary\'s cascades to '
            f'{past_match_count} transporter_platform.PastMatch rows'))

    def report_conflicts(self, conflicts):
        for conflict in conflicts:
            self.stdout.write(self.style.ERROR(conflict))
