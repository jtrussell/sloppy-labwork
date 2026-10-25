from django.test import SimpleTestCase

from .engine import (
    Action, DeckStatus, Phase, PlayedDeckRule, PoolDeck, Seat, StepSpec,
    choices_for, deck_status, game_label, games_won, step_label, wave_detail, ineligible_reason, missing_result_step, unbanned_matchup_orders,
    phase, replay, required_pick_count, results_summary_lines, seats_needing_picks,
    simulate_template_steps, validate_picks, validate_template_steps,
)

HOST = Seat.HOST
GUEST = Seat.GUEST
GUEST_ID_OFFSET = 100


def make_steps(*descriptions):
    steps = []
    for order, description in enumerate(descriptions):
        action, _, setting = description.partition(':')
        if action == Action.PLAY:
            steps.append(StepSpec(order, action, 1, setting or PlayedDeckRule.INELIGIBLE))
        else:
            steps.append(StepSpec(order, action, int(setting or 1)))
    return steps


def host_deck(number):
    return number


def guest_deck(number):
    return GUEST_ID_OFFSET + number


def make_pool(host_count, guest_count=None):
    guest_count = host_count if guest_count is None else guest_count
    return (
        [PoolDeck(host_deck(n), HOST) for n in range(1, host_count + 1)]
        + [PoolDeck(guest_deck(n), GUEST) for n in range(1, guest_count + 1)]
    )


class Match:
    def __init__(self, *step_descriptions, host_count=None, guest_count=None):
        self.steps = make_steps(*step_descriptions)
        submit_quantity = self.steps[0].quantity
        self.pool = make_pool(host_count or submit_quantity, guest_count or host_count or submit_quantity)
        self.revealed_picks = {}
        self.winners = {}
        self.revealed_count = 1

    @property
    def state(self):
        return replay(self.steps, self.pool, self.revealed_count, self.revealed_picks, self.winners)

    @property
    def current_step(self):
        return self.state.current_step

    def reveal(self, host=(), guest=()):
        step = self.current_step
        self.revealed_picks[step.order] = {HOST: tuple(host), GUEST: tuple(guest)}
        self.revealed_count += 1
        return self

    def record_winner(self, game_order, seat):
        self.winners[game_order] = seat
        return self

    def deck(self, deck_id):
        return self.state.decks[deck_id]

    def choices(self, seat):
        state = self.state
        return choices_for(state, state.current_step, seat)

    def status(self, deck_id):
        return deck_status(self.deck(deck_id))


