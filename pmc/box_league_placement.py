import math
from collections import deque, namedtuple


MINIMUM_PLAYERS_PER_BOX = 2

CompletedBox = namedtuple('CompletedBox', ['level', 'ordinal', 'ranked_member_ids'])
ProposedBox = namedtuple('ProposedBox', ['level', 'ordinal', 'member_ids'])
RankedPlayer = namedtuple('RankedPlayer', ['member_id', 'rank', 'played', 'wins', 'ties', 'losses', 'points'])

ARRIVED_BY_RELEGATION = 0
STAYED_ON_LEVEL = 1
ARRIVED_BY_PROMOTION = 2
NEWLY_JOINED = 3

POINTS_FOR_WIN = 2
POINTS_FOR_TIE = 1


def linear_tier_box_counts(total_boxes):
    return [1] * total_boxes


def pyramid_tier_box_counts(total_boxes):
    pending_shapes = deque([[1]])
    while pending_shapes:
        shape = pending_shapes.popleft()
        if sum(shape) == total_boxes:
            return shape
        for next_count in (shape[-1] * 2, shape[-1]):
            if sum(shape) + next_count <= total_boxes:
                pending_shapes.append(shape + [next_count])
    return linear_tier_box_counts(total_boxes)


def is_valid_tier_shape(tier_box_counts):
    if not tier_box_counts or tier_box_counts[0] != 1:
        return False
    return all(
        lower in (upper, upper * 2)
        for upper, lower in zip(tier_box_counts, tier_box_counts[1:])
    )


def relegations_from_box(relegation_count, boxes_on_level, boxes_on_level_below):
    return math.ceil(relegation_count * boxes_on_level_below / boxes_on_level)


def movement_for_box(rank_count, level, boxes_per_level, promotion_count, relegation_count):
    bottom_level = len(boxes_per_level)
    promoted_count = min(promotion_count, rank_count) if level > 1 else 0
    relegated_count = 0
    if level < bottom_level:
        box_winner_stays = rank_count - 1
        relegated_count = max(0, min(
            relegations_from_box(relegation_count, boxes_per_level[level - 1], boxes_per_level[level]),
            rank_count - promoted_count,
            box_winner_stays,
        ))
    return promoted_count, relegated_count


def boxes_per_level_of(completed_boxes):
    bottom_level = max(box.level for box in completed_boxes)
    return [
        sum(1 for box in completed_boxes if box.level == level)
        for level in range(1, bottom_level + 1)
    ]


def next_session_order(completed_boxes, promotion_count, relegation_count, departing_member_ids=(), joining_member_ids=()):
    departing = set(departing_member_ids)
    priorities = []
    bottom_level = 1
    if completed_boxes:
        boxes_per_level = boxes_per_level_of(completed_boxes)
        bottom_level = len(boxes_per_level)
        for box in completed_boxes:
            remaining_ids = [member_id for member_id in box.ranked_member_ids if member_id not in departing]
            promoted_count, relegated_count = movement_for_box(
                len(remaining_ids), box.level, boxes_per_level, promotion_count, relegation_count)
            for rank_index, member_id in enumerate(remaining_ids):
                if rank_index < promoted_count:
                    target_level, arrival = box.level - 1, ARRIVED_BY_PROMOTION
                elif rank_index >= len(remaining_ids) - relegated_count:
                    target_level, arrival = box.level + 1, ARRIVED_BY_RELEGATION
                else:
                    target_level, arrival = box.level, STAYED_ON_LEVEL
                priorities.append((target_level, arrival, rank_index, box.ordinal, member_id))

    already_placed = {priority[-1] for priority in priorities}
    newcomers = [
        member_id for member_id in joining_member_ids
        if member_id not in already_placed and member_id not in departing
    ]
    for join_index, member_id in enumerate(newcomers):
        priorities.append((bottom_level, NEWLY_JOINED, join_index, 0, member_id))

    return [priority[-1] for priority in sorted(priorities)]


def usable_tier_box_counts(tier_box_counts, player_count):
    usable_box_total = max(1, min(sum(tier_box_counts), player_count // MINIMUM_PLAYERS_PER_BOX))
    usable_counts = []
    for box_count in tier_box_counts:
        boxes_on_level = min(box_count, usable_box_total - sum(usable_counts))
        if boxes_on_level == 0:
            break
        usable_counts.append(boxes_on_level)
    return usable_counts


def even_box_sizes(player_count, box_count):
    base_size, boxes_with_extra = divmod(player_count, box_count)
    return [base_size + (1 if index < boxes_with_extra else 0) for index in range(box_count)]


def snake_box_indices(box_count):
    forward = list(range(box_count))
    while True:
        yield from forward
        yield from reversed(forward)


def deal_in_snake_order(member_ids, capacities):
    boxes = [[] for _ in capacities]
    pending_ids = list(member_ids)
    for box_index in snake_box_indices(len(capacities)):
        if not pending_ids:
            break
        if len(boxes[box_index]) < capacities[box_index]:
            boxes[box_index].append(pending_ids.pop(0))
    return boxes


def place_into_boxes(ordered_member_ids, tier_box_counts):
    if not ordered_member_ids:
        return []
    usable_counts = usable_tier_box_counts(tier_box_counts, len(ordered_member_ids))
    sizes = even_box_sizes(len(ordered_member_ids), sum(usable_counts))
    proposed_boxes = []
    placed_count = 0
    sized_box_count = 0
    for level, boxes_on_level in enumerate(usable_counts, start=1):
        capacities = sizes[sized_box_count:sized_box_count + boxes_on_level]
        level_member_ids = ordered_member_ids[placed_count:placed_count + sum(capacities)]
        for ordinal, member_ids in enumerate(deal_in_snake_order(level_member_ids, capacities), start=1):
            proposed_boxes.append(ProposedBox(level, ordinal, member_ids))
        sized_box_count += boxes_on_level
        placed_count += sum(capacities)
    return proposed_boxes


def rank_box(member_ids, results, tiebreak_key):
    current_ids = set(member_ids)
    counted_results = [
        result for result in results
        if result[0] in current_ids and result[1] in current_ids
    ]
    totals = {member_id: {'played': 0, 'wins': 0, 'ties': 0, 'losses': 0} for member_id in member_ids}
    for player_one_id, player_two_id, winner_id in counted_results:
        for member_id in (player_one_id, player_two_id):
            totals[member_id]['played'] += 1
            if winner_id is None:
                totals[member_id]['ties'] += 1
            elif winner_id == member_id:
                totals[member_id]['wins'] += 1
            else:
                totals[member_id]['losses'] += 1

    def points_for(member_id):
        return totals[member_id]['wins'] * POINTS_FOR_WIN + totals[member_id]['ties'] * POINTS_FOR_TIE

    def head_to_head_points(member_id):
        tied_ids = {other_id for other_id in member_ids if points_for(other_id) == points_for(member_id)}
        points = 0
        for player_one_id, player_two_id, winner_id in counted_results:
            if member_id not in (player_one_id, player_two_id):
                continue
            if player_one_id not in tied_ids or player_two_id not in tied_ids:
                continue
            if winner_id is None:
                points += POINTS_FOR_TIE
            elif winner_id == member_id:
                points += POINTS_FOR_WIN
        return points

    ordered_ids = sorted(
        member_ids,
        key=lambda member_id: (-points_for(member_id), -head_to_head_points(member_id), tiebreak_key(member_id)),
    )
    return [
        RankedPlayer(
            member_id=member_id,
            rank=rank,
            points=points_for(member_id),
            **totals[member_id],
        )
        for rank, member_id in enumerate(ordered_ids, start=1)
    ]
