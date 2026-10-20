from django.test import SimpleTestCase

from .box_league_placement import (
    CompletedBox, is_valid_tier_shape, linear_tier_box_counts, movement_for_box, next_session_order,
    place_into_boxes, pyramid_tier_box_counts, rank_box, relegations_from_box,
)


class TierShapeTests(SimpleTestCase):
    def test_linear_shape_has_one_box_per_tier(self):
        self.assertEqual(linear_tier_box_counts(3), [1, 1, 1])

    def test_pyramid_shapes_use_the_fewest_tiers(self):
        self.assertEqual(pyramid_tier_box_counts(1), [1])
        self.assertEqual(pyramid_tier_box_counts(3), [1, 2])
        self.assertEqual(pyramid_tier_box_counts(4), [1, 1, 2])
        self.assertEqual(pyramid_tier_box_counts(5), [1, 2, 2])
        self.assertEqual(pyramid_tier_box_counts(6), [1, 1, 2, 2])
        self.assertEqual(pyramid_tier_box_counts(7), [1, 2, 4])

    def test_every_pyramid_preset_is_a_valid_shape(self):
        for total_boxes in range(1, 40):
            shape = pyramid_tier_box_counts(total_boxes)
            self.assertEqual(sum(shape), total_boxes)
            self.assertTrue(is_valid_tier_shape(shape))

    def test_shape_validation(self):
        self.assertTrue(is_valid_tier_shape([1, 1, 2, 4, 4]))
        self.assertFalse(is_valid_tier_shape([2, 2]))
        self.assertFalse(is_valid_tier_shape([1, 3]))
        self.assertFalse(is_valid_tier_shape([1, 2, 1]))
        self.assertFalse(is_valid_tier_shape([]))

    def test_doubling_boundary_doubles_relegations(self):
        self.assertEqual(relegations_from_box(1, 1, 1), 1)
        self.assertEqual(relegations_from_box(1, 1, 2), 2)
        self.assertEqual(relegations_from_box(2, 2, 4), 4)


class NextSessionOrderTests(SimpleTestCase):
    def test_first_session_uses_join_order(self):
        self.assertEqual(next_session_order([], 1, 1, joining_member_ids=[3, 1, 2]), [3, 1, 2])

    def test_linear_league_swaps_one_up_and_one_down(self):
        completed = [
            CompletedBox(1, 1, [1, 2, 3]),
            CompletedBox(2, 1, [4, 5, 6]),
        ]
        order = next_session_order(completed, 1, 1)
        self.assertEqual(order[:3], [1, 2, 4])
        self.assertEqual(order[3:], [3, 5, 6])

    def test_relegated_players_rank_ahead_of_stayers_in_their_new_tier(self):
        completed = [
            CompletedBox(1, 1, [1, 2, 3]),
            CompletedBox(2, 1, [4, 5, 6]),
            CompletedBox(3, 1, [7, 8, 9]),
        ]
        order = next_session_order(completed, 1, 1)
        self.assertEqual(order, [1, 2, 4, 3, 5, 7, 6, 8, 9])

    def test_doubling_boundary_sends_two_down_and_one_up_from_each_lower_box(self):
        completed = [
            CompletedBox(1, 1, [1, 2, 3, 4]),
            CompletedBox(2, 1, [5, 6, 7]),
            CompletedBox(2, 2, [8, 9, 10]),
        ]
        order = next_session_order(completed, 1, 1)
        self.assertEqual(set(order[:4]), {1, 2, 5, 8})
        self.assertEqual(set(order[4:]), {3, 4, 6, 7, 9, 10})

    def test_departing_players_are_dropped_and_joiners_start_at_the_bottom(self):
        completed = [
            CompletedBox(1, 1, [1, 2, 3]),
            CompletedBox(2, 1, [4, 5, 6]),
        ]
        order = next_session_order(completed, 1, 1, departing_member_ids=[2], joining_member_ids=[7, 8])
        self.assertNotIn(2, order)
        self.assertEqual(order[-2:], [7, 8])

    def test_small_top_box_keeps_its_winner(self):
        completed = [
            CompletedBox(1, 1, [1, 2]),
            CompletedBox(2, 1, [3, 4]),
            CompletedBox(2, 2, [5, 6]),
        ]
        self.assertEqual(movement_for_box(2, 1, [1, 2], 1, 1), (0, 1))
        order = next_session_order(completed, 1, 1)
        self.assertEqual(order[0], 1)
        self.assertIn(order.index(2), range(3, 6))

    def test_two_player_middle_box_sends_winner_up_and_loser_down(self):
        self.assertEqual(movement_for_box(2, 2, [1, 1, 1], 1, 1), (1, 1))

    def test_movement_never_exceeds_the_box(self):
        completed = [
            CompletedBox(1, 1, [1, 2]),
            CompletedBox(2, 1, [3, 4]),
        ]
        order = next_session_order(completed, 3, 3)
        self.assertEqual(sorted(order), [1, 2, 3, 4])


