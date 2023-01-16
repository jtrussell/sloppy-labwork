def partition(lst, predicate):
    true_by_pred = []
    false_by_pred = []
    for elem in lst:
        if predicate(elem):
            true_by_pred.append(elem)
        else:
            false_by_pred.append(elem)
    return [true_by_pred, false_by_pred]
