from __future__ import annotations


class UnsupportedGameProfileError(RuntimeError):
    pass


def require_game_profile(game: dict, *, game_id: str = "GMPE01", region: str = "USA") -> dict:
    actual_id = game.get("game_id", "unknown") if game else "unknown"
    actual_region = game.get("region", "unknown") if game else "unknown"
    if actual_id != game_id or actual_region != region:
        raise UnsupportedGameProfileError(
            f"UNSUPPORTED_GAME_PROFILE: expected {game_id}/{region}, got {actual_id}/{actual_region}"
        )
    return game
