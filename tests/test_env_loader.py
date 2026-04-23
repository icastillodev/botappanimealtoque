import logging
import os
import unittest

from env_loader import load_task_and_shop_config, parse_env_int


class TestParseEnvInt(unittest.TestCase):
    def test_empty_returns_default(self):
        self.assertIsNone(parse_env_int("__MISSING_KEY_XYZ__", None))
        self.assertEqual(parse_env_int("__MISSING_KEY_XYZ__", 42), 42)

    def test_strip_and_comment(self):
        os.environ["__T_INT__"] = "  99  "
        self.assertEqual(parse_env_int("__T_INT__"), 99)
        os.environ["__T_INT2__"] = "7 # comentario"
        self.assertEqual(parse_env_int("__T_INT2__"), 7)
        del os.environ["__T_INT__"]
        del os.environ["__T_INT2__"]


class TestLoadTaskAndShop(unittest.TestCase):
    def setUp(self):
        self._backup = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._backup)

    def test_load_with_minimal_env(self):
        os.environ["GENERAL_CHANNEL_ID"] = "1"
        os.environ["PRESENTACION_CHANNEL_ID"] = "2"
        os.environ["REGLAS_CHANNEL_ID"] = "3"
        os.environ["SOCIAL_CHANNEL_ID"] = "4"
        os.environ["AUTOROL_CHANNEL_ID"] = "5"
        os.environ["FANARTS_CHANNEL_ID"] = "6"
        os.environ["COSPLAYS_CHANNEL_ID"] = "7"
        os.environ["MEMES_CHANNEL_ID"] = "8"
        os.environ["VIDEOS_CHANNEL_ID"] = "9"
        os.environ["ANIMEDEBATE_CHANNEL_ID"] = "10"
        os.environ["MANGA_CHANNEL_ID"] = "11"
        os.environ["ID_CANAL_CONTENIDOCOMUNIDAD"] = "12"
        os.environ["ROL_COMENTARIO_ID"] = "13"
        os.environ["PAIS_COMENTARIO_ID"] = "14"
        os.environ["AKATSUKI_ROLE_ID"] = "15"
        os.environ["JONIN_ROLE_ID"] = "16"
        os.environ["ID_ROL_CONTENIDOS"] = "17"
        # vacíos → 0 sin ValueError
        os.environ["SHOP_PRICE_ROLE_AKATSUKI"] = ""
        os.environ["SHOP_PRICE_ROLE_JONIN"] = ""
        os.environ["SHOP_PRICE_PIN_MESSAGE"] = ""
        os.environ["VOTING_CHANNEL_ID"] = "100"
        # sin VOTACION_CHANNEL_ID → debe tomar VOTING
        log = logging.getLogger("test")
        t, s = load_task_and_shop_config(log)
        self.assertIsNotNone(t)
        self.assertIsNotNone(s)
        assert s is not None
        self.assertEqual(s["price_akatsuki"], 0)
        self.assertEqual(s["votacion_channel_id"], 100)
        self.assertEqual(s["trampa_carta_rol_24h_id"], 0)
        self.assertEqual(t["channels"]["guia_bot"], 0)
        self.assertEqual(t["rewards"]["anime_top10_bonus"], 200)
        self.assertEqual(t["rewards"]["anime_top30_bonus"], 500)
        # Blister: default de código si no está en env
        self.assertEqual(s["price_blister_trampa"], 1200)

    def test_shop_global_scale_percent(self):
        os.environ["GENERAL_CHANNEL_ID"] = "1"
        os.environ["PRESENTACION_CHANNEL_ID"] = "2"
        os.environ["REGLAS_CHANNEL_ID"] = "3"
        os.environ["SOCIAL_CHANNEL_ID"] = "4"
        os.environ["AUTOROL_CHANNEL_ID"] = "5"
        os.environ["FANARTS_CHANNEL_ID"] = "6"
        os.environ["COSPLAYS_CHANNEL_ID"] = "7"
        os.environ["MEMES_CHANNEL_ID"] = "8"
        os.environ["VIDEOS_CHANNEL_ID"] = "9"
        os.environ["ANIMEDEBATE_CHANNEL_ID"] = "10"
        os.environ["MANGA_CHANNEL_ID"] = "11"
        os.environ["ID_CANAL_CONTENIDOCOMUNIDAD"] = "12"
        os.environ["ROL_COMENTARIO_ID"] = "13"
        os.environ["PAIS_COMENTARIO_ID"] = "14"
        os.environ["AKATSUKI_ROLE_ID"] = "15"
        os.environ["JONIN_ROLE_ID"] = "16"
        os.environ["ID_ROL_CONTENIDOS"] = "17"
        os.environ["SHOP_PRICE_BLISTER_TRAMPA"] = "1000"
        os.environ["SHOP_GLOBAL_SCALE_PERCENT"] = "130"
        os.environ["VOTING_CHANNEL_ID"] = "100"
        log = logging.getLogger("test")
        _t, s = load_task_and_shop_config(log)
        assert s is not None
        self.assertEqual(s["price_blister_trampa"], 1300)
        self.assertEqual(s["price_akatsuki"], 0)


if __name__ == "__main__":
    unittest.main()