class BanTests(SimpleTestCase):
    def test_ban_one_of_three_bans_only_that_opponent_deck(self):
        match = Match('submit:3', 'ban:1', 'play')
        self.assertEqual(match.choices(HOST), [guest_deck(1), guest_deck(2), guest_deck(3)])
        match.reveal(host=[guest_deck(2)], guest=[host_deck(1)])
        self.assertEqual(match.status(guest_deck(2)), DeckStatus.BANNED)
        self.assertEqual(match.status(host_deck(1)), DeckStatus.BANNED)
        self.assertEqual(match.status(guest_deck(1)), DeckStatus.AVAILABLE)

    def test_ban_choices_never_include_own_decks(self):
        match = Match('submit:3', 'ban:1', 'play')
        self.assertTrue(all(deck_id > GUEST_ID_OFFSET for deck_id in match.choices(HOST)))
        self.assertTrue(all(deck_id < GUEST_ID_OFFSET for deck_id in match.choices(GUEST)))

    def test_ban_two_of_five_bans_both(self):
        match = Match('submit:5', 'ban:2', 'play')
        self.assertEqual(required_pick_count(match.state, match.current_step, HOST), 2)
        match.reveal(host=[guest_deck(1), guest_deck(5)], guest=[host_deck(2), host_deck(3)])
        banned = [deck.id for deck in match.state.decks.values() if deck.is_banned]
        self.assertCountEqual(banned, [guest_deck(1), guest_deck(5), host_deck(2), host_deck(3)])

    def test_ban_three_leaves_remaining_decks_for_play(self):
        match = Match('submit:6', 'ban:3', 'play')
        match.reveal(host=[guest_deck(1), guest_deck(2), guest_deck(3)],
                     guest=[host_deck(4), host_deck(5), host_deck(6)])
        self.assertEqual(match.choices(HOST), [host_deck(1), host_deck(2), host_deck(3)])
        self.assertEqual(match.choices(GUEST), [guest_deck(4), guest_deck(5), guest_deck(6)])

    def test_banned_deck_is_excluded_from_later_steps(self):
        match = Match('submit:4', 'ban:1', 'safe:1', 'ban:1', 'steal:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertNotIn(host_deck(1), match.choices(HOST))
        match.reveal(host=[host_deck(2)], guest=[guest_deck(2)])
        self.assertNotIn(guest_deck(1), match.choices(HOST))
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        self.assertEqual(match.choices(HOST), [guest_deck(4)])
        match.reveal(host=[guest_deck(4)], guest=[host_deck(4)])
        self.assertNotIn(host_deck(1), match.choices(HOST))
        self.assertNotIn(host_deck(3), match.choices(HOST))

    def test_ban_picks_are_validated(self):
        match = Match('submit:3', 'ban:1', 'play')
        state, step = match.state, match.current_step
        self.assertEqual(validate_picks(state, step, HOST, [guest_deck(1)]), [])
        self.assertTrue(validate_picks(state, step, HOST, [host_deck(1)]))
        self.assertTrue(validate_picks(state, step, HOST, []))
        self.assertTrue(validate_picks(state, step, HOST, [guest_deck(1), guest_deck(2)]))
        self.assertTrue(validate_picks(state, step, HOST, [guest_deck(1), guest_deck(1)]))

    def test_already_banned_deck_cannot_be_banned_again(self):
        match = Match('submit:3', 'ban:1', 'ban:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertTrue(validate_picks(match.state, match.current_step, HOST, [guest_deck(1)]))


class SafeTests(SimpleTestCase):
    def test_safed_deck_cannot_be_banned_or_stolen_but_can_be_played(self):
        match = Match('submit:4', 'safe:1', 'ban:1', 'steal:1', 'play')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(match.status(host_deck(1)), DeckStatus.SAFED)
        self.assertNotIn(host_deck(1), match.choices(GUEST))
        match.reveal(host=[guest_deck(2)], guest=[host_deck(2)])
        self.assertNotIn(host_deck(1), match.choices(GUEST))
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        self.assertIn(host_deck(1), match.choices(HOST))

    def test_safe_two_protects_both(self):
        match = Match('submit:5', 'safe:2', 'ban:2', 'play')
        match.reveal(host=[host_deck(1), host_deck(2)], guest=[guest_deck(1), guest_deck(2)])
        self.assertEqual(match.choices(GUEST), [host_deck(3), host_deck(4), host_deck(5)])

    def test_safe_three_leaves_only_unsafed_targets(self):
        match = Match('submit:4', 'safe:3', 'ban:1', 'play')
        match.reveal(host=[host_deck(1), host_deck(2), host_deck(3)],
                     guest=[guest_deck(2), guest_deck(3), guest_deck(4)])
        self.assertEqual(match.choices(GUEST), [host_deck(4)])
        self.assertEqual(match.choices(HOST), [guest_deck(1)])

    def test_safe_choices_are_own_unsafed_decks(self):
        match = Match('submit:3', 'safe:1', 'safe:1', 'play')
        self.assertEqual(match.choices(HOST), [host_deck(1), host_deck(2), host_deck(3)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(match.choices(HOST), [host_deck(2), host_deck(3)])
        self.assertTrue(validate_picks(match.state, match.current_step, HOST, [host_deck(1)]))
        self.assertTrue(validate_picks(match.state, match.current_step, HOST, [guest_deck(2)]))


class StealTests(SimpleTestCase):
    def test_steal_one_resolves_simultaneously_against_pre_step_lineups(self):
        match = Match('submit:3', 'steal:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertEqual(match.deck(guest_deck(1)).holder_seat, HOST)
        self.assertEqual(match.deck(host_deck(1)).holder_seat, GUEST)
        self.assertEqual(len(match.state.decks_held_by(HOST)), 3)
        self.assertEqual(len(match.state.decks_held_by(GUEST)), 3)
        self.assertEqual(match.status(guest_deck(1)), DeckStatus.STOLEN)

    def test_steal_two_moves_four_decks(self):
        match = Match('submit:5', 'steal:2', 'play')
        match.reveal(host=[guest_deck(1), guest_deck(2)], guest=[host_deck(4), host_deck(5)])
        self.assertEqual(
            sorted(deck.id for deck in match.state.decks_held_by(HOST)),
            [host_deck(1), host_deck(2), host_deck(3), guest_deck(1), guest_deck(2)])
        self.assertEqual(len(match.state.decks_held_by(GUEST)), 5)

    def test_steal_three_of_four(self):
        match = Match('submit:4', 'steal:3', 'play')
        match.reveal(host=[guest_deck(1), guest_deck(2), guest_deck(3)],
                     guest=[host_deck(1), host_deck(2), host_deck(3)])
        self.assertEqual(match.choices(HOST), [host_deck(4), guest_deck(1), guest_deck(2), guest_deck(3)])

    def test_stolen_deck_is_playable_by_new_holder(self):
        match = Match('submit:3', 'steal:1', 'play')
        match.reveal(host=[guest_deck(3)], guest=[host_deck(2)])
        self.assertIn(guest_deck(3), match.choices(HOST))
        self.assertNotIn(host_deck(2), match.choices(HOST))

    def test_steal_quantity_clamps_when_opponent_has_fewer_open_decks(self):
        match = Match('submit:4', 'safe:1', 'safe:1', 'steal:3', 'play')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        match.reveal(host=[host_deck(2)], guest=[])
        state, step = match.state, match.current_step
        self.assertEqual(required_pick_count(state, step, GUEST), 2)
        self.assertEqual(required_pick_count(state, step, HOST), 3)

    def test_safed_banned_and_spent_decks_are_not_steal_targets(self):
        match = Match('submit:4', 'ban:1', 'safe:1', 'play', 'steal:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        match.reveal(host=[host_deck(2)], guest=[guest_deck(2)])
        match.reveal(host=[host_deck(3)], guest=[guest_deck(3)])
        self.assertEqual(match.choices(GUEST), [host_deck(4)])
        self.assertEqual(match.choices(HOST), [guest_deck(4)])

    def test_stolen_deck_can_be_stolen_back(self):
        match = Match('submit:3', 'steal:1', 'steal:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertIn(guest_deck(1), match.choices(GUEST))
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(match.deck(guest_deck(1)).holder_seat, GUEST)
        self.assertEqual(match.deck(host_deck(1)).holder_seat, HOST)
        self.assertEqual(match.deck(guest_deck(1)).stolen_at_orders, [1, 2])

    def test_stolen_deck_can_be_safed_by_new_holder(self):
        match = Match('submit:3', 'steal:1', 'safe:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertIn(guest_deck(1), match.choices(HOST))


class PlayTests(SimpleTestCase):
    def test_ineligible_rule_spends_played_deck(self):
        match = Match('submit:3', 'play:ineligible', 'play:ineligible')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(match.choices(HOST), [host_deck(2), host_deck(3)])
        self.assertEqual(match.status(host_deck(1)), DeckStatus.INELIGIBLE)
        self.assertEqual(ineligible_reason(match.state, match.deck(host_deck(1))), 'Played in game 1')

    def test_eligible_rule_keeps_played_deck(self):
        match = Match('submit:2', 'play:eligible', 'play:eligible')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(match.choices(HOST), [host_deck(1), host_deck(2)])
        self.assertEqual(match.status(host_deck(1)), DeckStatus.PLAYED)

    def test_losing_only_spends_winning_deck(self):
        match = Match('submit:3', 'play:losing_only', 'play:losing_only')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)]).record_winner(1, HOST)
        self.assertNotIn(host_deck(1), match.choices(HOST))
        self.assertIn(guest_deck(1), match.choices(GUEST))
        self.assertEqual(ineligible_reason(match.state, match.deck(host_deck(1))), 'Won game 1')

    def test_losing_only_blocks_until_result_recorded(self):
        match = Match('submit:3', 'play:losing_only', 'play:losing_only')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(missing_result_step(match.state).order, 1)
        self.assertEqual(phase(match.state, has_guest=True), Phase.AWAITING_RESULT)
        match.record_winner(1, GUEST)
        self.assertIsNone(missing_result_step(match.state))
        self.assertEqual(phase(match.state, has_guest=True), Phase.SELECTING)

    def test_last_losing_only_step_never_blocks(self):
        match = Match('submit:3', 'play:losing_only')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertIsNone(missing_result_step(match.state))
        self.assertEqual(phase(match.state, has_guest=True), Phase.COMPLETE)

    def test_other_rules_never_block(self):
        for rule in (PlayedDeckRule.ELIGIBLE, PlayedDeckRule.INELIGIBLE):
            match = Match('submit:3', f'play:{rule}', f'play:{rule}')
            match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
            self.assertEqual(phase(match.state, has_guest=True), Phase.SELECTING)

    def test_changing_an_earlier_result_changes_only_future_eligibility(self):
        match = Match('submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only')
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)]).record_winner(2, HOST)
        match.reveal(host=[host_deck(2)], guest=[guest_deck(1)]).record_winner(3, GUEST)
        self.assertEqual(match.choices(HOST), [host_deck(2)])
        match.record_winner(2, GUEST)
        self.assertEqual(match.choices(HOST), [host_deck(1), host_deck(2)])
        self.assertEqual(match.deck(host_deck(2)).played_at_orders, [3])

    def test_triad_two_nothing_concludes(self):
        match = Match('submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only')
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)]).record_winner(2, HOST)
        match.reveal(host=[host_deck(2)], guest=[guest_deck(1)]).record_winner(3, HOST)
        self.assertEqual(match.choices(HOST), [])
        self.assertEqual(phase(match.state, has_guest=True), Phase.CONCLUDED)
        self.assertEqual(games_won(match.state), {HOST: 2, GUEST: 0})

    def test_triad_split_goes_to_third_game(self):
        match = Match('submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only')
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)]).record_winner(2, HOST)
        match.reveal(host=[host_deck(2)], guest=[guest_deck(1)]).record_winner(3, GUEST)
        self.assertEqual(phase(match.state, has_guest=True), Phase.SELECTING)
        self.assertEqual(match.choices(HOST), [host_deck(2)])
        self.assertEqual(match.choices(GUEST), [guest_deck(2)])

    def test_spent_decks_are_not_ban_safe_or_steal_targets(self):
        match = Match('submit:4', 'play:ineligible', 'ban:1', 'safe:1', 'steal:1', 'play')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertNotIn(guest_deck(1), match.choices(HOST))
        match.reveal(host=[guest_deck(2)], guest=[host_deck(2)])
        self.assertEqual(match.choices(HOST), [host_deck(3), host_deck(4)])


