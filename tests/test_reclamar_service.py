import unittest
from unittest.mock import MagicMock, call

from cogs.economia.reclamar_service import (
    format_diaria_reclaim_blocked_explanation,
    parse_reclamo_prefijo_parts,
    reclaim_rewards,
)


class TestDiariaExplanation(unittest.TestCase):
    def test_diaria_explanation_lists_blocks(self):
        prog = {
            "mensajes_servidor": 10,
            "reacciones_servidor": 3,
            "oraculo_preguntas": 1,
            "trampa_enviada": 0,
            "trampa_sin_objetivo": 0,
        }
        txt = format_diaria_reclaim_blocked_explanation(prog)
        self.assertIn("premio 1", txt.lower())
        self.assertIn("premio 2", txt.lower())
        self.assertIn("10/10", txt)


class TestParseReclamoPrefijo(unittest.TestCase):
    def test_global_codes(self):
        self.assertEqual(parse_reclamo_prefijo_parts(["1"]), ("inicial", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["2"]), ("diaria", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["3"]), ("semanal", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["4"]), ("semanal_especial", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["5"]), ("semanal_minijuegos", None))

    def test_semanal_subrefs(self):
        self.assertEqual(parse_reclamo_prefijo_parts(["semanal", "1"]), ("semanal", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["weekly", "2"]), ("semanal_especial", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["semanal", "3"]), ("semanal_minijuegos", None))
        err = parse_reclamo_prefijo_parts(["semanal", "9"])[1]
        self.assertIsNotNone(err)

    def test_inicial_subrefs(self):
        self.assertEqual(parse_reclamo_prefijo_parts(["inicial"]), ("inicial", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["inicial", "1"]), ("inicial_comunidad", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["starter", "2"]), ("inicial_perfil_min", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["iniciacion", "3"]), ("inicial_perfil_max", None))

    def test_diaria_subrefs(self):
        self.assertEqual(parse_reclamo_prefijo_parts(["diaria"]), ("diaria", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["diaria", "1"]), ("diaria_actividad", None))
        self.assertEqual(parse_reclamo_prefijo_parts(["daily", "2"]), ("diaria_trampa", None))

    def test_todo_keyword(self):
        self.assertEqual(parse_reclamo_prefijo_parts(["todo"]), (None, None))


class TestReclaimRewards(unittest.TestCase):
    def test_inicial_claim_three_parts(self):
        db = MagicMock()
        db.modify_blisters.return_value = (1, [])
        db.get_progress_inicial.return_value = {
            "completado": 0,
            "completado_inicial_comunidad": 0,
            "completado_inicial_perfil_min": 0,
            "completado_inicial_perfil_max": 0,
            "presentacion": 1,
            "reaccion_pais": 1,
            "reaccion_rol": 1,
            "reaccion_social": 1,
            "reaccion_reglas": 1,
            "general_mensaje": 1,
        }
        db.wishlist_total_filled.return_value = 33
        db.anime_top_count_filled.side_effect = lambda _uid, n: n
        db.hated_total_filled.return_value = 10
        task_config = {
            "rewards": {
                "inicial_comunidad": 300,
                "inicial_perfil_min": 300,
                "inicial_perfil_max": 400,
                "inicial_comunidad_blisters": 1,
                "inicial_perfil_min_blisters": 1,
                "inicial_perfil_max_blisters": 1,
                "diaria": 1,
                "semanal": 1,
            }
        }

        ok, ok_msgs, err_msgs = reclaim_rewards(db, task_config, 12345, "inicial")

        self.assertTrue(ok)
        self.assertEqual(len(err_msgs), 0)
        self.assertEqual(db.claim_reward.call_count, 3)
        db.claim_reward.assert_has_calls(
            [
                call(12345, "inicial_comunidad"),
                call(12345, "inicial_perfil_min"),
                call(12345, "inicial_perfil_max"),
            ]
        )

    def test_inicial_all_done_bundle(self):
        db = MagicMock()
        db.get_progress_inicial.return_value = {"completado": 1}

        ok, ok_msgs, err_msgs = reclaim_rewards(db, {"rewards": {"inicial_comunidad": 1}}, 1, "inicial")

        self.assertFalse(ok)
        self.assertIn("tres partes", err_msgs[0].lower())

    def test_reclaim_all_partial_only_diaria(self):
        """`tipo=None` debe cobrar lo listo aunque inicial siga incompleto."""
        db = MagicMock()
        db.modify_blisters.return_value = (1, [])
        db.get_progress_inicial.return_value = {
            "completado": 0,
            "completado_inicial_comunidad": 0,
            "presentacion": 0,
        }
        db.wishlist_total_filled.return_value = 0
        db.anime_top_count_filled.return_value = 0
        db.hated_total_filled.return_value = 0
        db.get_progress_diaria.return_value = {
            "completado": 0,
            "completado_diaria_actividad": 0,
            "completado_diaria_trampa": 0,
            "mensajes_servidor": 10,
            "reacciones_servidor": 3,
            "trampa_enviada": 1,
            "trampa_sin_objetivo": 0,
            "oraculo_preguntas": 1,
        }
        db.get_progress_semanal.return_value = {
            "completado": 0,
            "debate_post": None,
            "videos_reaccion": None,
            "media_escrito": None,
            "completado_especial": 0,
            "impostor_partidas": 0,
            "impostor_victorias": 0,
            "completado_minijuegos": 0,
            "mg_ret_roll_apuesta": 0,
            "mg_roll_casual": 0,
            "mg_duelo": 0,
            "mg_voto_dom": 0,
        }
        task_config = {
            "rewards": {
                "inicial_comunidad": 1,
                "diaria_actividad": 25,
                "diaria_trampa": 25,
                "diaria_actividad_blisters": 1,
                "diaria_trampa_blisters": 0,
                "semanal": 1,
            }
        }

        ok, ok_msgs, err_msgs = reclaim_rewards(db, task_config, 999, None)

        self.assertTrue(ok)
        self.assertTrue(any("Diario 1" in m for m in ok_msgs))
        db.claim_reward.assert_called_once_with(999, "diaria_actividad")


if __name__ == "__main__":
    unittest.main()
