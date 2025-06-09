def partition(lst, predicate):
    true_by_pred = []
    false_by_pred = []
    for elem in lst:
        if predicate(elem):
            true_by_pred.append(elem)
        else:
            false_by_pred.append(elem)
    return [true_by_pred, false_by_pred]

def find_first_index(lst, condition):
    return next((i for i, x in enumerate(lst) if condition(x)), -1)

def find_last_index(lst, condition):
    return next((len(lst) - 1 - i for i, x in enumerate(reversed(lst)) if condition(x)), -1)

def get_rank_display_with_ties(first_index, last_index):
    return f"{'T' if first_index != last_index else ''}{first_index + 1}"