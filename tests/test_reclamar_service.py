import unittest
from unittest.mock import MagicMock

from cogs.economia.reclamar_service import reclaim_rewards


class TestReclaimRewards(unittest.TestCase):
    def test_inicial_claim(self):
        db = MagicMock()
        db.get_progress_inicial.return_value = {
            "completado": 0,
            "presentacion": 1,
            "reaccion_pais": 1,
            "reaccion_rol": 1,
            "reaccion_social": 1,
            "reaccion_reglas": 1,
            "general_mensaje": 1,
        }
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


if __name__ == "__main__":
    unittest.main()
