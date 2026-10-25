from contextlib import contextmanager

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from . import engine
from .engine import Action, PlayedDeckRule, Seat


CODE_CHARACTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generate_template_code():
    while True:
        code = 'tst_' + get_random_string(6, allowed_chars=CODE_CHARACTERS)
        if not SessionTemplate.objects.filter(code=code).exists():
            return code


def generate_session_code():
    while True:
        code = 'ts_' + get_random_string(6, allowed_chars=CODE_CHARACTERS)
        if not Session.objects.filter(code=code).exists():
            return code


class SessionTemplate(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = 'private', _('Private')
        PUBLIC = 'public', _('Public')

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='trade_secrets_templates')
    system_key = models.SlugField(max_length=30, unique=True, null=True, blank=True)
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE)
    archived_on = models.DateTimeField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=Q(owner__isnull=False) | Q(system_key__isnull=False),
                name='trade_secrets_template_owner_or_system'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_template_code()
        super().save(*args, **kwargs)

    @classmethod
    def usable_by(cls, user):
        if not user.is_authenticated:
            return cls.objects.filter(owner__isnull=True, archived_on__isnull=True)
        return cls.objects.filter(Q(owner__isnull=True) | Q(owner=user), archived_on__isnull=True)

    @classmethod
    def create_with_steps(cls, owner, name, description, step_specs):
        errors = engine.validate_template_steps(step_specs)
        if errors:
            raise ValidationError(errors)
        with transaction.atomic():
            template = cls.objects.create(owner=owner, name=name, description=description)
            TemplateStep.objects.bulk_create(
                TemplateStep(
                    template=template,
                    order=order,
                    action=spec.action,
                    quantity=spec.quantity,
                    played_deck_rule=spec.played_deck_rule,
                )
                for order, spec in enumerate(step_specs)
            )
        return template

    @property
    def is_system(self):
        return self.owner_id is None

    @property
    def is_archived(self):
        return self.archived_on is not None

    @property
    def is_public(self):
        return self.visibility == self.Visibility.PUBLIC

    def is_owned_by(self, user):
        return user.is_authenticated and self.owner_id == user.id

    def can_view(self, user):
        if self.is_system or self.is_owned_by(user):
            return True
        return user.is_authenticated and self.is_public

    def can_manage(self, user):
        return not self.is_system and self.is_owned_by(user)

    def can_start_session(self, user):
        return user.is_authenticated and self.can_view(user) and not self.is_archived

    def can_delete(self, user):
        return self.can_manage(user) and self.is_archived and not self.sessions.exists()

    def archive(self):
        self.archived_on = timezone.now()
        self.save(update_fields=['archived_on'])

    def unarchive(self):
        self.archived_on = None
        self.save(update_fields=['archived_on'])

    def set_visibility(self, visibility):
        if visibility not in self.Visibility.values:
            raise ValidationError(_('Choose a valid visibility.'))
        self.visibility = visibility
        self.save(update_fields=['visibility'])

    @cached_property
    def step_specs(self):
        return [step.to_spec() for step in self.steps.all()]

    @property
    def deck_count(self):
        return self.step_specs[0].quantity if self.step_specs else 0


class TemplateStep(models.Model):
    template = models.ForeignKey(
        SessionTemplate, on_delete=models.CASCADE, related_name='steps')
    order = models.PositiveSmallIntegerField()
    action = models.CharField(max_length=20, choices=Action.choices)
    quantity = models.PositiveSmallIntegerField(default=1)
    played_deck_rule = models.CharField(
        max_length=12, choices=PlayedDeckRule.choices, default=PlayedDeckRule.INELIGIBLE)

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'order'], name='trade_secrets_unique_template_step_order'),
            models.CheckConstraint(
                condition=Q(quantity__gte=1), name='trade_secrets_step_quantity_positive'),
            models.CheckConstraint(
                condition=~Q(action=Action.PLAY) | Q(quantity=1),
                name='trade_secrets_play_step_single_game'),
        ]

    def __str__(self):
        return f'{self.template.name} #{self.order + 1}: {engine.step_label(self.template.step_specs, self.to_spec())}'

    def to_spec(self):
        return engine.StepSpec(self.order, self.action, self.quantity, self.played_deck_rule)