class PhaseAndClampTests(SimpleTestCase):
    def test_waiting_for_guest(self):
        self.assertEqual(phase(Match('submit:3', 'play').state, has_guest=False), Phase.WAITING_FOR_GUEST)

    def test_submitting_decks(self):
        match = Match('submit:3', 'play')
        match.revealed_count = 0
        self.assertEqual(phase(match.state, has_guest=True), Phase.SUBMITTING_DECKS)

    def test_template_without_play_completes(self):
        match = Match('submit:3', 'ban:1')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertEqual(phase(match.state, has_guest=True), Phase.COMPLETE)

    def test_required_pick_count_is_clamped_to_choices(self):
        match = Match('submit:3', 'safe:2', 'ban:2', 'play')
        match.reveal(host=[host_deck(1), host_deck(2)], guest=[guest_deck(1)])
        state, step = match.state, match.current_step
        self.assertEqual(required_pick_count(state, step, GUEST), 1)
        self.assertEqual(required_pick_count(state, step, HOST), 2)

    def test_seat_with_no_choices_does_not_need_to_pick(self):
        match = Match('submit:2', 'safe:2', 'ban:1', 'play')
        match.reveal(host=[host_deck(1), host_deck(2)], guest=[guest_deck(1)])
        state, step = match.state, match.current_step
        self.assertEqual(seats_needing_picks(state, step), [HOST])

    def test_step_with_no_choices_for_anyone_needs_no_picks(self):
        match = Match('submit:2', 'safe:2', 'ban:1', 'play')
        match.reveal(host=[host_deck(1), host_deck(2)], guest=[guest_deck(1), guest_deck(2)])
        self.assertEqual(seats_needing_picks(match.state, match.current_step), [])

    def test_empty_pick_is_valid_when_nothing_is_eligible(self):
        match = Match('submit:2', 'safe:2', 'ban:1', 'play')
        match.reveal(host=[host_deck(1), host_deck(2)], guest=[guest_deck(1)])
        self.assertEqual(validate_picks(match.state, match.current_step, GUEST, []), [])


