import importlib
import uuid
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.test import TestCase, override_settings
from django.urls import reverse, reverse_lazy

from decks.models import Deck
from lineups.models import Lineup, LineupVersion, LineupVersionDeck

from . import engine
from .engine import Phase, Seat, StepSpec
from .models import PlayResult, Session, SessionTemplate, StepSubmission
from .session_view import build_session_view


FAST_PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
SIMPLE_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

HOST = Seat.HOST
GUEST = Seat.GUEST


def make_template_specs(*descriptions):
    specs = []
    for order, description in enumerate(descriptions):
        action, _, setting = description.partition(':')
        if action == 'play':
            specs.append(StepSpec(order, action, 1, setting or 'ineligible'))
        else:
            specs.append(StepSpec(order, action, int(setting or 1)))
    return specs


class TradeSecretsTestMixin:
    def make_user(self, username):
        return User.objects.create_user(username=username, password='password')

    def make_decks(self, count, prefix):
        return [
            Deck.objects.create(id=uuid.uuid4(), name=f'{prefix} Deck {number}')
            for number in range(1, count + 1)
        ]

    def make_template(self, owner, *descriptions, name='Custom'):
        return SessionTemplate.create_with_steps(owner, name, '', make_template_specs(*descriptions))

    def make_unvalidated_template(self, owner, *descriptions):
        template = SessionTemplate.objects.create(owner=owner, name='Unvalidated')
        for spec in make_template_specs(*descriptions):
            template.steps.create(
                order=spec.order, action=spec.action, quantity=spec.quantity,
                played_deck_rule=spec.played_deck_rule)
        return template

    def system_template(self, key):
        return SessionTemplate.objects.get(system_key=key)

    def start_session(self, template, host, guest=None):
        session = Session.objects.create(template=template, host=host)
        if guest:
            session.join(guest)
        return session

    def submit_both(self, session, host_decks, guest_decks):
        session.submit_decks(HOST, session.host, [deck.id for deck in host_decks])
        session.submit_decks(GUEST, session.guest, [deck.id for deck in guest_decks])

    def session_deck_id(self, session, deck):
        return session.decks.get(deck=deck).id

    def pick(self, session, seat, *decks):
        session.submit_picks(
            seat, session.user_for(seat), session.revealed_step_count,
            [self.session_deck_id(session, deck) for deck in decks])


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class SeededTemplateTests(TestCase):
    def test_exactly_the_three_system_templates_are_seeded(self):
        self.assertCountEqual(
            SessionTemplate.objects.filter(owner__isnull=True).values_list('system_key', flat=True),
            ['triad', 'triad-bo1', 'hexad'])

    def test_seeded_templates_are_valid(self):
        for template in SessionTemplate.objects.filter(owner__isnull=True):
            self.assertEqual(engine.validate_template_steps(template.step_specs), [], template.name)

    def test_seeded_step_definitions(self):
        def summary(key):
            return [(spec.action, spec.quantity, spec.played_deck_rule)
                    for spec in SessionTemplate.objects.get(system_key=key).step_specs]

        self.assertEqual(summary('triad'), [
            ('submit', 3, 'ineligible'), ('ban', 1, 'ineligible'),
            ('play', 1, 'losing_only'), ('play', 1, 'losing_only'), ('play', 1, 'losing_only')])
        self.assertEqual(summary('triad-bo1'), [
            ('submit', 3, 'ineligible'), ('ban', 1, 'ineligible'), ('play', 1, 'ineligible')])
        self.assertEqual(summary('hexad'), [
            ('submit', 6, 'ineligible'), ('ban', 1, 'ineligible'), ('safe', 1, 'ineligible'),
            ('ban', 1, 'ineligible'), ('play', 1, 'ineligible'), ('play', 1, 'ineligible'),
            ('play', 1, 'ineligible')])


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class TemplateModelTests(TradeSecretsTestMixin, TestCase):
    def setUp(self):
        self.alice = self.make_user('alice')
        self.bob = self.make_user('bob')

    def test_codes_are_generated(self):
        template = self.make_template(self.alice, 'submit:3', 'play')
        session = Session.objects.create(template=template, host=self.alice)
        self.assertTrue(template.code.startswith('tst_'))
        self.assertRegex(session.code, r'^ts_[A-Z0-9]{6}$')

    def test_usable_by_returns_system_and_own_unarchived_templates(self):
        own = self.make_template(self.alice, 'submit:3', 'play', name='Mine')
        self.make_template(self.bob, 'submit:3', 'play', name='Theirs')
        archived = self.make_template(self.alice, 'submit:3', 'play', name='Old')
        archived.archive()
        usable = SessionTemplate.usable_by(self.alice)
        self.assertIn(own, usable)
        self.assertNotIn(archived, usable)
        self.assertEqual(usable.filter(owner=self.bob).count(), 0)
        self.assertEqual(usable.filter(owner__isnull=True).count(), 3)

    def test_template_requires_owner_or_system_key(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SessionTemplate.objects.create(name='Orphan')

    def test_delete_requires_archived_and_unused(self):
        template = self.make_template(self.alice, 'submit:3', 'play')
        self.assertFalse(template.can_delete(self.alice))
        template.archive()
        self.assertTrue(template.can_delete(self.alice))
        self.assertFalse(template.can_delete(self.bob))
        template.unarchive()
        self.start_session(template, self.alice)
        template.archive()
        self.assertFalse(template.can_delete(self.alice))
        with self.assertRaises(RestrictedError):
            template.delete()

    def test_archived_template_cannot_start_sessions(self):
        template = self.make_template(self.alice, 'submit:3', 'play')
        self.assertTrue(template.can_start_session(self.alice))
        template.archive()
        self.assertFalse(template.can_start_session(self.alice))

    def test_system_templates_cannot_be_managed(self):
        triad = self.system_template('triad')
        self.assertFalse(triad.can_manage(self.alice))
        self.assertTrue(triad.can_start_session(self.alice))

    def test_guest_cannot_be_host(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Session.objects.filter(pk=session.pk).update(guest=self.alice)


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class SessionFlowTests(TradeSecretsTestMixin, TestCase):
    def setUp(self):
        self.alice = self.make_user('alice')
        self.bob = self.make_user('bob')
        self.carol = self.make_user('carol')
        self.alice_decks = self.make_decks(6, 'Alice')
        self.bob_decks = self.make_decks(6, 'Bob')

    def phase(self, session):
        return engine.phase(session.build_engine_state(), session.has_guest)

    def test_join_fills_seat_once(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        with self.assertRaises(ValidationError):
            session.join(self.alice)
        session.join(self.bob)
        self.assertEqual(session.guest, self.bob)
        with self.assertRaises(ValidationError):
            session.join(self.carol)
        self.assertEqual(Session.objects.get(pk=session.pk).guest, self.bob)

    def test_every_write_bumps_version(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        starting_version = session.version
        session.join(self.bob)
        self.assertEqual(session.version, starting_version + 1)

    def test_host_can_submit_before_guest_joins_and_reveal_waits_for_both(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        session.submit_decks(HOST, self.alice, [deck.id for deck in self.alice_decks[:3]])
        self.assertEqual(session.revealed_step_count, 0)
        session.join(self.bob)
        self.assertEqual(session.revealed_step_count, 0)
        session.submit_decks(GUEST, self.bob, [deck.id for deck in self.bob_decks[:3]])
        self.assertEqual(session.revealed_step_count, 1)
        self.assertEqual(self.phase(session), Phase.SELECTING)

    def test_resubmitting_decks_replaces_pool_until_reveal(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        session.submit_decks(HOST, self.alice, [deck.id for deck in self.alice_decks[:3]])
        session.submit_decks(HOST, self.alice, [deck.id for deck in self.alice_decks[3:6]])
        self.assertCountEqual(
            session.decks.filter(seat=HOST).values_list('deck_id', flat=True),
            [deck.id for deck in self.alice_decks[3:6]])
        session.submit_decks(GUEST, self.bob, [deck.id for deck in self.bob_decks[:3]])
        with self.assertRaises(ValidationError):
            session.submit_decks(HOST, self.alice, [deck.id for deck in self.alice_decks[:3]])

    def test_wrong_deck_count_is_rejected(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        with self.assertRaises(ValidationError):
            session.submit_decks(HOST, self.alice, [deck.id for deck in self.alice_decks[:2]])
        self.assertFalse(session.decks.exists())

    def test_pick_can_change_until_both_submit(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, HOST, self.bob_decks[1])
        self.assertEqual(session.revealed_step_count, 1)
        self.pick(session, GUEST, self.alice_decks[2])
        self.assertEqual(session.revealed_step_count, 2)
        state = session.build_engine_state()
        self.assertTrue(state.decks[self.session_deck_id(session, self.bob_decks[1])].is_banned)
        self.assertFalse(state.decks[self.session_deck_id(session, self.bob_decks[0])].is_banned)

    def test_stale_step_order_is_rejected(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, GUEST, self.alice_decks[0])
        with self.assertRaises(ValidationError):
            session.submit_picks(HOST, self.alice, 1, [self.session_deck_id(session, self.bob_decks[1])])

    def test_illegal_pick_is_rejected_and_nothing_written(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        with self.assertRaises(ValidationError):
            self.pick(session, HOST, self.alice_decks[0])
        self.assertFalse(StepSubmission.objects.filter(session=session, step__order=1).exists())

    def test_pending_picks_do_not_affect_state(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[0])
        state = session.build_engine_state()
        self.assertFalse(any(deck.is_banned for deck in state.decks.values()))

    def test_triad_two_nothing_concludes(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[2])
        self.pick(session, GUEST, self.alice_decks[2])
        self.pick(session, HOST, self.alice_decks[0])
        self.pick(session, GUEST, self.bob_decks[0])
        self.assertEqual(self.phase(session), Phase.AWAITING_RESULT)
        with self.assertRaises(ValidationError):
            self.pick(session, HOST, self.alice_decks[1])
        session.record_result(self.bob, 2, HOST, 3, 1)
        self.assertEqual(self.phase(session), Phase.SELECTING)
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 3, HOST, 3, 2)
        self.assertEqual(self.phase(session), Phase.CONCLUDED)

    def test_triad_bo1_completes_after_one_game(self):
        session = self.start_session(self.system_template('triad-bo1'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, GUEST, self.alice_decks[0])
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[1])
        self.assertEqual(self.phase(session), Phase.COMPLETE)

    def test_hexad_full_flow(self):
        session = self.start_session(self.system_template('hexad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks, self.bob_decks)
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, GUEST, self.alice_decks[0])
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[1])
        with self.assertRaises(ValidationError):
            self.pick(session, GUEST, self.alice_decks[1])
        self.pick(session, HOST, self.bob_decks[2])
        self.pick(session, GUEST, self.alice_decks[2])
        for host_deck, guest_deck in zip(self.alice_decks[3:6], self.bob_decks[3:6]):
            self.pick(session, HOST, host_deck)
            self.pick(session, GUEST, guest_deck)
        self.assertEqual(self.phase(session), Phase.COMPLETE)
        self.assertEqual(session.revealed_step_count, 7)

    def test_custom_steal_template_full_flow(self):
        template = self.make_template(
            self.alice, 'submit:4', 'ban:1', 'safe:1', 'steal:1', 'play', 'play', 'play', name='Tetrad')
        session = self.start_session(template, self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:4], self.bob_decks[:4])
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, GUEST, self.alice_decks[0])
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[1])
        self.pick(session, HOST, self.bob_decks[2])
        self.pick(session, GUEST, self.alice_decks[2])
        state = session.build_engine_state()
        self.assertEqual(state.decks[self.session_deck_id(session, self.bob_decks[2])].holder_seat, HOST)
        self.assertEqual(state.decks[self.session_deck_id(session, self.alice_decks[2])].holder_seat, GUEST)
        self.pick(session, HOST, self.bob_decks[2])
        self.pick(session, GUEST, self.alice_decks[2])
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[1])
        self.pick(session, HOST, self.alice_decks[3])
        self.pick(session, GUEST, self.bob_decks[3])
        self.assertEqual(self.phase(session), Phase.COMPLETE)

    def test_step_nobody_can_act_on_auto_reveals(self):
        template = self.make_unvalidated_template(
            self.alice, 'submit:2', 'play:losing_only', 'play:losing_only', 'safe:1', 'ban:1')
        session = self.start_session(template, self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:2], self.bob_decks[:2])
        self.pick(session, HOST, self.alice_decks[0])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 1, HOST)
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 2, GUEST)
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[1])
        self.assertEqual(session.revealed_step_count, 5)
        self.assertEqual(self.phase(session), Phase.COMPLETE)

    def test_seat_with_nothing_to_pick_is_not_waited_for(self):
        template = self.make_unvalidated_template(
            self.alice, 'submit:2', 'play:losing_only', 'safe:1', 'ban:1', 'play:eligible')
        session = self.start_session(template, self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:2], self.bob_decks[:2])
        self.pick(session, HOST, self.alice_decks[0])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 1, HOST)
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[0])
        self.assertEqual(session.revealed_step_count, 3)
        self.pick(session, HOST, self.bob_decks[1])
        self.assertEqual(session.revealed_step_count, 4)


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class ResultTests(TradeSecretsTestMixin, TestCase):
    def setUp(self):
        self.alice = self.make_user('alice')
        self.bob = self.make_user('bob')
        self.alice_decks = self.make_decks(3, 'Alice')
        self.bob_decks = self.make_decks(3, 'Bob')
        self.session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(self.session, self.alice_decks, self.bob_decks)
        self.pick(self.session, HOST, self.bob_decks[2])
        self.pick(self.session, GUEST, self.alice_decks[2])

    def play_game(self, host_deck, guest_deck):
        self.pick(self.session, HOST, host_deck)
        self.pick(self.session, GUEST, guest_deck)

    def test_unrevealed_game_cannot_have_result(self):
        with self.assertRaises(ValidationError):
            self.session.record_result(self.alice, 2, HOST)

    def test_non_play_step_cannot_have_result(self):
        with self.assertRaises(ValidationError):
            self.session.record_result(self.alice, 1, HOST)

    def test_either_player_can_edit_result(self):
        self.play_game(self.alice_decks[0], self.bob_decks[0])
        self.session.record_result(self.alice, 2, HOST, 3, 1)
        self.session.record_result(self.bob, 2, GUEST, 3, 2)
        result = PlayResult.objects.get(session=self.session)
        self.assertEqual(
            (result.winner_seat, result.host_score, result.guest_score, result.updated_by), (GUEST, 3, 2, self.bob))

    def test_earlier_result_locks_once_later_result_recorded(self):
        self.play_game(self.alice_decks[0], self.bob_decks[0])
        self.session.record_result(self.alice, 2, HOST)
        self.play_game(self.alice_decks[1], self.bob_decks[0])
        self.session.record_result(self.alice, 3, GUEST)
        with self.assertRaises(ValidationError):
            self.session.record_result(self.alice, 2, GUEST)
        with self.assertRaises(ValidationError):
            self.session.reset_result(2)

    def test_reset_unwinds_results_one_at_a_time(self):
        self.play_game(self.alice_decks[0], self.bob_decks[0])
        self.session.record_result(self.alice, 2, HOST)
        self.play_game(self.alice_decks[1], self.bob_decks[0])
        self.session.record_result(self.alice, 3, GUEST)
        self.session.reset_result(3)
        self.assertTrue(self.session.can_reset_result(2))
        self.session.reset_result(2)
        self.assertFalse(self.session.results.exists())

    def test_reset_of_blocking_result_blocks_progress_again(self):
        self.play_game(self.alice_decks[0], self.bob_decks[0])
        self.session.record_result(self.alice, 2, HOST)
        self.session.reset_result(2)
        self.assertEqual(
            engine.phase(self.session.build_engine_state(), True), Phase.AWAITING_RESULT)

    def test_result_edit_keeps_locked_pick_that_is_still_legal(self):
        self.play_game(self.alice_decks[0], self.bob_decks[0])
        self.session.record_result(self.alice, 2, GUEST)
        self.pick(self.session, GUEST, self.bob_decks[1])
        self.assertTrue(self.session.pending_submission_for(GUEST))
        self.session.record_result(self.alice, 2, HOST)
        self.assertIsNotNone(self.session.pending_submission_for(GUEST))
        self.pick(self.session, HOST, self.alice_decks[1])
        self.assertEqual(self.session.revealed_step_count, 4)

    def test_result_edit_clears_pick_of_deck_that_became_ineligible(self):
        self.play_game(self.alice_decks[0], self.bob_decks[0])
        self.session.record_result(self.alice, 2, GUEST)
        self.pick(self.session, HOST, self.alice_decks[0])
        self.session.record_result(self.bob, 2, HOST)
        self.assertIsNone(self.session.pending_submission_for(HOST))
        self.assertEqual(self.session.revealed_step_count, 3)


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class HomeViewTests(TestCase):
    def test_home_lists_system_formats(self):
        response = self.client.get(reverse('trade_secrets:home'))
        self.assertContains(response, 'Triad Bo1')
        self.assertContains(response, 'Hexad')

    def test_gizmo_list_links_to_trade_secrets(self):
        response = self.client.get(reverse('redacted-list'))
        self.assertContains(response, reverse('trade_secrets:home'))


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class ReviewRegressionModelTests(TradeSecretsTestMixin, TestCase):
    def setUp(self):
        self.alice = self.make_user('alice')
        self.bob = self.make_user('bob')
        self.alice_decks = self.make_decks(6, 'Alice')
        self.bob_decks = self.make_decks(6, 'Bob')

    def start_triad(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[2])
        self.pick(session, GUEST, self.alice_decks[2])
        return session

    def start_hexad_through_two_games(self):
        session = self.start_session(self.system_template('hexad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks, self.bob_decks)
        for host_deck, guest_deck in [
                (self.bob_decks[0], self.alice_decks[0]),
                (self.alice_decks[1], self.bob_decks[1]),
                (self.bob_decks[2], self.alice_decks[2]),
                (self.alice_decks[3], self.bob_decks[3]),
                (self.alice_decks[4], self.bob_decks[4])]:
            self.pick(session, HOST, host_deck)
            self.pick(session, GUEST, guest_deck)
        return session

    def phase(self, session):
        return engine.phase(session.build_engine_state(), session.has_guest)

    def test_missing_earlier_result_can_be_recorded_after_a_later_one(self):
        session = self.start_hexad_through_two_games()
        session.record_result(self.alice, 5, GUEST)
        session.record_result(self.alice, 4, HOST)
        self.assertEqual(session.results.count(), 2)
        with self.assertRaises(ValidationError):
            session.record_result(self.alice, 4, GUEST)
        with self.assertRaises(ValidationError):
            session.reset_result(4)

    def test_existing_result_stays_editable_while_later_game_has_no_result(self):
        session = self.start_hexad_through_two_games()
        session.record_result(self.alice, 4, HOST)
        session.record_result(self.bob, 4, GUEST, 1, 3)
        self.assertEqual(session.results.get().winner_seat, GUEST)

    def test_picks_are_rejected_once_session_concludes(self):
        session = self.start_triad()
        self.pick(session, HOST, self.alice_decks[0])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 2, HOST)
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 3, HOST)
        version = session.version
        with self.assertRaises(ValidationError):
            self.pick(session, GUEST, self.bob_decks[1])
        session.refresh_from_db()
        self.assertEqual(session.version, version)
        self.assertFalse(StepSubmission.objects.filter(session=session, step__order=4).exists())

    def test_result_edit_moves_between_concluded_and_selecting(self):
        session = self.start_triad()
        self.pick(session, HOST, self.alice_decks[0])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 2, HOST)
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 3, HOST)
        self.assertEqual(self.phase(session), Phase.CONCLUDED)
        session.record_result(self.bob, 3, GUEST)
        self.assertEqual(self.phase(session), Phase.SELECTING)
        self.pick(session, GUEST, self.bob_decks[1])
        session.record_result(self.alice, 3, HOST)
        self.assertEqual(self.phase(session), Phase.CONCLUDED)

    def test_reset_that_reblocks_keeps_legal_pending_pick(self):
        session = self.start_triad()
        self.pick(session, HOST, self.alice_decks[0])
        self.pick(session, GUEST, self.bob_decks[0])
        session.record_result(self.alice, 2, GUEST)
        self.pick(session, GUEST, self.bob_decks[1])
        session.reset_result(2)
        self.assertEqual(self.phase(session), Phase.AWAITING_RESULT)
        self.assertIsNotNone(session.pending_submission_for(GUEST))
        session.record_result(self.alice, 2, HOST)
        self.assertIsNotNone(session.pending_submission_for(GUEST))

    def test_duplicate_deck_ids_are_a_validation_error(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        deck_id = self.alice_decks[0].id
        with self.assertRaises(ValidationError):
            session.submit_decks(HOST, self.alice, [deck_id, deck_id, deck_id])
        self.assertFalse(session.decks.exists())

    def test_result_inputs_are_validated(self):
        session = self.start_triad()
        self.pick(session, HOST, self.alice_decks[0])
        self.pick(session, GUEST, self.bob_decks[0])
        version = session.version
        with self.assertRaises(ValidationError):
            session.record_result(self.alice, 2, 'nobody')
        with self.assertRaises(ValidationError):
            session.record_result(self.alice, 2, HOST, 3)
        with self.assertRaises(ValidationError):
            session.record_result(self.alice, 2, HOST, -1, 2)
        with self.assertRaises(ValidationError):
            session.record_result(self.alice, 99, HOST)
        with self.assertRaises(ValidationError):
            session.reset_result(2)
        with self.assertRaises(ValidationError):
            session.reset_result(1)
        session.refresh_from_db()
        self.assertEqual(session.version, version)

    def test_invalid_template_cannot_be_created(self):
        with self.assertRaises(ValidationError):
            self.make_template(self.alice, 'submit:3', 'ban:3', 'play')
        self.assertFalse(SessionTemplate.objects.filter(owner=self.alice).exists())

    def test_deleting_a_user_removes_their_templates_and_sessions(self):
        template = self.make_template(self.alice, 'submit:3', 'ban:1', 'play')
        session = self.start_session(template, self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[0])
        self.alice.delete()
        self.assertFalse(Session.objects.filter(pk=session.pk).exists())
        self.assertFalse(SessionTemplate.objects.filter(pk=template.pk).exists())

    def test_deleting_a_guest_removes_sessions_they_joined(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.bob.delete()
        self.assertFalse(Session.objects.filter(pk=session.pk).exists())

    def test_seed_reverse_keeps_system_templates_in_use(self):
        seed_migration = importlib.import_module('trade_secrets.migrations.0002_seed_system_templates')
        self.start_session(self.system_template('triad'), self.alice)
        seed_migration.remove_unused_system_templates(django_apps, None)
        self.assertEqual(
            list(SessionTemplate.objects.filter(owner__isnull=True).values_list('system_key', flat=True)),
            ['triad'])
        seed_migration.seed_system_templates(django_apps, None)
        self.assertEqual(SessionTemplate.objects.filter(owner__isnull=True).count(), 3)
        self.assertEqual(self.system_template('triad').steps.count(), 5)


def fake_hydrate(deck, save=True):
    deck.name = f'Hydrated {str(deck.id)[:8]}'
    if save:
        deck.save()


def failing_hydrate(deck, save=True):
    raise ValueError('Failed to fetch deck data: 404 Not Found')


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class SessionViewTestCase(TradeSecretsTestMixin, TestCase):
    def setUp(self):
        self.alice = self.make_user('alice')
        self.bob = self.make_user('bob')
        self.carol = self.make_user('carol')
        self.alice_decks = self.make_decks(6, 'Alice')
        self.bob_decks = self.make_decks(6, 'Bob')

    def detail_url(self, session):
        return reverse('trade_secrets:session-detail', args=[session.code])

    def htmx_post(self, url, data):
        return self.client.post(url, data, HTTP_HX_REQUEST='true')

    def started_triad(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        return session


class SessionRoleViewTests(SessionViewTestCase):
    def test_anonymous_visitor_sees_invite_with_login(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, 'invites you to play')
        self.assertContains(response, 'Log in to join')
        self.assertNotContains(response, reverse('trade_secrets:session-join', args=[session.code]))

    def test_logged_in_visitor_sees_join_button(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, 'alice')
        self.assertContains(response, 'Join game')

    def test_host_sees_share_link_and_deck_form(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        self.client.force_login(self.alice)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, 'Invite your opponent')
        self.assertContains(response, 'Submit decks')
        self.assertNotContains(response, 'Join game')

    def test_join_fills_seat_and_redirects(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        self.client.force_login(self.bob)
        response = self.client.post(reverse('trade_secrets:session-join', args=[session.code]))
        self.assertRedirects(response, self.detail_url(session))
        session.refresh_from_db()
        self.assertEqual(session.guest, self.bob)

    def test_second_joiner_sees_spectator_view_with_note(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.client.force_login(self.carol)
        response = self.client.post(reverse('trade_secrets:session-join', args=[session.code]))
        self.assertContains(response, 'This seat was just filled.')
        self.assertContains(response, 'Spectating')
        session.refresh_from_db()
        self.assertEqual(session.guest, self.bob)

    def test_join_requires_login(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        response = self.client.post(reverse('trade_secrets:session-join', args=[session.code]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_returning_player_resumes_their_session(self):
        session = self.started_triad()
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, "Ban 1 of alice")

    def test_detail_is_never_cached(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        response = self.client.get(self.detail_url(session))
        self.assertIn('no-cache', response['Cache-Control'])


class SessionSecrecyViewTests(SessionViewTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.started_triad()
        self.pick(self.session, HOST, self.bob_decks[1])

    def poll(self, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(
            reverse('trade_secrets:session-poll', args=[self.session.code]),
            {'v': '-1', 'stage': 'stale'}, HTTP_HX_REQUEST='true')

    def assert_pending_pick_hidden(self, response):
        self.assertNotContains(response, 'data-locked')
        self.assertNotContains(response, 'banned')
        self.assertNotContains(response, 'Bans revealed')

    def test_owner_sees_their_locked_pick(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.detail_url(self.session))
        self.assertContains(response, 'data-locked')
        self.assertContains(response, 'Update pick')

    def test_opponent_sees_only_that_a_pick_is_locked(self):
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url(self.session))
        self.assert_pending_pick_hidden(response)
        self.assertContains(response, 'locked in')
        self.assert_pending_pick_hidden(self.poll(self.bob))

    def test_spectator_and_anonymous_never_see_pending_pick(self):
        self.assert_pending_pick_hidden(self.client.get(self.detail_url(self.session)))
        self.assert_pending_pick_hidden(self.poll())
        self.client.force_login(self.carol)
        self.assert_pending_pick_hidden(self.client.get(self.detail_url(self.session)))
        self.assert_pending_pick_hidden(self.poll(self.carol))

    def test_opponent_decks_are_hidden_until_both_submit(self):
        session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        session.submit_decks(HOST, self.alice, [deck.id for deck in self.alice_decks[:3]])
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url(session))
        self.assertNotContains(response, 'Alice Deck 1')
        self.assertContains(response, 'Hidden deck')

    def test_reveal_shows_both_picks(self):
        self.pick(self.session, GUEST, self.alice_decks[0])
        self.client.force_login(self.carol)
        response = self.client.get(self.detail_url(self.session))
        self.assertContains(response, 'Bans revealed')
        self.assertContains(response, 'Bob Deck 2')
        self.assertContains(response, 'Alice Deck 1')


class SessionPollViewTests(SessionViewTestCase):
    def poll(self, session, version, stage):
        return self.client.get(
            reverse('trade_secrets:session-poll', args=[session.code]),
            {'v': version, 'stage': stage}, HTTP_HX_REQUEST='true')

    def current_stage(self, session, user):
        return build_session_view(session, user).stage_key

    def test_unchanged_version_returns_no_content(self):
        session = self.started_triad()
        self.client.force_login(self.alice)
        response = self.poll(session, session.version, 'anything')
        self.assertEqual(response.status_code, 204)

    def test_same_stage_returns_overview_only(self):
        session = self.started_triad()
        self.client.force_login(self.alice)
        stage = self.current_stage(session, self.alice)
        version = session.version
        self.pick(session, GUEST, self.alice_decks[0])
        response = self.poll(session, version, stage)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Retarget', response)
        self.assertContains(response, 'id="ts-overview"')
        self.assertNotContains(response, 'id="ts-board"')

    def test_stage_change_returns_board(self):
        session = self.started_triad()
        self.client.force_login(self.alice)
        stage = self.current_stage(session, self.alice)
        version = session.version
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, GUEST, self.alice_decks[0])
        response = self.poll(session, version, stage)
        self.assertEqual(response['HX-Retarget'], '#ts-board')
        self.assertContains(response, 'id="ts-board"')

    def test_guest_joining_does_not_reset_hosts_deck_form(self):
        session = self.start_session(self.system_template('triad'), self.alice)
        stage = self.current_stage(session, self.alice)
        version = session.version
        session.join(self.bob)
        self.client.force_login(self.alice)
        response = self.poll(session, version, stage)
        self.assertNotIn('HX-Retarget', response)

    def test_finished_session_polls_slowly(self):
        session = self.start_session(self.system_template('triad-bo1'), self.alice, self.bob)
        self.submit_both(session, self.alice_decks[:3], self.bob_decks[:3])
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, GUEST, self.alice_decks[0])
        self.pick(session, HOST, self.alice_decks[1])
        self.pick(session, GUEST, self.bob_decks[1])
        self.client.force_login(self.alice)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, 'every 15000ms')
        self.assertContains(response, 'Copy results')

    def test_unknown_session_is_not_found(self):
        response = self.poll(Session(code='NOPE00'), 0, '')
        self.assertEqual(response.status_code, 404)


@patch.object(Deck, 'hydrate_from_master_vault', autospec=True, side_effect=fake_hydrate)
class DeckSubmissionViewTests(SessionViewTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.start_session(self.system_template('triad'), self.alice, self.bob)
        self.decks_url = reverse('trade_secrets:session-decks', args=[self.session.code])
        self.client.force_login(self.alice)

    def submitted_deck_ids(self, seat=HOST):
        return list(self.session.decks.filter(seat=seat).order_by('sort_order').values_list('deck_id', flat=True))

    def test_mixed_link_formats_create_decks_in_order(self, hydrate):
        new_ids = [uuid.uuid4() for _ in range(3)]
        text = (
            f'https://www.keyforgegame.com/deck-details/{new_ids[0]}\n'
            f'https://decksofkeyforge.com/decks/{new_ids[1]}, {new_ids[2]}')
        response = self.htmx_post(self.decks_url, {'source': 'links', 'deck_links': text})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.submitted_deck_ids(), new_ids)
        self.assertEqual(hydrate.call_count, 3)

    def test_known_decks_are_not_refetched(self, hydrate):
        text = '\n'.join(str(deck.id) for deck in self.alice_decks[:3])
        self.htmx_post(self.decks_url, {'source': 'links', 'deck_links': text})
        hydrate.assert_not_called()
        self.assertEqual(len(self.submitted_deck_ids()), 3)

    def test_wrong_count_garbage_and_duplicates_write_nothing(self, hydrate):
        deck_id = self.alice_decks[0].id
        for text, message in [
                (f'{deck_id}', 'exactly 3 decks'),
                (f'{deck_id} not-a-deck {self.alice_decks[1].id}', 'No deck found in: not-a-deck'),
                (f'{deck_id} {deck_id} {deck_id}', 'only be submitted once')]:
            response = self.htmx_post(self.decks_url, {'source': 'links', 'deck_links': text})
            self.assertContains(response, message)
        self.assertEqual(self.submitted_deck_ids(), [])

    def test_master_vault_failure_writes_nothing(self, hydrate):
        hydrate.side_effect = failing_hydrate
        text = ' '.join(str(uuid.uuid4()) for _ in range(3))
        response = self.htmx_post(self.decks_url, {'source': 'links', 'deck_links': text})
        self.assertContains(response, 'Could not fetch these decks from Master Vault')
        self.assertEqual(self.submitted_deck_ids(), [])

    def test_lineup_defaults_to_latest_version(self, hydrate):
        lineup = Lineup.objects.create(owner=self.alice, name='Triad Stack')
        old_version = LineupVersion.objects.create(lineup=lineup, name='v1', sort_order=1)
        latest_version = LineupVersion.objects.create(lineup=lineup, name='v2', sort_order=2)
        for sort_order, deck in enumerate(self.alice_decks[:3]):
            LineupVersionDeck.objects.create(version=old_version, deck=deck, sort_order=sort_order)
        for sort_order, deck in enumerate(self.alice_decks[3:6]):
            LineupVersionDeck.objects.create(version=latest_version, deck=deck, sort_order=sort_order)
        self.htmx_post(self.decks_url, {'source': 'lineup', 'lineup': lineup.pk})
        self.assertEqual(self.submitted_deck_ids(), [deck.id for deck in self.alice_decks[3:6]])
        self.assertEqual(self.session.decks.first().source_version, latest_version)

    def test_lineup_with_wrong_deck_count_is_rejected(self, hydrate):
        lineup = Lineup.objects.create(owner=self.alice, name='Too Small')
        version = LineupVersion.objects.create(lineup=lineup, name='v1')
        LineupVersionDeck.objects.create(version=version, deck=self.alice_decks[0])
        response = self.htmx_post(self.decks_url, {'source': 'lineup', 'lineup': lineup.pk, 'version': version.pk})
        self.assertContains(response, 'exactly 3 decks')
        self.assertEqual(self.submitted_deck_ids(), [])

    def test_other_users_lineup_is_rejected(self, hydrate):
        lineup = Lineup.objects.create(owner=self.bob, name='Not Yours')
        version = LineupVersion.objects.create(lineup=lineup, name='v1')
        for deck in self.bob_decks[:3]:
            LineupVersionDeck.objects.create(version=version, deck=deck)
        self.htmx_post(self.decks_url, {'source': 'lineup', 'lineup': lineup.pk, 'version': version.pk})
        self.assertEqual(self.submitted_deck_ids(), [])

    def test_lineup_versions_lists_only_own_versions(self, hydrate):
        own = Lineup.objects.create(owner=self.alice, name='Mine')
        LineupVersion.objects.create(lineup=own, name='My Version')
        theirs = Lineup.objects.create(owner=self.bob, name='Theirs')
        LineupVersion.objects.create(lineup=theirs, name='Their Version')
        url = reverse('trade_secrets:lineup-versions')
        self.assertContains(self.client.get(url, {'lineup': own.pk, 'count': 3}), 'My Version')
        self.assertNotContains(self.client.get(url, {'lineup': theirs.pk, 'count': 3}), 'Their Version')

    def test_lineup_preview_shows_own_version_decks(self, hydrate):
        own = Lineup.objects.create(owner=self.alice, name='Mine')
        own_version = LineupVersion.objects.create(lineup=own, name='v1')
        for sort_order, deck in enumerate(self.alice_decks[:3]):
            LineupVersionDeck.objects.create(version=own_version, deck=deck, sort_order=sort_order)
        theirs = Lineup.objects.create(owner=self.bob, name='Theirs')
        their_version = LineupVersion.objects.create(lineup=theirs, name='v1')
        LineupVersionDeck.objects.create(version=their_version, deck=self.bob_decks[0])
        url = reverse('trade_secrets:lineup-preview')
        response = self.client.get(url, {'version': own_version.pk})
        for deck in self.alice_decks[:3]:
            self.assertContains(response, deck.name)
        self.assertNotContains(self.client.get(url, {'version': their_version.pk}), 'Bob Deck 1')

    def test_lineup_endpoints_ignore_missing_or_invalid_ids(self, hydrate):
        for url, parameter in [
                (reverse('trade_secrets:lineup-preview'), 'version'),
                (reverse('trade_secrets:lineup-versions'), 'lineup')]:
            for value in ['', 'abc']:
                response = self.client.get(url, {parameter: value, 'count': 3})
                self.assertEqual(response.status_code, 200)

    def test_deck_form_loads_lineup_preview(self, hydrate):
        lineup = Lineup.objects.create(owner=self.alice, name='Mine')
        LineupVersion.objects.create(lineup=lineup, name='v1')
        response = self.client.get(self.detail_url(self.session))
        self.assertContains(response, reverse('trade_secrets:lineup-preview'))
        self.assertContains(response, 'id="ts-lineup-preview"')

    def test_spectator_cannot_submit_decks(self, hydrate):
        self.client.force_login(self.carol)
        text = ' '.join(str(deck.id) for deck in self.alice_decks[:3])
        response = self.client.post(self.decks_url, {'source': 'links', 'deck_links': text})
        self.assertEqual(response.status_code, 403)


class PickViewTests(SessionViewTestCase):
    def pick_url(self, session):
        return reverse('trade_secrets:session-pick', args=[session.code])

    def test_pick_locks_and_reveal_happens_on_second_pick(self):
        session = self.started_triad()
        self.client.force_login(self.alice)
        response = self.htmx_post(self.pick_url(session), {
            'step_order': 1, 'deck': [self.session_deck_id(session, self.bob_decks[0])]})
        self.assertContains(response, 'Update pick')
        self.client.force_login(self.bob)
        response = self.htmx_post(self.pick_url(session), {
            'step_order': 1, 'deck': [self.session_deck_id(session, self.alice_decks[0])]})
        self.assertContains(response, 'Bans revealed')
        session.refresh_from_db()
        self.assertEqual(session.revealed_step_count, 2)

    def test_stale_step_is_rejected_inline(self):
        session = self.started_triad()
        self.pick(session, HOST, self.bob_decks[0])
        self.pick(session, GUEST, self.alice_decks[0])
        self.client.force_login(self.alice)
        response = self.htmx_post(self.pick_url(session), {
            'step_order': 1, 'deck': [self.session_deck_id(session, self.bob_decks[1])]})
        self.assertContains(response, 'already revealed')

    def test_illegal_deck_is_rejected_inline(self):
        session = self.started_triad()
        self.client.force_login(self.alice)
        response = self.htmx_post(self.pick_url(session), {
            'step_order': 1, 'deck': [self.session_deck_id(session, self.alice_decks[0])]})
        self.assertContains(response, 'cannot be picked')
        self.assertIsNone(session.pending_submission_for(HOST))

    def test_non_player_cannot_pick(self):
        session = self.started_triad()
        self.client.force_login(self.carol)
        response = self.client.post(self.pick_url(session), {
            'step_order': 1, 'deck': [self.session_deck_id(session, self.alice_decks[0])]})
        self.assertEqual(response.status_code, 403)

    def test_non_htmx_pick_redirects(self):
        session = self.started_triad()
        self.client.force_login(self.alice)
        response = self.client.post(self.pick_url(session), {
            'step_order': 1, 'deck': [self.session_deck_id(session, self.bob_decks[0])]})
        self.assertRedirects(response, self.detail_url(session))


class ResultViewTests(SessionViewTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.started_triad()
        self.pick(self.session, HOST, self.bob_decks[2])
        self.pick(self.session, GUEST, self.alice_decks[2])
        self.pick(self.session, HOST, self.alice_decks[0])
        self.pick(self.session, GUEST, self.bob_decks[0])
        self.result_url = reverse('trade_secrets:session-result', args=[self.session.code, 2])

    def test_blocking_result_prompts_players(self):
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url(self.session))
        self.assertContains(response, 'Record game 1 to continue')
        self.assertContains(response, 'Record result')

    def test_result_form_warns_about_eligibility(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.result_url, HTTP_HX_REQUEST='true')
        self.assertContains(response, "can't be played again")
        self.assertNotContains(response, '<html')

    def test_recording_result_unblocks_and_returns_board(self):
        self.client.force_login(self.bob)
        response = self.htmx_post(self.result_url, {'winner_seat': HOST, 'host_score': 3, 'guest_score': 1})
        self.assertContains(response, 'id="ts-board"')
        self.assertContains(response, 'alice won')
        self.assertContains(response, 'Pick your deck for game 2')

    def test_invalid_result_retargets_dialog(self):
        self.client.force_login(self.bob)
        response = self.htmx_post(self.result_url, {'winner_seat': 'nobody'})
        self.assertEqual(response['HX-Retarget'], '#ts-dialog')
        self.assertContains(response, 'ts-result-form')

    def test_scores_must_be_entered_for_both_players_or_neither(self):
        self.client.force_login(self.bob)
        response = self.htmx_post(self.result_url, {'winner_seat': HOST, 'host_score': 3})
        self.assertEqual(response['HX-Retarget'], '#ts-dialog')
        self.assertContains(response, 'Enter a score for both players')
        self.assertFalse(self.session.results.exists())

    def test_result_without_scores_is_allowed(self):
        self.client.force_login(self.bob)
        self.htmx_post(self.result_url, {'winner_seat': GUEST})
        result = self.session.results.get()
        self.assertEqual((result.winner_seat, result.host_score, result.guest_score), (GUEST, None, None))

    def test_history_shows_score_line_in_seat_order(self):
        self.session.record_result(self.alice, 2, GUEST, 1, 3)
        self.client.force_login(self.alice)
        response = self.client.get(self.detail_url(self.session))
        self.assertContains(response, 'alice 1 – 3 bob')

    def test_result_dialog_uses_player_cards_and_prefills_scores(self):
        self.session.record_result(self.alice, 2, HOST, 3, 2)
        self.client.force_login(self.bob)
        response = self.client.get(self.result_url, HTTP_HX_REQUEST='true')
        self.assertContains(response, 'class="report-player"', count=2)
        self.assertContains(response, 'name="host_score" id="id_host_score" value="3"')
        self.assertContains(response, 'value="host" class="report-player__radio" required checked')

    def test_spectator_cannot_record_result(self):
        self.client.force_login(self.carol)
        response = self.client.post(self.result_url, {'winner_seat': HOST})
        self.assertEqual(response.status_code, 403)

    def test_reset_clears_latest_result(self):
        self.session.record_result(self.alice, 2, HOST)
        self.client.force_login(self.bob)
        response = self.htmx_post(
            reverse('trade_secrets:session-result-reset', args=[self.session.code, 2]), {})
        self.assertContains(response, 'Record game 1 to continue')
        self.assertFalse(self.session.results.exists())

    def test_unrevealed_game_result_is_not_found(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('trade_secrets:session-result', args=[self.session.code, 3]))
        self.assertEqual(response.status_code, 404)


class TemplateViewTests(SessionViewTestCase):
    builder_url = reverse_lazy('trade_secrets:template-create')

    def builder_post(self, steps, builder_action='', name='My Format'):
        data = {'name': name, 'description': '', 'builder_action': builder_action}
        for index, (action, quantity, rule) in enumerate(steps):
            data[f'steps-{index}-action'] = action
            data[f'steps-{index}-quantity'] = quantity
            data[f'steps-{index}-rule'] = rule
        return self.htmx_post(self.builder_url, data)

    def test_builder_requires_login(self):
        response = self.client.get(self.builder_url)
        self.assertEqual(response.status_code, 302)

    def test_builder_starts_with_a_valid_template(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.builder_url)
        self.assertContains(response, 'Decks per player')
        self.assertNotContains(response, 'is-invalid')

    def test_builder_actions_add_move_and_remove(self):
        self.client.force_login(self.alice)
        steps = [('submit', 4, ''), ('ban', 1, ''), ('play', 1, 'ineligible')]
        response = self.builder_post(steps, 'add:steal')
        self.assertContains(response, 'name="steps-3-action" value="steal"')
        response = self.builder_post(steps + [('steal', 1, '')], 'up:3')
        self.assertContains(response, 'name="steps-2-action" value="steal"')
        response = self.builder_post(steps, 'remove:1')
        self.assertNotContains(response, 'value="ban"')

    def test_invalid_template_shows_step_error_and_cannot_save(self):
        self.client.force_login(self.alice)
        response = self.builder_post([('submit', 3, ''), ('ban', 3, ''), ('play', 1, 'ineligible')], 'save')
        self.assertContains(response, 'Step 3 (Play)')
        self.assertContains(response, 'disabled>Save template')
        self.assertFalse(SessionTemplate.objects.filter(owner=self.alice).exists())

    def test_valid_template_saves_and_redirects(self):
        self.client.force_login(self.alice)
        response = self.builder_post(
            [('submit', 4, ''), ('ban', 1, ''), ('safe', 1, ''), ('steal', 1, ''), ('play', 1, 'eligible')],
            'save', name='Tetrad-ish')
        template = SessionTemplate.objects.get(owner=self.alice)
        self.assertEqual(response['HX-Redirect'], reverse('trade_secrets:template-detail', args=[template.code]))
        self.assertEqual([spec.action for spec in template.step_specs], ['submit', 'ban', 'safe', 'steal', 'play'])
        self.assertEqual(template.step_specs[-1].played_deck_rule, 'eligible')

    def test_save_requires_name(self):
        self.client.force_login(self.alice)
        self.builder_post([('submit', 3, ''), ('play', 1, 'ineligible')], 'save', name='')
        self.assertFalse(SessionTemplate.objects.filter(owner=self.alice).exists())

    def test_other_users_template_is_hidden(self):
        template = self.make_template(self.bob, 'submit:3', 'play')
        self.client.force_login(self.alice)
        response = self.client.get(reverse('trade_secrets:template-detail', args=[template.code]))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse('trade_secrets:session-create'), {'template_code': template.code})
        self.assertEqual(response.status_code, 403)

    def test_archive_unarchive_and_delete(self):
        template = self.make_template(self.alice, 'submit:3', 'play')
        self.client.force_login(self.alice)
        delete_url = reverse('trade_secrets:template-delete', args=[template.code])
        archive_url = reverse('trade_secrets:template-archive', args=[template.code])
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        self.client.post(archive_url)
        template.refresh_from_db()
        self.assertTrue(template.is_archived)
        self.assertNotContains(self.client.get(reverse('trade_secrets:home')), f'value="{template.code}"')
        self.client.post(archive_url)
        template.refresh_from_db()
        self.assertFalse(template.is_archived)
        self.client.post(archive_url)
        self.client.post(delete_url)
        self.assertFalse(SessionTemplate.objects.filter(pk=template.pk).exists())

    def test_used_template_cannot_be_deleted(self):
        template = self.make_template(self.alice, 'submit:3', 'play')
        self.start_session(template, self.alice)
        template.archive()
        self.client.force_login(self.alice)
        response = self.client.post(reverse('trade_secrets:template-delete', args=[template.code]))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse('trade_secrets:template-detail', args=[template.code]))
        self.assertContains(response, "can't be deleted because 1 session uses it")

    def test_archived_template_cannot_start_session(self):
        template = self.make_template(self.alice, 'submit:3', 'play')
        template.archive()
        self.client.force_login(self.alice)
        response = self.client.post(reverse('trade_secrets:session-create'), {'template_code': template.code})
        self.assertEqual(response.status_code, 403)

    def test_system_template_cannot_be_archived(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('trade_secrets:template-archive', args=[self.system_template('triad').code]))
        self.assertEqual(response.status_code, 403)

    def test_start_session_redirects_to_session(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('trade_secrets:session-create'), {'template_code': self.system_template('hexad').code})
        session = Session.objects.get(host=self.alice)
        self.assertRedirects(response, self.detail_url(session))


class HexadBo1Mixin:
    def start_hexad_bo1(self):
        template = self.make_template(
            self.alice, 'submit:6', 'ban:1', 'safe:1', 'ban:1', 'play', 'play', 'play', 'ban_matchup',
            name='Hexad Bo1')
        session = self.start_session(template, self.alice, self.bob)
        self.submit_both(session, self.alice_decks, self.bob_decks)
        for host_deck, guest_deck in [
                (self.bob_decks[0], self.alice_decks[0]),
                (self.alice_decks[1], self.bob_decks[1]),
                (self.bob_decks[2], self.alice_decks[2]),
                (self.alice_decks[3], self.bob_decks[3]),
                (self.alice_decks[4], self.bob_decks[4]),
                (self.alice_decks[5], self.bob_decks[5])]:
            self.pick(session, HOST, host_deck)
            self.pick(session, GUEST, guest_deck)
        return session

    def ban_matchups(self, session, host_order, guest_order):
        session.submit_picks(HOST, self.alice, 7, [host_order])
        session.submit_picks(GUEST, self.bob, 7, [guest_order])


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class MatchupBanSessionTests(HexadBo1Mixin, SessionViewTestCase):
    def test_matchup_ban_reveals_and_completes(self):
        session = self.start_hexad_bo1()
        self.ban_matchups(session, 4, 6)
        self.assertEqual(session.revealed_step_count, 8)
        self.assertEqual(session.banned_matchup_orders(), {4, 6})

    def test_banned_matchup_cannot_have_result(self):
        session = self.start_hexad_bo1()
        self.ban_matchups(session, 4, 6)
        with self.assertRaises(ValidationError):
            session.record_result(self.alice, 4, HOST)
        session.record_result(self.alice, 5, GUEST, 3, 2)
        self.assertEqual(session.results.get().step.order, 5)

    def test_same_ban_leaves_two_recordable_matchups(self):
        session = self.start_hexad_bo1()
        self.ban_matchups(session, 5, 5)
        self.assertTrue(session.can_record_result(4))
        self.assertTrue(session.can_record_result(6))
        self.assertFalse(session.can_record_result(5))

    def test_matchup_ban_rejects_deck_ids_and_unplayed_steps(self):
        session = self.start_hexad_bo1()
        with self.assertRaises(ValidationError):
            session.submit_picks(HOST, self.alice, 7, [1])
        with self.assertRaises(ValidationError):
            session.submit_picks(HOST, self.alice, 7, [4, 5])

    def test_ban_page_offers_matchups_and_labels_them(self):
        session = self.start_hexad_bo1()
        self.client.force_login(self.alice)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, 'Ban 1 matchup')
        self.assertContains(response, 'ts-matchup')
        self.assertContains(response, 'Matchup 3')
        self.assertNotContains(response, 'Game 1')

    def test_matchup_ban_pick_view_and_finished_prompt(self):
        session = self.start_hexad_bo1()
        self.client.force_login(self.alice)
        self.htmx_post(reverse('trade_secrets:session-pick', args=[session.code]), {'step_order': 7, 'deck': [4]})
        self.assertEqual(session.pending_submission_for(HOST).picked_ids(), (4,))
        self.client.force_login(self.bob)
        response = self.htmx_post(
            reverse('trade_secrets:session-pick', args=[session.code]), {'step_order': 7, 'deck': [6]})
        self.assertContains(response, 'Matchup bans revealed')
        self.assertContains(response, 'Play matchup 2 and record the result')
        self.assertContains(response, 'Banned')

    def test_pending_matchup_ban_stays_secret(self):
        session = self.start_hexad_bo1()
        session.submit_picks(HOST, self.alice, 7, [5])
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url(session))
        self.assertNotContains(response, 'data-locked')
        self.assertNotContains(response, 'Matchup bans revealed')

    def test_builder_offers_ban_matchup(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('trade_secrets:template-create'))
        self.assertContains(response, 'value="add:ban_matchup"')


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class MatchupReviewRegressionTests(HexadBo1Mixin, SessionViewTestCase):
    def start_matchups_then_games(self):
        template = self.make_template(
            self.alice, 'submit:6', 'play', 'play', 'play', 'ban_matchup', 'play:losing_only', 'play',
            name='Matchups then games')
        session = self.start_session(template, self.alice, self.bob)
        self.submit_both(session, self.alice_decks, self.bob_decks)
        for index in range(3):
            self.pick(session, HOST, self.alice_decks[index])
            self.pick(session, GUEST, self.bob_decks[index])
        session.submit_picks(HOST, self.alice, 4, [1])
        session.submit_picks(GUEST, self.bob, 4, [3])
        return session

    def test_matchup_results_wait_for_the_ban(self):
        template = self.make_template(
            self.alice, 'submit:6', 'ban:1', 'safe:1', 'ban:1', 'play', 'play', 'play', 'ban_matchup')
        session = self.start_session(template, self.alice, self.bob)
        self.submit_both(session, self.alice_decks, self.bob_decks)
        for host_deck, guest_deck in [
                (self.bob_decks[0], self.alice_decks[0]),
                (self.alice_decks[1], self.bob_decks[1]),
                (self.bob_decks[2], self.alice_decks[2]),
                (self.alice_decks[3], self.bob_decks[3])]:
            self.pick(session, HOST, host_deck)
            self.pick(session, GUEST, guest_deck)
        self.assertFalse(session.can_record_result(4))
        with self.assertRaises(ValidationError):
            session.record_result(self.alice, 4, HOST)
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(self.detail_url(session)), 'Not played yet')

    def test_finished_prompt_clears_once_any_unbanned_matchup_has_a_result(self):
        session = self.start_hexad_bo1()
        self.ban_matchups(session, 5, 5)
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(self.detail_url(session)), 'Play matchup 1 or matchup 3')
        session.record_result(self.alice, 4, HOST)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, 'All done')
        self.assertNotContains(response, 'Play matchup 3')

    def test_banned_matchup_cannot_be_reset(self):
        session = self.start_hexad_bo1()
        self.ban_matchups(session, 4, 6)
        self.assertFalse(session.can_reset_result(4))
        with self.assertRaises(ValidationError):
            session.reset_result(4)

    def test_game_results_do_not_lock_matchup_results(self):
        session = self.start_matchups_then_games()
        self.pick(session, HOST, self.alice_decks[3])
        self.pick(session, GUEST, self.bob_decks[3])
        session.record_result(self.alice, 5, HOST)
        session.record_result(self.alice, 2, GUEST, 1, 3)
        self.assertTrue(session.can_reset_result(2))
        self.assertTrue(session.can_record_result(5))
        session.record_result(self.bob, 2, HOST, 3, 1)
        self.assertEqual(session.results.get(step__order=2).winner_seat, HOST)

    def test_play_after_matchup_ban_is_a_game(self):
        session = self.start_matchups_then_games()
        self.client.force_login(self.alice)
        response = self.client.get(self.detail_url(session))
        self.assertContains(response, 'Pick your deck for game 4')
        self.assertContains(response, 'Matchup 2')

    def test_result_form_names_the_matchup(self):
        session = self.start_hexad_bo1()
        self.ban_matchups(session, 4, 6)
        self.client.force_login(self.alice)
        response = self.client.get(
            reverse('trade_secrets:session-result', args=[session.code, 5]), HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Matchup 2')
        self.assertNotContains(response, 'Game 2')

    def test_finished_matchup_session_renders_for_every_viewer(self):
        session = self.start_hexad_bo1()
        self.ban_matchups(session, 4, 6)
        for user in (self.alice, self.bob, self.carol, None):
            self.client.logout()
            if user:
                self.client.force_login(user)
            response = self.client.get(self.detail_url(session))
            self.assertContains(response, 'Matchup bans revealed')

    def test_opponent_does_not_see_pending_matchup_ban_selected(self):
        session = self.start_hexad_bo1()
        session.submit_picks(HOST, self.alice, 7, [5])
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url(session))
        self.assertNotContains(response, 'is-selected')

    def test_builder_adds_and_saves_ban_matchup(self):
        self.client.force_login(self.alice)
        steps = [('submit', 6, ''), ('play', 1, 'ineligible'), ('play', 1, 'ineligible'), ('play', 1, 'ineligible')]
        data = {'name': 'Bo1', 'description': '', 'builder_action': 'add:ban_matchup'}
        for index, (action, quantity, rule) in enumerate(steps):
            data.update({f'steps-{index}-action': action, f'steps-{index}-quantity': quantity,
                         f'steps-{index}-rule': rule})
        response = self.htmx_post(reverse('trade_secrets:template-create'), data)
        self.assertContains(response, 'value="ban_matchup"')
        self.assertContains(response, 'Unbanned matchups: at least 1')
        data.update({'steps-4-action': 'ban_matchup', 'steps-4-quantity': 1, 'builder_action': 'save'})
        self.htmx_post(reverse('trade_secrets:template-create'), data)
        template = SessionTemplate.objects.get(owner=self.alice, name='Bo1')
        self.assertEqual(template.step_specs[-1].action, 'ban_matchup')


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class ScoreMigrationTests(TradeSecretsTestMixin, TestCase):
    def test_text_scores_split_by_winner(self):
        migration = importlib.import_module('trade_secrets.migrations.0005_per_player_scores')
        match = migration.TEXT_SCORE_PATTERN.match(' 3 - 1 ')
        self.assertEqual(match.groups(), ('3', '1'))
        self.assertIsNone(migration.TEXT_SCORE_PATTERN.match('3 keys to 1'))


