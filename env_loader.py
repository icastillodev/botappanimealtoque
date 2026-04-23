"""
Carga de variables de entorno para economía / tienda / tareas.
Enteros vacíos o inválidos → valor por omisión (no rompe int()).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple


def parse_env_int(key: str, default: Optional[int] = None) -> Optional[int]:
    raw = os.getenv(key)
    if raw is None:
        return default
    s = str(raw).strip()
    if not s or s.startswith("#"):
        return default
    if "#" in s:
        s = s.split("#", 1)[0].strip()
    if not s:
        return default
    try:
        return int(s)
    except ValueError:
        return default


def _int(key: str, default: int = 0) -> int:
    v = parse_env_int(key, default)
    return int(v) if v is not None else default


def load_task_and_shop_config(log: logging.Logger) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    log.info("Cargando IDs de configuración (env_loader)...")
    try:
        price_inicial = _int("REWARD_INICIAL_POINTS", 1000)
        price_diaria = _int("REWARD_DIARIA_POINTS", 50)
        price_semanal = _int("REWARD_SEMANAL_POINTS", 300)

        task_config: Dict[str, Any] = {
            "channels": {
                "general": _int("GENERAL_CHANNEL_ID", 0),
                "presentacion": _int("PRESENTACION_CHANNEL_ID", 0),
                "reglas": _int("REGLAS_CHANNEL_ID", 0),
                "social": _int("SOCIAL_CHANNEL_ID", 0),
                "autorol": _int("AUTOROL_CHANNEL_ID", 0),
                "fanarts": _int("FANARTS_CHANNEL_ID", 0),
                "cosplays": _int("COSPLAYS_CHANNEL_ID", 0),
                "memes": _int("MEMES_CHANNEL_ID", 0),
                "videos": _int("VIDEOS_CHANNEL_ID", 0),
                "anime_debate": _int("ANIMEDEBATE_CHANNEL_ID", 0),
                "manga_debate": _int("MANGA_CHANNEL_ID", 0),
                "contenido_comunidad": _int("ID_CANAL_CONTENIDOCOMUNIDAD", 0),
                "guia_bot": _int("BOT_GUIA_CHANNEL_ID", 0),
            },
            "messages": {
                "rol": _int("ROL_COMENTARIO_ID", 0),
                "pais": _int("PAIS_COMENTARIO_ID", 0),
            },
            "rewards": {
                "inicial": price_inicial,
                "diaria": price_diaria,
                "semanal": price_semanal,
                "especial_semanal": _int("REWARD_ESPECIAL_SEMANAL_POINTS", 400),
                "especial_semanal_blisters": _int("REWARD_ESPECIAL_SEMANAL_BLISTERS", 2),
                "minijuegos_semanal": _int("REWARD_MINIJUEGOS_SEMANAL_POINTS", 150),
                "minijuegos_semanal_blisters": _int("REWARD_MINIJUEGOS_SEMANAL_BLISTERS", 1),
                # Oráculo: puntos por pregunta (hasta N preguntas/día con puntos; igual cuenta para la diaria)
                "oracle_pregunta_points": _int("REWARD_ORACLE_PREGUNTA_POINTS", 3),
                "oracle_max_preguntas_con_puntos": _int("REWARD_ORACLE_MAX_PREGUNTAS_CON_PUNTOS", 5),
                "anime_top10_bonus": _int("REWARD_ANIME_TOP10_POINTS", 200),
                "anime_top30_bonus": _int("REWARD_ANIME_TOP30_POINTS", 500),
            },
        }

        votacion_ch = _int("VOTACION_CHANNEL_ID", 0) or _int("VOTING_CHANNEL_ID", 0)

        # Multiplica solo precios de tienda > 0 (100 = igual; 130 ≈ +30 %). Útil si subió el ingreso diario.
        shop_scale = _int("SHOP_GLOBAL_SCALE_PERCENT", 100)
        shop_scale = max(50, min(300, shop_scale))

        def _scaled_shop_price(key: str, default: int = 0) -> int:
            p = _int(key, default)
            if p <= 0:
                return p
            return max(1, int(round(p * (shop_scale / 100.0))))

        shop_config: Dict[str, Any] = {
            "akatsuki_role_id": _int("AKATSUKI_ROLE_ID", 0),
            "jonin_role_id": _int("JONIN_ROLE_ID", 0),
            "id_rol_contenidos": _int("ID_ROL_CONTENIDOS", 0),
            "price_akatsuki": _scaled_shop_price("SHOP_PRICE_ROLE_AKATSUKI", 0),
            "price_jonin": _scaled_shop_price("SHOP_PRICE_ROLE_JONIN", 0),
            "price_pin": _scaled_shop_price("SHOP_PRICE_PIN_MESSAGE", 0),
            "price_blister_trampa": _scaled_shop_price("SHOP_PRICE_BLISTER_TRAMPA", 1200),
            "price_poll_tienda": _scaled_shop_price("SHOP_PRICE_POLL_TIENDA", 0),
            "price_pin_general": _scaled_shop_price("SHOP_PRICE_PIN_GENERAL", 0),
            "price_temp_role": _scaled_shop_price("SHOP_PRICE_TEMP_ROLE", 0),
            "votacion_channel_id": votacion_ch,
            "temp_role_prefix": (os.getenv("SHOP_TEMP_ROLE_PREFIX", "★ ") or "★ ")[:16],
            "temp_role_days": _int("SHOP_TEMP_ROLE_DAYS", 30),
            "trampa_carta_rol_24h_id": _int("TRAMPA_CARTA_ROL_24H_ROLE_ID", 0),
            "trampa_carta_rol_24h_hours": max(1, min(168, _int("TRAMPA_CARTA_ROL_24H_HOURS", 24))),
        }

        log.info("Configuración de Tareas y Tienda cargada exitosamente.")
        return task_config, shop_config

    except Exception as e:
        log.critical("Error cargando configuración desde .env: %s", e)
        return None, None