class StatusPriorityTests(SimpleTestCase):
    def test_banned_beats_everything(self):
        match = Match('submit:3', 'play:eligible', 'ban:1', 'play')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertEqual(match.status(guest_deck(1)), DeckStatus.BANNED)

    def test_spent_beats_safed(self):
        match = Match('submit:3', 'safe:1', 'play')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(match.status(host_deck(1)), DeckStatus.INELIGIBLE)

    def test_safed_beats_stolen(self):
        match = Match('submit:3', 'steal:1', 'safe:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertEqual(match.status(guest_deck(1)), DeckStatus.SAFED)

    def test_stolen_beats_played(self):
        match = Match('submit:3', 'steal:1', 'play:eligible')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        self.assertEqual(match.status(guest_deck(1)), DeckStatus.STOLEN)


class TemplateValidationTests(SimpleTestCase):
    def assertValid(self, *descriptions):
        self.assertEqual(validate_template_steps(make_steps(*descriptions)), [])

    def assertInvalid(self, *descriptions):
        errors = validate_template_steps(make_steps(*descriptions))
        self.assertTrue(errors)
        return errors

    def test_system_formats_are_valid(self):
        self.assertValid('submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only')
        self.assertValid('submit:3', 'ban:1', 'play:ineligible')
        self.assertValid('submit:6', 'ban:1', 'safe:1', 'ban:1', 'play', 'play', 'play')

    def test_steal_formats_are_valid(self):
        self.assertValid('submit:4', 'ban:1', 'safe:1', 'steal:1', 'play', 'play', 'play')
        self.assertValid('submit:4', 'safe:1', 'steal:3')
        self.assertValid('submit:8', 'ban:2', 'safe:2', 'ban:2', 'play', 'play', 'play')

    def test_templates_without_play_are_valid(self):
        self.assertValid('submit:3')
        self.assertValid('submit:3', 'ban:2')

    def test_pool_shortages_are_rejected(self):
        self.assertInvalid('submit:3', 'ban:3', 'play')
        self.assertInvalid('submit:3', 'safe:2', 'ban:2')
        self.assertInvalid('submit:4', 'safe:1', 'steal:4')
        self.assertInvalid('submit:3', 'ban:1', 'play', 'play', 'play')

    def test_ban_may_take_every_deck_when_nothing_plays_after(self):
        self.assertValid('submit:3', 'ban:3')

    def test_replayable_decks_allow_many_games(self):
        self.assertValid('submit:2', 'play:eligible', 'play:eligible', 'play:eligible', 'play:eligible', 'play:eligible')
        self.assertValid('submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only',
                         'play:losing_only', 'play:losing_only')

    def test_safed_decks_count_toward_play(self):
        self.assertValid('submit:2', 'safe:2', 'play', 'play')
        self.assertInvalid('submit:2', 'safe:2', 'play', 'play', 'play')

    def test_structural_errors(self):
        self.assertTrue(validate_template_steps([]))
        self.assertInvalid('ban:1', 'play')
        self.assertInvalid('submit:3', 'submit:3', 'play')
        self.assertInvalid('submit:0', 'play')
        self.assertInvalid('submit:13', 'play')
        self.assertInvalid('submit:3', 'ban:0', 'play')
        self.assertInvalid('submit:12', 'ban:13')
        self.assertInvalid(*(['submit:12'] + ['play:eligible'] * 20))
        self.assertTrue(validate_template_steps([StepSpec(0, 'submit', 3), StepSpec(1, 'play', 2)]))
        self.assertTrue(validate_template_steps([StepSpec(0, 'submit', 3), StepSpec(1, 'dance', 1)]))
        self.assertTrue(validate_template_steps([StepSpec(0, 'submit', 3), StepSpec(1, 'play', 1, 'maybe')]))

    def test_error_names_step_and_action(self):
        self.assertEqual(
            self.assertInvalid('submit:3', 'ban:1', 'ban:2', 'play'),
            ['Step 4 (Game 1): needs 1 eligible deck(s) but at most 0 may remain.'])
        self.assertEqual(
            self.assertInvalid('submit:3', 'safe:1', 'ban:3'),
            ['Step 3 (Ban): needs 3 eligible deck(s) but at most 2 may remain.'])

    def test_simulation_trace_reports_pool_sizes(self):
        traces = simulate_template_steps(make_steps('submit:6', 'ban:1', 'safe:1', 'ban:1', 'play', 'play', 'play'))
        self.assertTrue(all(not trace.open_range_varies for trace in traces))
        self.assertEqual([(t.fewest_open, t.fewest_safed) for t in traces],
                         [(6, 0), (5, 0), (4, 1), (3, 1), (3, 0), (2, 0), (1, 0)])
        self.assertTrue(all(not trace.error for trace in traces))


class SummaryTests(SimpleTestCase):
    def test_summary_contains_only_revealed_information(self):
        match = Match('submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only')
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)]).record_winner(2, HOST)
        deck_names = {deck.id: f'Deck {deck.id}' for deck in match.pool}
        lines = results_summary_lines(
            match.state, 'Triad', 'ABC123', {HOST: 'Alice', GUEST: 'Bob'},
            deck_names, {2: (3, 1)}, 'https://example.com/trade-secrets/ABC123/')
        self.assertEqual(lines, [
            'Trade Secrets: Triad (ABC123)',
            'Alice vs Bob',
            'Alice decks: Deck 1; Deck 2; Deck 3',
            'Bob decks: Deck 101; Deck 102; Deck 103',
            'Ban: Alice banned Deck 103; Bob banned Deck 3',
            'Game 1: Deck 1 (Alice) vs Deck 101 (Bob) - Alice won, Alice 3 – 1 Bob',
            'Games won: Alice 1, Bob 0',
            'https://example.com/trade-secrets/ABC123/',
        ])


