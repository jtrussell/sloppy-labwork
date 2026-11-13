from dataclasses import dataclass

from trade_secrets.deck_sources import build_deck_source_context
from trade_secrets.engine import DeckStatus

from .models import Player


@dataclass
class PlayerLineupPanel:
    cards: list
    required_deck_count: int
    can_change: bool
    is_editing: bool = False
    was_saved: bool = False

    @property
    def deck_count(self):
        return len(self.cards)

    @property
    def is_complete(self):
        return self.deck_count == self.required_deck_count

    @property
    def shows_form(self):
        return self.can_change and (self.is_editing or not self.is_complete)

    @property
    def is_locked(self):
        return self.is_complete and not self.can_change


def get_lineup_cards(player):
    player_decks = player.lineup_decks.select_related(
        'deck__set', 'deck__house_1', 'deck__house_2', 'deck__house_3')
    return [{'deck': player_deck.deck, 'status': DeckStatus.AVAILABLE} for player_deck in player_decks]


def build_player_lineup_panel(player, required_deck_count, is_editing=False, was_saved=False):
    return PlayerLineupPanel(
        cards=get_lineup_cards(player),
        required_deck_count=required_deck_count,
        can_change=player.can_change_lineup(required_deck_count),
        is_editing=is_editing,
        was_saved=was_saved,
    )


def can_register(tournament):
    return tournament.is_accepting_registrations and not tournament.is_closed


def build_registration_lineup_context(tournament, user, player, submitted_deck_form=None,
                                      is_editing_lineup=False, was_lineup_saved=False):
    context = {
        'trade_secrets_template': None,
        'can_view_trade_secrets_template': False,
        'required_deck_count': None,
        'player_lineup': None,
    }
    if not user.is_authenticated:
        return context

    if tournament.trade_secrets_template_id is not None:
        context['trade_secrets_template'] = tournament.trade_secrets_template
        context['can_view_trade_secrets_template'] = tournament.trade_secrets_template.can_view(user)

    required_deck_count = tournament.get_required_deck_count()
    if required_deck_count is None:
        return context
    context['required_deck_count'] = required_deck_count

    shows_deck_form = player is None and can_register(tournament)
    if player is not None and player.status == Player.PlayerStatus.ACTIVE:
        player_lineup = build_player_lineup_panel(
            player, required_deck_count, is_editing_lineup, was_lineup_saved)
        context['player_lineup'] = player_lineup
        shows_deck_form = player_lineup.shows_form

    if shows_deck_form:
        context.update(build_deck_source_context(user, required_deck_count, submitted_deck_form))
    return context
