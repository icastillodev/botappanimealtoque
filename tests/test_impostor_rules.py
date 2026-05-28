"""Tests de reglas Impostor (sin instalar discord.py en el runner)."""
import importlib.util
import os
import sys
import types
import unittest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_IMPOSTOR_DIR = os.path.join(_ROOT, "cogs", "impostor")


def _load_impostor_module(name: str):
    """Carga un .py de cogs/impostor sin ejecutar __init__.py (evita import discord)."""
    if "cogs" not in sys.modules:
        sys.modules["cogs"] = types.ModuleType("cogs")
    if "cogs.impostor" not in sys.modules:
        sys.modules["cogs.impostor"] = types.ModuleType("cogs.impostor")

    full_name = f"cogs.impostor.{name}"
    path = os.path.join(_IMPOSTOR_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(full_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


engine = _load_impostor_module("engine")
config = _load_impostor_module("config")
rules = _load_impostor_module("rules")
rematch_utils = _load_impostor_module("rematch_utils")

GameState = engine.GameState
PHASE_END = engine.PHASE_END
PHASE_IDLE = engine.PHASE_IDLE
ROLE_IMPOSTOR = engine.ROLE_IMPOSTOR
ROLE_SOCIAL = engine.ROLE_SOCIAL


class TestMaxImpostors(unittest.TestCase):
    def test_scaling(self):
        self.assertEqual(rules.max_impostors_for_players(4), 1)
        self.assertEqual(rules.max_impostors_for_players(6), 2)
        self.assertEqual(rules.max_impostors_for_players(9), 3)


class TestVictory(unittest.TestCase):
    def _lobby_with_players(self, n_humans: int, impostor_ids: set):
        lb = GameState(
            lobby_name="t",
            guild_id=1,
            channel_id=2,
            host_id=100,
        )
        for i in range(n_humans):
            uid = 1000 + i
            p = lb.add_player(uid, is_bot=False)
            p.role = ROLE_IMPOSTOR if uid in impostor_ids else ROLE_SOCIAL
            p.alive = True
        lb.impostor_ids = impostor_ids
        return lb

    def test_social_wins_no_impostors(self):
        lb = self._lobby_with_players(4, {1000})
        lb.get_player(1000).alive = False
        lb.impostor_ids = set()
        result = rules.check_round_start_victory(lb)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], ROLE_SOCIAL)

    def test_impostor_wins_two_or_less_socials(self):
        lb = self._lobby_with_players(4, {1000})
        for uid in (1001, 1002, 1003):
            lb.get_player(uid).alive = False
        result = rules.check_round_start_victory(lb)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], ROLE_IMPOSTOR)


class TestRematchVotes(unittest.TestCase):
    def test_percent_50(self):
        os.environ["IMPOSTOR_REMATCH_VOTE_PERCENT"] = "50"
        lb = GameState("t", 1, 2, 3)
        for i in range(4):
            lb.add_player(10 + i, is_bot=False)
        self.assertEqual(rematch_utils.rematch_votes_needed(lb), 2)
        del os.environ["IMPOSTOR_REMATCH_VOTE_PERCENT"]

    def test_percent_100(self):
        os.environ["IMPOSTOR_REMATCH_VOTE_PERCENT"] = "100"
        lb = GameState("t", 1, 2, 3)
        for i in range(5):
            lb.add_player(10 + i, is_bot=False)
        self.assertEqual(rematch_utils.rematch_votes_needed(lb), 5)
        del os.environ["IMPOSTOR_REMATCH_VOTE_PERCENT"]


class TestResetForRematch(unittest.TestCase):
    def test_reset_clears_game_state(self):
        lb = GameState("t", 1, 2, 3)
        lb.add_player(10, is_bot=False)
        lb.phase = PHASE_END
        lb.in_progress = True
        lb.round_num = 2
        lb.character_name = "Naruto"
        lb.impostor_ids = {10}
        lb.rematch_votes = {10}
        lb.reset_for_rematch()
        self.assertEqual(lb.phase, PHASE_IDLE)
        self.assertFalse(lb.in_progress)
        self.assertEqual(lb.round_num, 0)
        self.assertIsNone(lb.character_name)
        self.assertEqual(len(lb.impostor_ids), 0)
        self.assertEqual(len(lb.rematch_votes), 0)
        self.assertFalse(lb.get_player(10).ready_in_lobby)


if __name__ == "__main__":
    unittest.main()