class ReviewRegressionTests(SimpleTestCase):
    def test_deck_stolen_back_is_no_longer_marked_stolen(self):
        match = Match('submit:3', 'steal:1', 'steal:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        self.assertEqual(match.status(guest_deck(1)), DeckStatus.AVAILABLE)
        self.assertEqual(match.status(host_deck(1)), DeckStatus.AVAILABLE)

    def test_ineligible_reason_names_the_game_that_spent_the_deck(self):
        match = Match('submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only')
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)]).record_winner(2, GUEST)
        match.reveal(host=[host_deck(1)], guest=[guest_deck(2)])
        match.record_winner(2, HOST)
        self.assertEqual(ineligible_reason(match.state, match.deck(host_deck(1))), 'Won game 1')

    def test_steal_shortage_message(self):
        self.assertEqual(
            validate_template_steps(make_steps('submit:4', 'safe:2', 'steal:3')),
            ['Step 3 (Steal): needs 3 eligible deck(s) but at most 2 may remain.'])

    def test_play_shortage_after_safed_decks_are_used(self):
        self.assertEqual(
            validate_template_steps(make_steps('submit:2', 'safe:1', 'ban:1', 'play', 'play')),
            ['Step 5 (Game 2): needs 1 eligible deck(s) but at most 0 may remain.'])

    def test_mixed_play_rules_in_one_template(self):
        match = Match('submit:2', 'play:eligible', 'play:losing_only', 'play:ineligible')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(2)]).record_winner(2, HOST)
        self.assertEqual(match.choices(HOST), [host_deck(2)])
        self.assertEqual(match.choices(GUEST), [guest_deck(1), guest_deck(2)])

    def test_summary_covers_safe_steal_empty_picks_and_unrecorded_games(self):
        match = Match('submit:2', 'safe:1', 'steal:1', 'play')
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        match.reveal(host=[guest_deck(2)], guest=[])
        match.reveal(host=[host_deck(1)], guest=[guest_deck(1)])
        deck_names = {deck.id: f'Deck {deck.id}' for deck in match.pool}
        lines = results_summary_lines(
            match.state, 'Custom', 'XYZ789', {HOST: 'Alice', GUEST: 'Bob'}, deck_names, {}, 'url')
        self.assertIn('Safe: Alice safed Deck 1; Bob safed Deck 101', lines)
        self.assertIn('Steal: Alice stole Deck 102; Bob stole nothing', lines)
        self.assertIn('Game 1: Deck 1 (Alice) vs Deck 101 (Bob) - result not recorded', lines)
        self.assertIn('Games won: Alice 0, Bob 0', lines)

    def test_losing_only_games_show_an_open_deck_range(self):
        traces = simulate_template_steps(make_steps(
            'submit:3', 'ban:1', 'play:losing_only', 'play:losing_only', 'play:losing_only'))
        self.assertEqual(
            [(trace.fewest_open, trace.most_open) for trace in traces],
            [(3, 3), (2, 2), (1, 2), (0, 2), (0, 2)])
        self.assertTrue(all(not trace.error for trace in traces))

    def test_steps_after_losing_only_games_must_fit_the_fewest_open_decks(self):
        self.assertEqual(
            validate_template_steps(make_steps('submit:3', 'ban:1', 'play:losing_only', 'ban:2')),
            ['Step 4 (Ban 2): needs 2 eligible deck(s) but as few as 1 may remain.'])
        self.assertEqual(
            validate_template_steps(make_steps('submit:3', 'ban:1', 'play:losing_only', 'ban:1')), [])