@override_settings(STORAGES=SIMPLE_STORAGES, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class TemplateVisibilityTests(SessionViewTestCase):
    def setUp(self):
        super().setUp()
        self.template = self.make_template(self.alice, 'submit:3', 'ban:1', 'play', name='Shared Format')
        self.detail_url_for_template = reverse('trade_secrets:template-detail', args=[self.template.code])
        self.visibility_url = reverse('trade_secrets:template-visibility', args=[self.template.code])

    def start_as(self, user):
        self.client.force_login(user)
        return self.client.post(reverse('trade_secrets:session-create'), {'template_code': self.template.code})

    def test_templates_start_private(self):
        self.assertEqual(self.template.visibility, SessionTemplate.Visibility.PRIVATE)
        self.assertEqual(self.start_as(self.bob).status_code, 403)

    def test_public_template_can_be_opened_and_started_by_link(self):
        self.template.set_visibility(SessionTemplate.Visibility.PUBLIC)
        self.client.force_login(self.bob)
        response = self.client.get(self.detail_url_for_template)
        self.assertContains(response, 'Shared by alice')
        self.assertNotContains(response, 'ts-sharing')
        response = self.start_as(self.bob)
        session = Session.objects.get(host=self.bob)
        self.assertRedirects(response, self.detail_url(session))

    def test_public_templates_are_not_listed_for_others(self):
        self.template.set_visibility(SessionTemplate.Visibility.PUBLIC)
        self.client.force_login(self.bob)
        self.assertNotContains(self.client.get(reverse('trade_secrets:home')), 'Shared Format')

    def test_anonymous_visitor_is_sent_to_log_in_for_public_templates(self):
        self.template.set_visibility(SessionTemplate.Visibility.PUBLIC)
        response = self.client.get(self.detail_url_for_template)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_private_template_is_hidden_from_others(self):
        self.assertEqual(self.client.get(self.detail_url_for_template).status_code, 404)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.detail_url_for_template).status_code, 404)

    def test_owner_toggles_visibility_and_sees_share_link(self):
        self.client.force_login(self.alice)
        self.client.post(self.visibility_url, {'visibility': 'public'})
        self.template.refresh_from_db()
        self.assertTrue(self.template.is_public)
        response = self.client.get(self.detail_url_for_template)
        self.assertContains(response, 'Copy link')
        self.assertContains(response, f'http://testserver{self.detail_url_for_template}')
        self.client.post(self.visibility_url, {'visibility': 'private'})
        self.template.refresh_from_db()
        self.assertFalse(self.template.is_public)

    def test_invalid_visibility_is_ignored(self):
        self.client.force_login(self.alice)
        self.client.post(self.visibility_url, {'visibility': 'secret'})
        self.template.refresh_from_db()
        self.assertEqual(self.template.visibility, SessionTemplate.Visibility.PRIVATE)

    def test_only_owner_can_change_visibility(self):
        self.template.set_visibility(SessionTemplate.Visibility.PUBLIC)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(self.visibility_url, {'visibility': 'private'}).status_code, 403)
        system_url = reverse('trade_secrets:template-visibility', args=[self.system_template('triad').code])
        self.assertEqual(self.client.post(system_url, {'visibility': 'private'}).status_code, 403)

    def test_making_private_keeps_existing_sessions_working(self):
        self.template.set_visibility(SessionTemplate.Visibility.PUBLIC)
        self.start_as(self.bob)
        session = Session.objects.get(host=self.bob)
        session.join(self.carol)
        self.template.set_visibility(SessionTemplate.Visibility.PRIVATE)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.detail_url(session)).status_code, 200)
        self.submit_both(session, self.bob_decks[:3], self.alice_decks[:3])
        self.assertEqual(session.revealed_step_count, 1)
        self.assertEqual(self.start_as(self.bob).status_code, 403)

    def test_archived_public_template_cannot_start_sessions(self):
        self.template.set_visibility(SessionTemplate.Visibility.PUBLIC)
        self.template.archive()
        self.assertEqual(self.start_as(self.bob).status_code, 403)