class PlaceIntoBoxesTests(SimpleTestCase):
    def test_no_players_means_no_boxes(self):
        self.assertEqual(place_into_boxes([], [1, 1]), [])

    def test_linear_placement_fills_top_down_evenly(self):
        boxes = place_into_boxes(list(range(1, 8)), [1, 1])
        self.assertEqual([box.member_ids for box in boxes], [[1, 2, 3, 4], [5, 6, 7]])
        self.assertEqual([(box.level, box.ordinal) for box in boxes], [(1, 1), (2, 1)])

    def test_pyramid_tier_is_snake_dealt(self):
        boxes = place_into_boxes(list(range(1, 10)), [1, 2])
        self.assertEqual(boxes[0].member_ids, [1, 2, 3])
        self.assertEqual(boxes[1].member_ids, [4, 7, 8])
        self.assertEqual(boxes[2].member_ids, [5, 6, 9])

    def test_trailing_boxes_are_left_out_when_players_run_short(self):
        boxes = place_into_boxes([1, 2, 3, 4, 5], [1, 2, 2])
        self.assertEqual(len(boxes), 2)
        self.assertEqual([box.level for box in boxes], [1, 2])
        self.assertTrue(all(len(box.member_ids) >= 2 for box in boxes))

    def test_a_single_player_still_gets_a_box(self):
        self.assertEqual(place_into_boxes([1], [1, 1]), [place_into_boxes([1], [1])[0]])


class RankBoxTests(SimpleTestCase):
    def rank(self, member_ids, results):
        return [player.member_id for player in rank_box(member_ids, results, lambda member_id: member_id)]

    def test_points_order_wins_ties_and_losses(self):
        ranked = rank_box([1, 2, 3], [(1, 2, 1), (1, 3, None), (2, 3, 3)], lambda member_id: member_id)
        self.assertEqual([player.member_id for player in ranked], [1, 3, 2])
        self.assertEqual([player.points for player in ranked], [3, 3, 0])
        self.assertEqual((ranked[0].wins, ranked[0].ties, ranked[0].losses, ranked[0].played), (1, 1, 0, 2))

    def test_two_way_tie_broken_by_head_to_head(self):
        results = [(1, 2, 2), (1, 3, 1), (2, 3, 3)]
        self.assertEqual(self.rank([1, 2, 3], results), [1, 2, 3])
        results = [(1, 2, 2), (1, 3, 1), (2, 3, 3), (1, 4, 1), (2, 4, 2)]
        self.assertEqual(self.rank([1, 2, 3, 4], results)[:2], [2, 1])

    def test_three_way_tie_uses_mini_league_then_tiebreak(self):
        results = [(1, 2, 1), (2, 3, 2), (3, 1, 3)]
        self.assertEqual(self.rank([3, 1, 2], results), [1, 2, 3])

    def test_tiebreak_key_is_used_when_everything_else_ties(self):
        ranked = rank_box([1, 2], [], lambda member_id: -member_id)
        self.assertEqual([player.member_id for player in ranked], [2, 1])

    def test_results_with_players_outside_the_box_are_ignored(self):
        ranked = rank_box([1, 2], [(1, 9, 1), (2, 1, 2)], lambda member_id: member_id)
        self.assertEqual([player.member_id for player in ranked], [2, 1])
        self.assertEqual(ranked[1].played, 1)