HEXAD_BO1 = ('submit:6', 'ban:1', 'safe:1', 'ban:1', 'play', 'play', 'play', 'ban_matchup')


class MatchupBanTests(SimpleTestCase):
    def play_three_matchups(self, match):
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        match.reveal(host=[host_deck(2)], guest=[guest_deck(2)])
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        for number in (4, 5, 6):
            match.reveal(host=[host_deck(number)], guest=[guest_deck(number)])
        return match

    def test_choices_are_revealed_unbanned_matchups_for_both_players(self):
        match = self.play_three_matchups(Match(*HEXAD_BO1))
        self.assertEqual(match.choices(HOST), [4, 5, 6])
        self.assertEqual(match.choices(GUEST), [4, 5, 6])
        self.assertEqual(required_pick_count(match.state, match.current_step, HOST), 1)

    def test_separate_bans_leave_one_matchup(self):
        match = self.play_three_matchups(Match(*HEXAD_BO1))
        match.reveal(host=[4], guest=[6])
        self.assertEqual(match.state.banned_matchup_orders, {4, 6})
        self.assertEqual(unbanned_matchup_orders(match.state), [5])
        self.assertEqual(phase(match.state, has_guest=True), Phase.COMPLETE)

    def test_same_ban_leaves_two_matchups(self):
        match = self.play_three_matchups(Match(*HEXAD_BO1))
        match.reveal(host=[5], guest=[5])
        self.assertEqual(unbanned_matchup_orders(match.state), [4, 6])

    def test_matchup_picks_are_validated(self):
        match = self.play_three_matchups(Match(*HEXAD_BO1))
        state, step = match.state, match.current_step
        self.assertEqual(validate_picks(state, step, HOST, [5]), [])
        self.assertTrue(validate_picks(state, step, HOST, [1]))
        self.assertTrue(validate_picks(state, step, HOST, [4, 5]))
        self.assertIn('That matchup cannot be picked for this step.', validate_picks(state, step, HOST, [99]))

    def test_banned_matchups_do_not_count_as_games_won(self):
        match = self.play_three_matchups(Match(*HEXAD_BO1))
        match.record_winner(4, HOST).record_winner(5, GUEST)
        match.reveal(host=[4], guest=[6])
        self.assertEqual(games_won(match.state), {HOST: 0, GUEST: 1})

    def test_play_steps_before_a_matchup_ban_are_matchups(self):
        steps = make_steps(*HEXAD_BO1)
        self.assertEqual(game_label(steps, steps[4]), 'Matchup 1')
        self.assertEqual(game_label(steps, steps[6]), 'Matchup 3')
        hexad = make_steps('submit:6', 'ban:1', 'safe:1', 'ban:1', 'play', 'play', 'play')
        self.assertEqual(game_label(hexad, hexad[4]), 'Game 1')

    def test_play_after_the_last_matchup_ban_is_a_game(self):
        steps = make_steps('submit:6', 'play', 'play', 'play', 'ban_matchup', 'play')
        self.assertEqual(game_label(steps, steps[1]), 'Matchup 1')
        self.assertEqual(game_label(steps, steps[5]), 'Game 4')

    def test_summary_marks_banned_matchups(self):
        match = self.play_three_matchups(Match(*HEXAD_BO1))
        match.reveal(host=[4], guest=[6])
        match.record_winner(5, GUEST)
        deck_names = {deck.id: f'Deck {deck.id}' for deck in match.pool}
        lines = results_summary_lines(
            match.state, 'Hexad Bo1', 'ts_ABC123', {HOST: 'Alice', GUEST: 'Bob'}, deck_names, {}, 'url')
        self.assertIn('Matchup 1: Deck 4 (Alice) vs Deck 104 (Bob) - banned', lines)
        self.assertIn('Matchup 2: Deck 5 (Alice) vs Deck 105 (Bob) - Bob won', lines)
        self.assertIn('Ban matchup: Alice banned Matchup 1; Bob banned Matchup 3', lines)
        self.assertIn('Games won: Alice 0, Bob 1', lines)


