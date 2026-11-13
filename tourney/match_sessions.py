from django.db import IntegrityError, transaction

from trade_secrets.engine import Seat
from trade_secrets.models import PreloadedLineup, Session

from .models import Match


def can_match_have_session(tournament, match):
    return (
        tournament.trade_secrets_template_id is not None
        and match.player_two is not None
        and match.player_one.player.user_id is not None
        and match.player_two.player.user_id is not None
    )


def get_preloaded_lineup(player, required_deck_count):
    player_decks = list(player.lineup_decks.select_related('source_version'))
    if len(player_decks) != required_deck_count:
        return None
    return PreloadedLineup(
        deck_ids=tuple(player_deck.deck_id for player_deck in player_decks),
        source_version=player_decks[0].source_version,
    )


def get_preloaded_lineups_by_seat(tournament, match):
    required_deck_count = tournament.get_required_deck_count()
    if required_deck_count is None:
        return {}
    players_by_seat = {
        Seat.HOST: match.player_one.player,
        Seat.GUEST: match.player_two.player,
    }
    lineups_by_seat = {
        seat: get_preloaded_lineup(player, required_deck_count)
        for seat, player in players_by_seat.items()
    }
    return {seat: lineup for seat, lineup in lineups_by_seat.items() if lineup is not None}


def create_session_unless_match_has_one(tournament, match):
    with transaction.atomic():
        locked_match = Match.objects.select_for_update().get(pk=match.pk)
        if locked_match.trade_secrets_session_id is None:
            locked_match.trade_secrets_session = Session.create_for_players(
                tournament.trade_secrets_template,
                host=match.player_one.player.user,
                guest=match.player_two.player.user,
                lineups_by_seat=get_preloaded_lineups_by_seat(tournament, match),
            )
            locked_match.save(update_fields=['trade_secrets_session'])
        return locked_match.trade_secrets_session


def find_match_session(match):
    return Match.objects.select_related('trade_secrets_session').get(pk=match.pk).trade_secrets_session


def get_or_create_match_session(tournament, match):
    if match.trade_secrets_session_id is not None:
        return match.trade_secrets_session
    if not can_match_have_session(tournament, match):
        return None
    try:
        return create_session_unless_match_has_one(tournament, match)
    except IntegrityError:
        return find_match_session(match)