class Session(models.Model):
    code = models.CharField(max_length=10, unique=True)
    template = models.ForeignKey(
        SessionTemplate, on_delete=models.RESTRICT, related_name='sessions')
    host = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='hosted_trade_secrets_sessions')
    guest = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='joined_trade_secrets_sessions')
    revealed_step_count = models.PositiveSmallIntegerField(default=0)
    version = models.PositiveIntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_on']
        constraints = [
            models.CheckConstraint(
                condition=~Q(guest=F('host')), name='trade_secrets_guest_is_not_host'),
        ]

    def __str__(self):
        return f'{self.template.name} ({self.code})'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_session_code()
        super().save(*args, **kwargs)

    @property
    def has_guest(self):
        return self.guest_id is not None

    def seat_for(self, user):
        if not user.is_authenticated:
            return None
        if user.id == self.host_id:
            return Seat.HOST
        if user.id == self.guest_id:
            return Seat.GUEST
        return None

    def user_for(self, seat):
        return self.host if seat == Seat.HOST else self.guest

    def seat_names(self):
        return {
            Seat.HOST: self.host.username,
            Seat.GUEST: self.guest.username if self.guest else str(_('Opponent')),
        }

    def template_steps(self):
        return list(self.template.steps.all())

    def build_engine_state(self):
        steps = self.template_steps()
        pool = [
            engine.PoolDeck(session_deck.id, session_deck.seat)
            for session_deck in self.decks.all()
        ]
        return engine.replay(
            [step.to_spec() for step in steps],
            pool,
            self.revealed_step_count,
            self.revealed_picks(),
            self.winners_by_order(),
        )

    def revealed_picks(self):
        picks = {}
        submissions = self.submissions.filter(
            step__order__lt=self.revealed_step_count
        ).select_related('step').prefetch_related('decks', 'matchups')
        for submission in submissions:
            picks.setdefault(submission.step.order, {})[submission.seat] = submission.picked_ids()
        return picks

    def banned_matchup_orders(self):
        return set(TemplateStep.objects.filter(
            matchup_bans__session=self,
            matchup_bans__step__order__lt=self.revealed_step_count,
        ).values_list('order', flat=True))

    def winners_by_order(self):
        return {
            result.step.order: result.winner_seat
            for result in self.results.select_related('step')
        }

    def pending_submission_for(self, seat):
        if self.revealed_step_count >= self.template.steps.count():
            return None
        return self.submissions.filter(
            seat=seat, step__order=self.revealed_step_count
        ).prefetch_related('decks', 'matchups').first()

    def step_at(self, order):
        return self.template.steps.get(order=order)

    @contextmanager
    def _locked(self):
        with transaction.atomic():
            locked = Session.objects.select_for_update().get(pk=self.pk)
            revealed_count_when_locked = locked.revealed_step_count
            yield locked
            updated_rows = Session.objects.filter(
                pk=locked.pk, revealed_step_count=revealed_count_when_locked
            ).update(
                guest=locked.guest,
                revealed_step_count=locked.revealed_step_count,
                version=F('version') + 1,
                updated_on=timezone.now(),
            )
            if not updated_rows:
                raise ValidationError(_('That step was already revealed.'))
        self.refresh_from_db()

    def join(self, user):
        with self._locked() as session:
            if session.host_id == user.id:
                raise ValidationError(_('You are already hosting this session.'))
            if session.guest_id is not None:
                raise ValidationError(_('This seat was just filled.'))
            session.guest = user
            session.advance()

    def submit_decks(self, seat, user, deck_ids, source_version=None):
        with self._locked() as session:
            if session.revealed_step_count > 0:
                raise ValidationError(_('Decks have already been revealed.'))
            submit_step = session.step_at(0)
            if len(set(deck_ids)) != len(deck_ids):
                raise ValidationError(_('Each deck can only be submitted once.'))
            if len(deck_ids) != submit_step.quantity:
                raise ValidationError(
                    _('Submit exactly {count} decks.').format(count=submit_step.quantity))
            session.decks.filter(seat=seat).delete()
            SessionDeck.objects.bulk_create(
                SessionDeck(
                    session=session, seat=seat, deck_id=deck_id,
                    source_version=source_version, sort_order=sort_order)
                for sort_order, deck_id in enumerate(deck_ids)
            )
            StepSubmission.objects.update_or_create(
                session=session, step=submit_step, seat=seat,
                defaults={'submitted_by': user})
            session.advance()

    def submit_picks(self, seat, user, step_order, deck_ids):
        with self._locked() as session:
            state = session.build_engine_state()
            step = state.current_step
            if step is None or step.order != step_order or step.is_submit:
                raise ValidationError(_('That step was already revealed.'))
            if engine.missing_result_step(state) is not None:
                raise ValidationError(_('Record the previous game result before picking.'))
            if engine.phase(state, session.has_guest) in engine.FINISHED_PHASES:
                raise ValidationError(_('This session is over.'))
            errors = engine.validate_picks(state, step, seat, deck_ids)
            if errors:
                raise ValidationError(errors)
            submission, _created = StepSubmission.objects.update_or_create(
                session=session, step=session.step_at(step_order), seat=seat,
                defaults={'submitted_by': user})
            if step.is_matchup_ban:
                submission.matchups.set(session.template.steps.filter(order__in=deck_ids))
            else:
                submission.decks.set(deck_ids)
            session.advance()

    def is_revealed_game(self, step_order):
        if step_order >= self.revealed_step_count or step_order in self.banned_matchup_orders():
            return False
        step_specs = self.template.step_specs
        if step_order >= len(step_specs) or not step_specs[step_order].is_play:
            return False
        return not engine.is_awaiting_matchup_ban(step_specs, step_specs[step_order], self.revealed_step_count)

    def is_result_locked(self, step_order):
        result_orders = self.results.values_list('step__order', flat=True)
        return engine.is_result_locked(self.template.step_specs, step_order, result_orders)

    def can_record_result(self, step_order):
        if not self.is_revealed_game(step_order):
            return False
        has_result = self.results.filter(step__order=step_order).exists()
        return not has_result or not self.is_result_locked(step_order)

    def can_reset_result(self, step_order):
        return (
            self.is_revealed_game(step_order)
            and self.results.filter(step__order=step_order).exists()
            and not self.is_result_locked(step_order)
        )

    def record_result(self, user, step_order, winner_seat, host_score=None, guest_score=None):
        if winner_seat not in Seat.values:
            raise ValidationError(_('Choose a winner.'))
        if (host_score is None) != (guest_score is None):
            raise ValidationError(_('Enter a score for both players, or leave both blank.'))
        if any(score is not None and score < 0 for score in (host_score, guest_score)):
            raise ValidationError(_('Scores cannot be negative.'))
        with self._locked() as session:
            if not session.is_revealed_game(step_order):
                raise ValidationError(_('That game cannot have a result yet.'))
            if not session.can_record_result(step_order):
                raise ValidationError(_('This result is locked because a later game has a result.'))
            PlayResult.objects.update_or_create(
                session=session, step=session.step_at(step_order),
                defaults={
                    'winner_seat': winner_seat,
                    'host_score': host_score,
                    'guest_score': guest_score,
                    'updated_by': user,
                })
            session.discard_invalid_pending_picks()
            session.advance()

    def reset_result(self, step_order):
        with self._locked() as session:
            if not session.can_reset_result(step_order):
                raise ValidationError(_('Only the most recent result can be reset.'))
            session.results.filter(step__order=step_order).delete()
            session.discard_invalid_pending_picks()
            session.advance()

    def discard_invalid_pending_picks(self):
        state = self.build_engine_state()
        step = state.current_step
        if step is None or step.is_submit:
            return
        for submission in self.submissions.filter(step__order=step.order).prefetch_related('decks', 'matchups'):
            if engine.validate_picks(state, step, submission.seat, submission.picked_ids()):
                submission.delete()

    def advance(self):
        if not self.has_guest:
            return
        while True:
            state = self.build_engine_state()
            step = state.current_step
            if step is None or engine.missing_result_step(state) is not None:
                return
            if step.is_play and engine.phase(state, has_guest=True) == engine.Phase.CONCLUDED:
                return
            seats_to_wait_for = engine.SEATS if step.is_submit else engine.seats_needing_picks(state, step)
            submitted_seats = set(
                self.submissions.filter(step__order=step.order).values_list('seat', flat=True))
            if not set(seats_to_wait_for) <= submitted_seats:
                return
            self.revealed_step_count = step.order + 1