class MatchupBanValidationTests(SimpleTestCase):
    def test_hexad_bo1_is_valid(self):
        self.assertEqual(validate_template_steps(make_steps(*HEXAD_BO1)), [])

    def test_needs_three_unbanned_matchups(self):
        self.assertEqual(
            validate_template_steps(make_steps('submit:6', 'play', 'play', 'ban_matchup')),
            ['Step 4 (Ban matchup): needs at least 3 unbanned matchups but as few as 2 may remain.'])
        self.assertTrue(validate_template_steps(make_steps('submit:3', 'ban_matchup')))

    def test_consecutive_bans_assume_separate_picks(self):
        self.assertEqual(validate_template_steps(make_steps(
            'submit:6', 'play', 'play', 'play', 'play', 'play', 'ban_matchup', 'ban_matchup')), [])
        self.assertTrue(validate_template_steps(make_steps(
            'submit:6', 'play', 'play', 'play', 'play', 'ban_matchup', 'ban_matchup')))

    def test_rejected_after_only_losing_decks(self):
        errors = validate_template_steps(make_steps(
            'submit:6', 'play:losing_only', 'play', 'play', 'ban_matchup'))
        self.assertEqual(len(errors), 1)
        self.assertIn('Only losing decks', errors[0])

    def test_ban_matchup_quantity_is_always_one(self):
        self.assertTrue(validate_template_steps(
            [StepSpec(0, 'submit', 3), StepSpec(1, 'play'), StepSpec(2, 'play'), StepSpec(3, 'play'),
             StepSpec(4, 'ban_matchup', 2)]))

    def test_trace_counts_matchups(self):
        traces = simulate_template_steps(make_steps(*HEXAD_BO1))
        self.assertEqual([trace.fewest_matchups for trace in traces], [0, 0, 0, 0, 1, 2, 3, 1])


