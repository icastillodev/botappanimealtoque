# Lógica compartida de /aat-reclamar (una sola implementación).
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .toque_labels import fmt_toque_sentence

log = logging.getLogger(__name__)


def _pv(val: Any) -> int:
    """SQLite / Row a veces devuelve None o str; evita TypeError en comparaciones."""
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _claimed(val: Any) -> bool:
    return _pv(val) == 1

TipoReclamo = Optional[str]

_CANONICAL_TIPOS = frozenset(
    {
        "inicial",
        "diaria",
        "semanal",
        "semanal_especial",
        "semanal_minijuegos",
        "inicial_comunidad",
        "inicial_perfil_min",
        "inicial_perfil_max",
        "diaria_actividad",
        "diaria_trampa",
    }
)

# Alias → nombre interno de `claim_reward` / slash.
_RECLAMO_ALIASES: Dict[str, str] = {
    "inicial": "inicial",
    "starter": "inicial",
    "iniciacion": "inicial",
    "onboarding": "inicial",
    "diaria": "diaria",
    "diario": "diaria",
    "daily": "diaria",
    "semanal": "semanal",
    "weekly": "semanal",
    "semanal_especial": "semanal_especial",
    "especial": "semanal_especial",
    "impostor": "semanal_especial",
    "special": "semanal_especial",
    "weekly_special": "semanal_especial",
    "semanal_minijuegos": "semanal_minijuegos",
    "minijuegos": "semanal_minijuegos",
    "minigames": "semanal_minijuegos",
    "weekly_minigames": "semanal_minijuegos",
}


RECLAMO_TIPOS_AYUDA = (
    "Sin argumento = intenta **todo** lo listo. **Iniciación** (3 premios): `?reclamar inicial` (= todo lo listo de iniciación) · "
    "`?reclamar inicial 1` (Discord/comunidad) · `inicial 2` (wishlist+top+odiados al **mínimo**) · `inicial 3` (perfil **completo** al tope). "
    "**Diario** (2 premios): `?reclamar diaria` (= ambos bloques listos) · `diaria 1` (mensajes+reacciones+oráculo) · `diaria 2` (trampa). "
    "**Semanal:** `?reclamar semanal 1` (base) · `2` (especial) · `3` (minijuegos) · `especial 1` · `minijuegos 1`. "
    "**Códigos:** `?reclamar 1` (iniciación, varios cobros) · `2` (diario) · `3`…`5` (semanales). `all` / `todo`."
)

# Atajo numérico (mismo orden que en la guía de estado).
GLOBAL_RECLAMO_CODE_TO_TIPO: Dict[int, str] = {
    1: "inicial",
    2: "diaria",
    3: "semanal",
    4: "semanal_especial",
    5: "semanal_minijuegos",
}


