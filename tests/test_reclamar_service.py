import unittest
from unittest.mock import MagicMock

from cogs.economia.reclamar_service import reclaim_rewards


class TestReclaimRewards(unittest.TestCase):
    def test_inicial_claim(self):
        db = MagicMock()
        db.modify_blisters.return_value = (3, [])
        db.get_progress_inicial.return_value = {
            "completado": 0,
            "presentacion": 1,
            "reaccion_pais": 1,
            "reaccion_rol": 1,
            "reaccion_social": 1,
            "reaccion_reglas": 1,
            "general_mensaje": 1,
        }
        db.wishlist_total_filled.return_value = 10
        db.anime_top_count_filled.return_value = 10
        db.hated_total_filled.return_value = 5
        task_config = {"rewards": {"inicial": 1000, "diaria": 1, "semanal": 1}}

        ok, ok_msgs, err_msgs = reclaim_rewards(db, task_config, 12345, "inicial")

        self.assertTrue(ok)
        self.assertTrue(any("Inicial" in m for m in ok_msgs))
        self.assertFalse(err_msgs)
        db.modify_points.assert_called_once_with(12345, 1000)
        db.modify_blisters.assert_called_once_with(12345, "trampa", 3)
        db.claim_reward.assert_called_once_with(12345, "inicial")

    def test_inicial_already_done(self):
        db = MagicMock()
        db.get_progress_inicial.return_value = {"completado": 1}
        task_config = {"rewards": {"inicial": 1000}}

        ok, ok_msgs, err_msgs = reclaim_rewards(db, task_config, 1, "inicial")

        self.assertFalse(ok)
        self.assertIn("Inicial: Ya reclamado.", err_msgs[0])

    def test_reclaim_all_partial_only_diaria(self):
        """`tipo=None` debe cobrar lo listo aunque inicial siga incompleto."""
        db = MagicMock()
        db.modify_blisters.return_value = (1, [])
        db.get_progress_inicial.return_value = {"completado": 0, "presentacion": 0}
        db.wishlist_total_filled.return_value = 0
        db.anime_top_count_filled.return_value = 0
        db.hated_total_filled.return_value = 0
        db.get_progress_diaria.return_value = {
            "completado": 0,
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
        task_config = {"rewards": {"inicial": 1000, "diaria": 50, "semanal": 1}}

        ok, ok_msgs, err_msgs = reclaim_rewards(db, task_config, 999, None)

        self.assertTrue(ok)
        self.assertTrue(any("Diaria" in m for m in ok_msgs))
        db.claim_reward.assert_called_once_with(999, "diaria")


if __name__ == "__main__":
    unittest.main()