class SessionDeck(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='decks')
    seat = models.CharField(max_length=5, choices=Seat.choices)
    deck = models.ForeignKey(
        'decks.Deck', on_delete=models.PROTECT, related_name='trade_secrets_entries')
    source_version = models.ForeignKey(
        'lineups.LineupVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='trade_secrets_entries')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['seat', 'sort_order']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'seat', 'deck'], name='trade_secrets_unique_seat_deck'),
        ]

    def __str__(self):
        return f'{self.session.code} {self.seat}: {self.deck}'


class StepSubmission(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='submissions')
    step = models.ForeignKey(TemplateStep, on_delete=models.RESTRICT, related_name='submissions')
    seat = models.CharField(max_length=5, choices=Seat.choices)
    decks = models.ManyToManyField(SessionDeck, blank=True, related_name='submissions')
    matchups = models.ManyToManyField(TemplateStep, blank=True, related_name='matchup_bans')
    submitted_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='trade_secrets_submissions')
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'step', 'seat'], name='trade_secrets_unique_step_seat_submission'),
        ]

    def __str__(self):
        return f'{self.session.code} step {self.step.order + 1} {self.seat}'

    def picked_ids(self):
        if self.step.action == Action.BAN_MATCHUP:
            return tuple(matchup.order for matchup in self.matchups.all())
        return tuple(deck.id for deck in self.decks.all())


class PlayResult(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='results')
    step = models.ForeignKey(TemplateStep, on_delete=models.RESTRICT, related_name='results')
    winner_seat = models.CharField(max_length=5, choices=Seat.choices)
    host_score = models.PositiveIntegerField(null=True, blank=True)
    guest_score = models.PositiveIntegerField(null=True, blank=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'step'], name='trade_secrets_unique_session_step_result'),
        ]

    def __str__(self):
        return f'{self.session.code} step {self.step.order + 1}: {self.winner_seat}'