def parse_reclamo_prefijo_parts(parts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Trocea `?reclamar …` (palabras sin vacíos).
    Devuelve (tipo para `reclaim_rewards`, mensaje_error).
    (None, None) = reclamar **todo** (equivale a `all` / `todo`, lo resuelve el caller).
    """
    if not parts:
        return (None, "Escribí al menos un tipo o `?reclamar` solo para la guía.")

    def _parse_ref(tok: str) -> Tuple[Optional[int], Optional[str]]:
        try:
            n = int(tok, 10)
        except ValueError:
            return None, f"Número de referencia inválido: `{tok}` (tenés que ser un entero, ej. `1`)."
        if n < 1:
            return None, "La referencia tiene que ser **≥ 1**."
        return n, None

    p0 = parts[0].strip()
    low = p0.lower()

    if is_reclamar_all_keyword(low):
        return (None, None)

    # Solo dígitos: código global 1–5 (un solo token)
    if low.isdigit():
        if len(parts) > 1:
            return (
                None,
                "Para el **código global** usá **solo** el número (ej. `?reclamar 2`). "
                "Si querés tipo + referencia: `?reclamar diaria 1` · `?reclamar semanal 2`.",
            )
        code = int(low, 10)
        mapped = GLOBAL_RECLAMO_CODE_TO_TIPO.get(code)
        if not mapped:
            return (
                None,
                f"Código **`{code}`** inválido. Usá **1**=inicial · **2**=diaria · **3**=semanal base · "
                "**4**=especial Impostor · **5**=minijuegos.",
            )
        return (mapped, None)

    m = map_reclamo_token_to_tipo(p0)
    if m is None:
        return (None, f"No reconozco `{parts[0]}`. {RECLAMO_TIPOS_AYUDA}")

    if len(parts) > 2:
        return (None, "Demasiados argumentos: usá `?reclamar <tipo> [número]` o `?reclamar <código>`.")

    if m == "semanal":
        ref = 1
        if len(parts) >= 2:
            r, err = _parse_ref(parts[1])
            if err:
                return (None, err)
            ref = r  # type: ignore[assignment]
        if ref == 1:
            return ("semanal", None)
        if ref == 2:
            return ("semanal_especial", None)
        if ref == 3:
            return ("semanal_minijuegos", None)
        return (
            None,
            "Para **`semanal`** el número es **1** (base), **2** (especial Impostor) o **3** (minijuegos). "
            "También podés `?reclamar especial 1` o `?reclamar minijuegos 1`.",
        )

    if m == "inicial":
        if len(parts) == 1:
            return ("inicial", None)
        r, err = _parse_ref(parts[1])
        if err:
            return (None, err)
        if r == 1:
            return ("inicial_comunidad", None)
        if r == 2:
            return ("inicial_perfil_min", None)
        if r == 3:
            return ("inicial_perfil_max", None)
        return (None, "Para **`inicial`** la referencia es **1** (Discord), **2** (perfil mínimo) o **3** (perfil completo).")

    if m == "diaria":
        if len(parts) == 1:
            return ("diaria", None)
        r, err = _parse_ref(parts[1])
        if err:
            return (None, err)
        if r == 1:
            return ("diaria_actividad", None)
        if r == 2:
            return ("diaria_trampa", None)
        return (None, "Para **`diaria`** / **`daily`** la referencia es **1** (actividad+oráculo) o **2** (trampa).")

    if m in ("semanal_especial", "semanal_minijuegos"):
        ref = 1
        if len(parts) >= 2:
            r, err = _parse_ref(parts[1])
            if err:
                return (None, err)
            ref = r  # type: ignore[assignment]
        if ref != 1:
            return (
                None,
                f"Para **`{parts[0]}`** solo existe la referencia **1** (o omitila). "
                "Los otros premios semanales van con `?reclamar semanal 2` / `semanal 3`.",
            )
        return (m, None)

    return (m, None)


def is_reclamar_all_keyword(token: str) -> bool:
    return token.strip().lower() in ("all", "todo", "todos", "everything")


def map_reclamo_token_to_tipo(token: str) -> Optional[str]:
    """Primer token de `?reclamar …` → nombre canónico, o None si no existe."""
    k = str(token).strip().lower().replace("-", "_")
    if not k:
        return None
    mapped = _RECLAMO_ALIASES.get(k, k)
    if mapped in _CANONICAL_TIPOS:
        return mapped
    return None


# Aviso al reclamar: progreso de iniciación + historial si ya cumplieron Discord antes.
MSG_TIP_INICIACION_AL_RECLAMAR = (
    "Para ver **iniciación** (Discord + perfil): **`/aat-progreso-iniciacion`** o **`?inicial`**. "
    "Si **ya** habías hecho pasos de Discord **antes** y el bot no los cuenta, usá **`/aat-verificar-antiguas`**."
)

# Iniciación: tareas de Discord + perfil (wishlist / top favoritos / odiados).
INICIAL_DISCORD_KEYS = [
    "presentacion",
    "reaccion_pais",
    "reaccion_rol",
    "reaccion_social",
    "reaccion_reglas",
    "general_mensaje",
]
INICIAL_WISHLIST_MIN = 10
INICIAL_TOP_MIN = 10
INICIAL_HATED_MIN = 5
PERFIL_WISHLIST_CAP = 33
PERFIL_TOP_CAP = 33
PERFIL_HATED_CAP = 10


def expand_reclaim_tipos(tipo: TipoReclamo) -> List[str]:
    """Orden de intentos en `reclaim_rewards` (inicial y diario primero por sub-partes)."""
    if tipo is None:
        return [
            "inicial_comunidad",
            "inicial_perfil_min",
            "inicial_perfil_max",
            "diaria_actividad",
            "diaria_trampa",
            "semanal",
            "semanal_especial",
            "semanal_minijuegos",
        ]
    if tipo == "inicial":
        return ["inicial_comunidad", "inicial_perfil_min", "inicial_perfil_max"]
    if tipo == "diaria":
        return ["diaria_actividad", "diaria_trampa"]
    return [tipo]


def inicial_all_claimed(prog: Dict[str, Any]) -> bool:
    if _claimed(prog.get("completado")):
        return True
    return (
        _claimed(prog.get("completado_inicial_comunidad"))
        and _claimed(prog.get("completado_inicial_perfil_min"))
        and _claimed(prog.get("completado_inicial_perfil_max"))
    )


def diaria_all_claimed(prog: Dict[str, Any]) -> bool:
    if _claimed(prog.get("completado")):
        return True
    return _claimed(prog.get("completado_diaria_actividad")) and _claimed(prog.get("completado_diaria_trampa"))


def _inicial_discord_done(prog: Dict[str, Any]) -> bool:
    return all(_pv(prog.get(k)) >= 1 for k in INICIAL_DISCORD_KEYS)


def _inicial_profile_counts(db: Any, user_id: int) -> Tuple[int, int, int]:
    wl = int(db.wishlist_total_filled(user_id))
    top = int(db.anime_top_count_filled(user_id, INICIAL_TOP_MIN))
    hat = int(db.hated_total_filled(user_id))
    return wl, top, hat


def inicial_profile_ready(db: Any, user_id: int) -> bool:
    wl, top, hat = _inicial_profile_counts(db, user_id)
    return wl >= INICIAL_WISHLIST_MIN and top >= INICIAL_TOP_MIN and hat >= INICIAL_HATED_MIN


def inicial_perfil_max_ready(db: Any, user_id: int) -> bool:
    wl = int(db.wishlist_total_filled(user_id))
    top = int(db.anime_top_count_filled(user_id, PERFIL_TOP_CAP))
    hat = int(db.hated_total_filled(user_id))
    return wl >= PERFIL_WISHLIST_CAP and top >= PERFIL_TOP_CAP and hat >= PERFIL_HATED_CAP


def _diaria_actividad_ready(prog: Dict[str, Any]) -> bool:
    msg_n = _pv(prog.get("mensajes_servidor"))
    rx_n = _pv(prog.get("reacciones_servidor"))
    or_n = _pv(prog.get("oraculo_preguntas"))
    return msg_n >= 10 and rx_n >= 3 and or_n >= 1


def _diaria_trampa_ready(prog: Dict[str, Any]) -> bool:
    tr = _pv(prog.get("trampa_enviada"))
    ts = _pv(prog.get("trampa_sin_objetivo"))
    return tr >= 1 or ts >= 1


def _diaria_prog_ready(prog: Dict[str, Any]) -> bool:
    return _diaria_actividad_ready(prog) and _diaria_trampa_ready(prog)


# Alias para imports desde vistas / otros cogs (misma lógica que `?diaria`).
diaria_actividad_ready = _diaria_actividad_ready
diaria_trampa_ready = _diaria_trampa_ready


def format_diaria_actividad_reclaim_blocked(prog: Dict[str, Any]) -> str:
    msg_n = _pv(prog.get("mensajes_servidor"))
    rx_n = _pv(prog.get("reacciones_servidor"))
    or_n = _pv(prog.get("oraculo_preguntas"))
    msg_ok = msg_n >= 10
    rx_ok = rx_n >= 3
    or_ok = or_n >= 1
    lines: List[str] = [
        "**Diario — premio 1 (actividad + oráculo):** todavía no se puede cobrar.",
        f"· Mensajes en el servidor: **{msg_n}/10**",
        f"· Reacciones en el servidor: **{rx_n}/3**",
        f"· Oráculo: **{or_n}/1** (`?pregunta`, @bot, `/aat-consulta`)",
        "_Cuando las tres líneas cumplan, usá **`?reclamar diaria 1`** (o `?reclamar diaria` si también tenés la trampa lista)._",
    ]
    if msg_ok and rx_ok and not or_ok:
        lines.append("_Falta la consulta al oráculo._")
    return "\n".join(lines)


def format_diaria_trampa_reclaim_blocked(prog: Dict[str, Any]) -> str:
    tr = _pv(prog.get("trampa_enviada"))
    ts = _pv(prog.get("trampa_sin_objetivo"))
    lines: List[str] = [
        "**Diario — premio 2 (trampa):** todavía no contó un uso válido hoy.",
        f"· Trampa **con @**: **{tr}/1**",
        f"· Trampa **sin objetivo**: **{ts}/1**",
        "_Alcanza **una** de las dos vías. Luego **`?reclamar diaria 2`**._",
    ]
    return "\n".join(lines)


def format_diaria_reclaim_blocked_explanation(prog: Dict[str, Any]) -> str:
    """Resumen de ambos bloques (p. ej. `?reclamar diaria` cuando falta algo)."""
    return (
        "**Diario:** son **dos premios** por separado (`?reclamar diaria 1` y `diaria 2`).\n\n"
        + format_diaria_actividad_reclaim_blocked(prog)
        + "\n\n"
        + format_diaria_trampa_reclaim_blocked(prog)
    )


def _inicial_sub_claimed(prog: Dict[str, Any], col: str) -> bool:
    if _claimed(prog.get("completado")):
        return True
    return _claimed(prog.get(col))


def _diaria_sub_claimed(prog: Dict[str, Any], col: str) -> bool:
    if _claimed(prog.get("completado")):
        return True
    return _claimed(prog.get(col))


def build_reclaim_status_block(db: Any, _task_config: Dict[str, Any], user_id: int) -> str:
    """Resumen legible: iniciación (3), diario (2), semanales (3)."""
    lines: List[str] = []
    pi = db.get_progress_inicial(user_id)
    if _inicial_sub_claimed(pi, "completado_inicial_comunidad"):
        lines.append("✅ **Inicial 1 — Comunidad (Discord)** — ya cobrado.")
    elif _inicial_discord_done(pi):
        lines.append("☑ **Inicial 1 — Comunidad** — listo · `?reclamar inicial 1` · código **`?reclamar 1`** (varias partes)")
    else:
        lines.append("☐ **Inicial 1 — Comunidad** — incompleto (`?inicial`).")
    if _inicial_sub_claimed(pi, "completado_inicial_perfil_min"):
        lines.append("✅ **Inicial 2 — Perfil mínimo** (wishlist/top/odiados) — ya cobrado.")
    elif inicial_profile_ready(db, user_id):
        lines.append("☑ **Inicial 2 — Perfil mínimo** — listo · `?reclamar inicial 2`")
    else:
        lines.append("☐ **Inicial 2 — Perfil mínimo** — incompleto.")
    if _inicial_sub_claimed(pi, "completado_inicial_perfil_max"):
        lines.append("✅ **Inicial 3 — Perfil completo** (topes) — ya cobrado.")
    elif inicial_perfil_max_ready(db, user_id):
        lines.append("☑ **Inicial 3 — Perfil completo** — listo · `?reclamar inicial 3`")
    else:
        lines.append("☐ **Inicial 3 — Perfil completo** — incompleto.")
    pd = db.get_progress_diaria(user_id)
    if _diaria_sub_claimed(pd, "completado_diaria_actividad"):
        lines.append("✅ **Diario 1 — Actividad + oráculo** — ya cobrado hoy.")
    elif _diaria_actividad_ready(pd):
        lines.append("☑ **Diario 1 — Actividad + oráculo** — listo · `?reclamar diaria 1` · **`?reclamar 2`**")
    else:
        lines.append("☐ **Diario 1 — Actividad + oráculo** — incompleto (`?diaria`).")
    if _diaria_sub_claimed(pd, "completado_diaria_trampa"):
        lines.append("✅ **Diario 2 — Trampa** — ya cobrado hoy.")
    elif _diaria_trampa_ready(pd):
        lines.append("☑ **Diario 2 — Trampa** — listo · `?reclamar diaria 2`")
    else:
        lines.append("☐ **Diario 2 — Trampa** — incompleto.")
    ps = db.get_progress_semanal(user_id)
    if int(ps.get("completado") or 0) == 1:
        lines.append("✅ **Semanal base (ref. 1)** (*weekly*) — ya reclamado.")
    elif int(ps.get("debate_post") or 0) >= 1 and int(ps.get("videos_reaccion") or 0) >= 1 and int(ps.get("media_escrito") or 0) >= 1:
        lines.append("☑ **Semanal base (ref. 1)** — listo · `?reclamar semanal 1` o **`?reclamar 3`**")
    else:
        lines.append("☐ **Semanal base (ref. 1)** — incompleto (`?semanal`).")
    if int(ps.get("completado_especial") or 0) == 1:
        lines.append("✅ **Especial Impostor (ref. 2)** — ya reclamado.")
    elif int(ps.get("impostor_partidas") or 0) >= 3 and int(ps.get("impostor_victorias") or 0) >= 1:
        lines.append("☑ **Especial Impostor (ref. 2)** — listo · `?reclamar semanal 2` · `especial 1` · **`?reclamar 4`**")
    else:
        lines.append("☐ **Especial Impostor (ref. 2)** — incompleto.")
    mg_ok = (
        int(ps.get("mg_ret_roll_apuesta") or 0) >= 1
        and int(ps.get("mg_roll_casual") or 0) >= 1
        and int(ps.get("mg_duelo") or 0) >= 1
        and int(ps.get("mg_voto_dom") or 0) >= 1
    )
    if int(ps.get("completado_minijuegos") or 0) == 1:
        lines.append("✅ **Minijuegos semanal (ref. 3)** — ya reclamado.")
    elif mg_ok:
        lines.append("☑ **Minijuegos semanal (ref. 3)** — listo · `?reclamar semanal 3` · `minijuegos 1` · **`?reclamar 5`**")
    else:
        lines.append("☐ **Minijuegos semanal (ref. 3)** — incompleto.")
    return "\n".join(lines)


def build_inicial_reclaim_hint(db: Any, user_id: int) -> Optional[str]:
    """Si la iniciación sigue pendiente, resume Discord vs perfil (y sugerencia de verificar)."""
    prog = db.get_progress_inicial(user_id)
    if inicial_all_claimed(prog):
        return None
    disc = _inicial_discord_done(prog)
    wl_full = min(int(db.wishlist_total_filled(user_id)), PERFIL_WISHLIST_CAP)
    top_full = int(db.anime_top_count_filled(user_id, PERFIL_TOP_CAP))
    hat_full = min(int(db.hated_total_filled(user_id)), PERFIL_HATED_CAP)
    wl_i, top_i, hat_i = _inicial_profile_counts(db, user_id)
    prof_ok = wl_i >= INICIAL_WISHLIST_MIN and top_i >= INICIAL_TOP_MIN and hat_i >= INICIAL_HATED_MIN

    lines: List[str] = ["📋 **Iniciación:**"]
    lines.append(
        "• Discord: **listo** — si el bot no lo marcó, `/aat-verificar-antiguas`."
        if disc
        else "• Discord: **falta algo** — `/aat-progreso-iniciacion` y `/aat-verificar-antiguas`."
    )
    lines.append(
        f"• Perfil mínimo (reclamo): wishlist **{wl_i}/{INICIAL_WISHLIST_MIN}**, top favoritos **{top_i}/{INICIAL_TOP_MIN}**, "
        f"odiados **{hat_i}/{INICIAL_HATED_MIN}** (`/aat-wishlist_*`, `/aat-anime-top_*`, `/aat-hated_*`)."
    )
    lines.append(
        f"• Perfil completo (máx.): wishlist **{wl_full}/{PERFIL_WISHLIST_CAP}**, top **{top_full}/{PERFIL_TOP_CAP}**, "
        f"odiados **{hat_full}/{PERFIL_HATED_CAP}**."
    )
    if disc and not prof_ok:
        lines.append("**Tip:** Ya cumpliste Discord; completá el perfil y usá `/aat-reclamar` → `inicial`.")
    elif prof_ok and not disc:
        lines.append("**Tip:** Perfil listo para iniciación; falta marcar Discord (o usá `/aat-verificar-antiguas`).")
    elif disc and prof_ok:
        lines.append("**Podés reclamar:** `/aat-reclamar` → `inicial` (cobrá **1 · 2 · 3** según corresponda).")
    return "\n".join(lines)


def reclaim_rewards(
    db: Any,
    task_config: Dict[str, Any],
    user_id: int,
    tipo: TipoReclamo = None,
) -> Tuple[bool, List[str], List[str]]:
    """
    Devuelve (hubo_reclamo, mensajes_exito, mensajes_error).
    Con `tipo=None` intenta **cada** recompensa por separado: cobra las que estén listas
    aunque falte el resto (inicial / diario / semanal no tienen que estar todos juntos).
    """
    if tipo == "inicial":
        p0 = db.get_progress_inicial(user_id)
        if inicial_all_claimed(p0):
            return False, [], ["Inicial: las tres partes ya están cobradas."]
    if tipo == "diaria":
        d0 = db.get_progress_diaria(user_id)
        if diaria_all_claimed(d0):
            return False, [], ["Diaria: las dos partes de hoy ya están cobradas."]

    tipos_a_revisar = expand_reclaim_tipos(tipo)
    rewards = (task_config or {}).get("rewards") or {}
    mute_claimed = tipo is None or tipo in ("inicial", "diaria")

    reclamado_algo = False
    mensajes_exito: List[str] = []
    mensajes_error: List[str] = []

    for objetivo in tipos_a_revisar:
        try:
            if objetivo == "inicial_comunidad":
                prog = db.get_progress_inicial(user_id)
                if _inicial_sub_claimed(prog, "completado_inicial_comunidad"):
                    if not mute_claimed:
                        mensajes_error.append("Inicial 1 (comunidad): ya cobrado.")
                    continue
                if _inicial_discord_done(prog):
                    pts = int(rewards.get("inicial_comunidad") or 0)
                    bl = int(rewards.get("inicial_comunidad_blisters") or 1)
                    if pts <= 0 and bl <= 0:
                        mensajes_error.append("Inicial 1: falta configuración de recompensa.")
                        continue
                    if pts:
                        db.modify_points(user_id, pts)
                    if bl > 0:
                        _, bcol = db.modify_blisters(user_id, "trampa", bl)
                        mensajes_exito.extend(bcol)
                    if not db.claim_reward(user_id, "inicial_comunidad"):
                        continue
                    extra = f" + {bl} Blister(s) 🃏" if bl else ""
                    mensajes_exito.append(f"**Inicial 1 — Comunidad (Discord):** {fmt_toque_sentence(pts)}{extra}")
                    reclamado_algo = True
                elif tipo == "inicial_comunidad":
                    mensajes_error.append(
                        "Inicial 1: incompleto — Discord (presentación, autorol, #general, etc.). "
                        + MSG_TIP_INICIACION_AL_RECLAMAR
                    )

            elif objetivo == "inicial_perfil_min":
                prog = db.get_progress_inicial(user_id)
                if _inicial_sub_claimed(prog, "completado_inicial_perfil_min"):
                    if not mute_claimed:
                        mensajes_error.append("Inicial 2 (perfil mínimo): ya cobrado.")
                    continue
                if inicial_profile_ready(db, user_id):
                    pts = int(rewards.get("inicial_perfil_min") or 0)
                    bl = int(rewards.get("inicial_perfil_min_blisters") or 1)
                    if pts <= 0 and bl <= 0:
                        mensajes_error.append("Inicial 2: falta configuración de recompensa.")
                        continue
                    if pts:
                        db.modify_points(user_id, pts)
                    if bl > 0:
                        _, bcol = db.modify_blisters(user_id, "trampa", bl)
                        mensajes_exito.extend(bcol)
                    if not db.claim_reward(user_id, "inicial_perfil_min"):
                        continue
                    extra = f" + {bl} Blister(s) 🃏" if bl else ""
                    mensajes_exito.append(f"**Inicial 2 — Perfil mínimo:** {fmt_toque_sentence(pts)}{extra}")
                    reclamado_algo = True
                elif tipo == "inicial_perfil_min":
                    wl_i, top_i, hat_i = _inicial_profile_counts(db, user_id)
                    mensajes_error.append(
                        "Inicial 2: incompleto — "
                        f"wishlist {wl_i}/{INICIAL_WISHLIST_MIN}, top {top_i}/{INICIAL_TOP_MIN}, odiados {hat_i}/{INICIAL_HATED_MIN}."
                    )

            elif objetivo == "inicial_perfil_max":
                prog = db.get_progress_inicial(user_id)
                if _inicial_sub_claimed(prog, "completado_inicial_perfil_max"):
                    if not mute_claimed:
                        mensajes_error.append("Inicial 3 (perfil completo): ya cobrado.")
                    continue
                if inicial_perfil_max_ready(db, user_id):
                    pts = int(rewards.get("inicial_perfil_max") or 0)
                    bl = int(rewards.get("inicial_perfil_max_blisters") or 1)
                    if pts <= 0 and bl <= 0:
                        mensajes_error.append("Inicial 3: falta configuración de recompensa.")
                        continue
                    if pts:
                        db.modify_points(user_id, pts)
                    if bl > 0:
                        _, bcol = db.modify_blisters(user_id, "trampa", bl)
                        mensajes_exito.extend(bcol)
                    if not db.claim_reward(user_id, "inicial_perfil_max"):
                        continue
                    extra = f" + {bl} Blister(s) 🃏" if bl else ""
                    mensajes_exito.append(f"**Inicial 3 — Perfil completo:** {fmt_toque_sentence(pts)}{extra}")
                    reclamado_algo = True
                elif tipo == "inicial_perfil_max":
                    mensajes_error.append("Inicial 3: incompleto — falta llenar wishlist/top/odiados a los topes del perfil.")

            elif objetivo == "diaria_actividad":
                prog = db.get_progress_diaria(user_id)
                if _diaria_sub_claimed(prog, "completado_diaria_actividad"):
                    if not mute_claimed:
                        mensajes_error.append("Diario 1 (actividad): ya cobrado hoy.")
                    continue
                if _diaria_actividad_ready(prog):
                    pts = int(rewards.get("diaria_actividad") or rewards.get("diaria") or 0)
                    bl = int(rewards.get("diaria_actividad_blisters") or 0)
                    if pts <= 0 and bl <= 0:
                        mensajes_error.append("Diario 1: falta configuración de recompensa (rewards.diaria_actividad).")
                        continue
                    if pts:
                        db.modify_points(user_id, pts)
                    if bl > 0:
                        _, bcol = db.modify_blisters(user_id, "trampa", bl)
                        mensajes_exito.extend(bcol)
                    if not db.claim_reward(user_id, "diaria_actividad"):
                        continue
                    extra = f" + {bl} Blister(s) 🃏" if bl else ""
                    mensajes_exito.append(f"**Diario 1 — Actividad + oráculo:** {fmt_toque_sentence(pts)}{extra}")
                    reclamado_algo = True
                elif tipo == "diaria_actividad":
                    mensajes_error.append(
                        "**Diario 1:** no se puede cobrar todavía.\n" + format_diaria_actividad_reclaim_blocked(prog)
                    )

            elif objetivo == "diaria_trampa":
                prog = db.get_progress_diaria(user_id)
                if _diaria_sub_claimed(prog, "completado_diaria_trampa"):
                    if not mute_claimed:
                        mensajes_error.append("Diario 2 (trampa): ya cobrado hoy.")
                    continue
                if _diaria_trampa_ready(prog):
                    pts = int(rewards.get("diaria_trampa") or 0)
                    bl = int(rewards.get("diaria_trampa_blisters") or 0)
                    if pts <= 0 and bl <= 0:
                        mensajes_error.append("Diario 2: falta configuración de recompensa (rewards.diaria_trampa).")
                        continue
                    if pts:
                        db.modify_points(user_id, pts)
                    if bl > 0:
                        _, bcol = db.modify_blisters(user_id, "trampa", bl)
                        mensajes_exito.extend(bcol)
                    if not db.claim_reward(user_id, "diaria_trampa"):
                        continue
                    extra = f" + {bl} Blister(s) 🃏" if bl else ""
                    mensajes_exito.append(f"**Diario 2 — Trampa:** {fmt_toque_sentence(pts)}{extra}")
                    reclamado_algo = True
                elif tipo == "diaria_trampa":
                    mensajes_error.append(
                        "**Diario 2:** no se puede cobrar todavía.\n" + format_diaria_trampa_reclaim_blocked(prog)
                    )

            elif objetivo == "semanal":
                prog = db.get_progress_semanal(user_id)
                if _claimed(prog.get("completado")):
                    if tipo:
                        mensajes_error.append("Semanal: Ya reclamado esta semana.")
                    continue

                if (
                    _pv(prog.get("debate_post")) >= 1
                    and _pv(prog.get("videos_reaccion")) >= 1
                    and _pv(prog.get("media_escrito")) >= 1
                ):
                    recompensa = rewards.get("semanal")
                    if recompensa is None:
                        mensajes_error.append("Semanal: falta configuración de recompensa (rewards.semanal).")
                        continue
                    db.modify_points(user_id, recompensa)
                    _, bcol = db.modify_blisters(user_id, "trampa", 1)
                    mensajes_exito.extend(bcol)
                    db.claim_reward(user_id, "semanal")
                    mensajes_exito.append(f"**Semanal:** {fmt_toque_sentence(int(recompensa))} + 1 Blister 🃏")
                    reclamado_algo = True
                else:
                    if tipo:
                        mensajes_error.append("Semanal: Tareas incompletas.")

            elif objetivo == "semanal_especial":
                prog = db.get_progress_semanal(user_id)
                if _claimed(prog.get("completado_especial")):
                    if tipo:
                        mensajes_error.append("Especial semanal: Ya reclamado.")
                    continue
                ip = _pv(prog.get("impostor_partidas"))
                iv = _pv(prog.get("impostor_victorias"))
                if ip >= 3 and iv >= 1:
                    pts = int(rewards.get("especial_semanal", 400))
                    bl = int(rewards.get("especial_semanal_blisters", 2))
                    db.modify_points(user_id, pts)
                    _, bcol = db.modify_blisters(user_id, "trampa", bl)
                    mensajes_exito.extend(bcol)
                    db.claim_reward(user_id, "semanal_especial")
                    mensajes_exito.append(f"**Especial semanal:** {fmt_toque_sentence(pts)} + {bl} Blisters 🃏")
                    reclamado_algo = True
                else:
                    if tipo:
                        mensajes_error.append("Especial semanal: Necesitás 3 partidas Impostor y 1 victoria como impostor.")

            elif objetivo == "semanal_minijuegos":
                prog = db.get_progress_semanal(user_id)
                if _claimed(prog.get("completado_minijuegos")):
                    if tipo:
                        mensajes_error.append("Minijuegos semanal: Ya reclamado.")
                    continue
                if (
                    _pv(prog.get("mg_ret_roll_apuesta")) >= 1
                    and _pv(prog.get("mg_roll_casual")) >= 1
                    and _pv(prog.get("mg_duelo")) >= 1
                    and _pv(prog.get("mg_voto_dom")) >= 1
                ):
                    pts = int(rewards.get("minijuegos_semanal", 150))
                    bl = int(rewards.get("minijuegos_semanal_blisters", 1))
                    db.modify_points(user_id, pts)
                    _, bcol = db.modify_blisters(user_id, "trampa", bl)
                    mensajes_exito.extend(bcol)
                    db.claim_reward(user_id, "semanal_minijuegos")
                    mensajes_exito.append(f"**Minijuegos semanal:** {fmt_toque_sentence(pts)} + {bl} Blister(s) 🃏")
                    reclamado_algo = True
                else:
                    if tipo:
                        mensajes_error.append("Minijuegos: faltan reto con apuesta, roll casual, duelo y voto.")
        except Exception:
            log.exception("reclaim_rewards falló en objetivo=%s user=%s", objetivo, user_id)
            mensajes_error.append(f"{objetivo}: error interno al cobrar (avisá al staff).")

    return reclamado_algo, mensajes_exito, mensajes_error
