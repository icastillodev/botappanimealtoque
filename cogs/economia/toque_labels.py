# Marca "Toque" (moneda del canal). El emote por defecto es :mmmm:; en .env podés poner TOQUE_EMOJI=<:mmmm:ID> para que renderice en todos lados.
from __future__ import annotations

import os

TOQUE_EMOJI = (os.environ.get("TOQUE_EMOJI") or ":mmmm:").strip()


def toque_emote() -> str:
    return TOQUE_EMOJI


def toque_unit_name() -> str:
    """Nombre visible de la moneda (con emote)."""
    return f"{TOQUE_EMOJI} Toque points"


def fmt_toque_line(n: int) -> str:
    """Una cantidad en una línea de texto (precios, tablas)."""
    return f"{TOQUE_EMOJI} **{int(n)}**"


def fmt_toque_sentence(n: int) -> str:
    """Para frases tipo 'ganaste X toque points'."""
    return f"**{int(n)}** {TOQUE_EMOJI} Toque points"


def guia_toque_explicacion() -> str:
    """Párrafo corto para guía / ayuda: qué son."""
    return (
        f"{TOQUE_EMOJI} **Toque points** — moneda del servidor para tienda, canjes y minijuegos "
        f"(antes «puntos del bot»). Consultá tu saldo con **`?puntos`** o **`/aat-puntos`**."
    )