class WaveLabelTests(SimpleTestCase):
    def test_waves_are_numbered_only_when_repeated(self):
        hexad = make_steps('submit:6', 'ban:1', 'safe:1', 'ban:1', 'play', 'play', 'play')
        self.assertEqual(
            [step_label(hexad, step) for step in hexad],
            ['Submit 6', 'Ban 1', 'Safe', 'Ban 2', 'Game 1', 'Game 2', 'Game 3'])
        triad = make_steps('submit:3', 'ban:1', 'play')
        self.assertEqual(step_label(triad, triad[1]), 'Ban')

    def test_multiple_matchup_bans_are_numbered(self):
        steps = make_steps('submit:6', 'play', 'play', 'play', 'play', 'play', 'ban_matchup', 'ban_matchup')
        self.assertEqual(step_label(steps, steps[6]), 'Ban matchup 1')
        self.assertEqual(step_label(steps, steps[7]), 'Ban matchup 2')

    def test_wave_detail_only_for_multiple_decks(self):
        steps = make_steps('submit:6', 'ban:2', 'safe:1', 'steal:3', 'play')
        self.assertEqual([wave_detail(step) for step in steps], ['', '2 decks banned', '', '3 decks stolen', ''])

    def test_summary_heading_includes_wave_detail(self):
        match = Match('submit:5', 'ban:2', 'ban:1', 'play')
        match.reveal(host=[guest_deck(1), guest_deck(2)], guest=[host_deck(1), host_deck(2)])
        deck_names = {deck.id: f'Deck {deck.id}' for deck in match.pool}
        lines = results_summary_lines(match.state, 'Custom', 'ts_X', {HOST: 'Alice', GUEST: 'Bob'}, deck_names, {}, 'url')
        self.assertIn('Ban 1 (2 decks banned): Alice banned Deck 101; Deck 102; Bob banned Deck 1; Deck 2', lines)

    def test_engine_records_wave_orders(self):
        match = Match('submit:4', 'ban:1', 'safe:1', 'ban:1', 'play')
        match.reveal(host=[guest_deck(1)], guest=[host_deck(1)])
        match.reveal(host=[host_deck(2)], guest=[guest_deck(2)])
        match.reveal(host=[guest_deck(3)], guest=[host_deck(3)])
        self.assertEqual(match.deck(guest_deck(1)).banned_at_order, 1)
        self.assertEqual(match.deck(guest_deck(3)).banned_at_order, 3)
        self.assertEqual(match.deck(host_deck(2)).safed_at_order, 2)
