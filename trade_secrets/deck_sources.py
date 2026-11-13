from django.db.models import Count

from lineups.models import Lineup

from .forms import DeckLineupForm, DeckLinksForm

SOURCE_LINKS = 'links'
SOURCE_LINEUP = 'lineup'


def own_lineups(user):
    return list(Lineup.objects.filter(owner=user).order_by('name'))


def versions_with_deck_counts(lineup):
    if lineup is None:
        return []
    return list(lineup.versions.annotate(deck_count=Count('version_decks')).order_by('-sort_order'))


def build_deck_source_form(data, user, required_count):
    if data.get('source', SOURCE_LINKS) == SOURCE_LINEUP:
        return DeckLineupForm(data, user=user, required_count=required_count)
    return DeckLinksForm(data, required_count=required_count)


def get_deck_source_errors(form):
    return [error for errors in form.errors.values() for error in errors]


def parse_submitted_id(form, field_name):
    try:
        return int(form[field_name].value())
    except (TypeError, ValueError):
        return None


def without_browser_required_validation(form):
    form.use_required_attribute = False
    return form


def build_deck_source_context(user, required_count, submitted_form=None):
    lineups = own_lineups(user)
    submitted_lineup_form = submitted_form if isinstance(submitted_form, DeckLineupForm) else None
    submitted_links_form = submitted_form if isinstance(submitted_form, DeckLinksForm) else None

    selected_lineup = lineups[0] if lineups else None
    selected_version_id = None
    if submitted_lineup_form is not None:
        submitted_lineup_id = parse_submitted_id(submitted_lineup_form, 'lineup')
        selected_lineup = next(
            (lineup for lineup in lineups if lineup.pk == submitted_lineup_id), selected_lineup)
        selected_version_id = parse_submitted_id(submitted_lineup_form, 'version')

    return {
        'links_form': without_browser_required_validation(
            submitted_links_form or DeckLinksForm(required_count=required_count)),
        'lineups': lineups,
        'selected_lineup_id': selected_lineup.pk if selected_lineup else None,
        'versions': versions_with_deck_counts(selected_lineup),
        'selected_version_id': selected_version_id,
        'required_count': required_count,
        'deck_source': SOURCE_LINEUP if submitted_lineup_form is not None and lineups else SOURCE_LINKS,
        'deck_source_errors': get_deck_source_errors(submitted_form) if submitted_form is not None else [],
    }
