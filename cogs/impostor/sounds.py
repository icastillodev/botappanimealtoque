# Sonidos opcionales al ver el rol (ephemeral).
from __future__ import annotations

import io
import logging
import os
from typing import Optional

import aiohttp
import discord

log = logging.getLogger(__name__)


def get_impostor_sound_url() -> Optional[str]:
    raw = (os.getenv("IMPOSTOR_SOUND_URL") or "").strip()
    return raw or None


def get_social_sound_url() -> Optional[str]:
    raw = (os.getenv("SOCIAL_SOUND_URL") or "").strip()
    return raw or None


async def fetch_role_sound_file(url: Optional[str]) -> Optional[discord.File]:
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                if not data or len(data) > 7_500_000:
                    return None
                name = "impostor.mp3" if "impostor" in url.lower() else "social.mp3"
                return discord.File(io.BytesIO(data), filename=name)
    except Exception as e:
        log.debug("No se pudo descargar sonido de rol: %s", e)
        return None
