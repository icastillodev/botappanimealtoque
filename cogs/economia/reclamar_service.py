# Lógica compartida de /aat-reclamar (una sola implementación).
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from .toque_labels import fmt_toque_sentence

TipoReclamo = Optional[Literal["inicial", "diaria", "semanal", "semanal_especial", "semanal_minijuegos"]]

_CANONICAL_TIPOS = frozenset({"inicial", "diaria", "semanal", "semanal_especial", "semanal_minijuegos"})

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
    "Sin argumento = intenta **todo** lo listo. O un solo tipo: "
    "`inicial` · `diaria` / `diario` / `daily` · `semanal` / `weekly` · "
    "`especial` / `semanal_especial` · `minijuegos` / `semanal_minijuegos` · "
    "`all` / `todo` (= todo)."
)


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


def _inicial_discord_done(prog: Dict[str, Any]) -> bool:
    return all(int(prog.get(k) or 0) >= 1 for k in INICIAL_DISCORD_KEYS)


def _inicial_profile_counts(db: Any, user_id: int) -> Tuple[int, int, int]:
    wl = int(db.wishlist_total_filled(user_id))
    top = int(db.anime_top_count_filled(user_id, INICIAL_TOP_MIN))
    hat = int(db.hated_total_filled(user_id))
    return wl, top, hat


def inicial_profile_ready(db: Any, user_id: int) -> bool:
    wl, top, hat = _inicial_profile_counts(db, user_id)
    return wl >= INICIAL_WISHLIST_MIN and top >= INICIAL_TOP_MIN and hat >= INICIAL_HATED_MIN


def _diaria_prog_ready(prog: Dict[str, Any]) -> bool:
    msg_n = int(prog.get("mensajes_servidor") or 0)
    rx_n = int(prog.get("reacciones_servidor") or 0)
    tr = int(prog.get("trampa_enviada") or 0)
    ts = int(prog.get("trampa_sin_objetivo") or 0)
    tr_ok = tr >= 1 or ts >= 1
    or_n = int(prog.get("oraculo_preguntas") or 0)
    return msg_n >= 10 and rx_n >= 3 and tr_ok and or_n >= 1


def build_reclaim_status_block(db: Any, _task_config: Dict[str, Any], user_id: int) -> str:
    """Resumen legible de las 5 recompensas: ya reclamado / listo / falta."""
    lines: List[str] = []
    pi = db.get_progress_inicial(user_id)
    if int(pi.get("completado") or 0) == 1:
        lines.append("✅ **Inicial** — ya reclamado.")
    elif _inicial_discord_done(pi) and inicial_profile_ready(db, user_id):
        lines.append("☑ **Inicial** — listo · `?reclamar inicial`")
    else:
        lines.append("☐ **Inicial** — incompleto (`?inicial`).")
    pd = db.get_progress_diaria(user_id)
    if int(pd.get("completado") or 0) == 1:
        lines.append("✅ **Diario** (*daily*) — ya reclamado hoy.")
    elif _diaria_prog_ready(pd):
        lines.append("☑ **Diario** — listo · `?reclamar diaria`")
    else:
        lines.append("☐ **Diario** — incompleto (`?diaria`).")
    ps = db.get_progress_semanal(user_id)
    if int(ps.get("completado") or 0) == 1:
        lines.append("✅ **Semanal base** (*weekly*) — ya reclamado.")
    elif int(ps.get("debate_post") or 0) >= 1 and int(ps.get("videos_reaccion") or 0) >= 1 and int(ps.get("media_escrito") or 0) >= 1:
        lines.append("☑ **Semanal base** — listo · `?reclamar semanal`")
    else:
        lines.append("☐ **Semanal base** — incompleto (`?semanal`).")
    if int(ps.get("completado_especial") or 0) == 1:
        lines.append("✅ **Especial Impostor** — ya reclamado.")
    elif int(ps.get("impostor_partidas") or 0) >= 3 and int(ps.get("impostor_victorias") or 0) >= 1:
        lines.append("☑ **Especial Impostor** — listo · `?reclamar especial`")
    else:
        lines.append("☐ **Especial Impostor** — incompleto.")
    mg_ok = (
        int(ps.get("mg_ret_roll_apuesta") or 0) >= 1
        and int(ps.get("mg_roll_casual") or 0) >= 1
        and int(ps.get("mg_duelo") or 0) >= 1
        and int(ps.get("mg_voto_dom") or 0) >= 1
    )
    if int(ps.get("completado_minijuegos") or 0) == 1:
        lines.append("✅ **Minijuegos semanal** — ya reclamado.")
    elif mg_ok:
        lines.append("☑ **Minijuegos semanal** — listo · `?reclamar minijuegos`")
    else:
        lines.append("☐ **Minijuegos semanal** — incompleto.")
    return "\n".join(lines)


def build_inicial_reclaim_hint(db: Any, user_id: int) -> Optional[str]:
    """Si la iniciación sigue pendiente, resume Discord vs perfil (y sugerencia de verificar)."""
    prog = db.get_progress_inicial(user_id)
    if int(prog.get("completado") or 0) == 1:
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
        lines.append("**Podés reclamar:** `/aat-reclamar` → `inicial`.")
    return "\n".join(lines)


def reclaim_rewards(
    db: Any,
    task_config: Dict[str, Any],
    user_id: int,
    tipo: TipoReclamo = None,
) -> Tuple[bool, List[str], List[str]]:
    """
    Devuelve (hubo_reclamo, mensajes_exito, mensajes_error).
    """
    tipos_a_revisar: List[str] = [tipo] if tipo else ["inicial", "diaria", "semanal", "semanal_especial", "semanal_minijuegos"]

    reclamado_algo = False
    mensajes_exito: List[str] = []
    mensajes_error: List[str] = []

    for objetivo in tipos_a_revisar:
        if objetivo == "inicial":
            prog = db.get_progress_inicial(user_id)
            if prog["completado"] == 1:
                if tipo:
                    mensajes_error.append("Inicial: Ya reclamado.")
                continue

            if _inicial_discord_done(prog) and inicial_profile_ready(db, user_id):
                recompensa = task_config["rewards"]["inicial"]
                db.modify_points(user_id, recompensa)
                _, bcol = db.modify_blisters(user_id, "trampa", 3)
                mensajes_exito.extend(bcol)
                db.claim_reward(user_id, "inicial")
                mensajes_exito.append(f"**Inicial:** {fmt_toque_sentence(int(recompensa))} + 3 Blisters 🃏")
                reclamado_algo = True
            else:
                if tipo:
                    partes: List[str] = []
                    if not _inicial_discord_done(prog):
                        partes.append("Discord (presentación, autorol, #general, etc.)")
                    if not inicial_profile_ready(db, user_id):
                        wl_i, top_i, hat_i = _inicial_profile_counts(db, user_id)
                        partes.append(
                            f"perfil: wishlist {wl_i}/{INICIAL_WISHLIST_MIN}, top {top_i}/{INICIAL_TOP_MIN}, "
                            f"odiados {hat_i}/{INICIAL_HATED_MIN}"
                        )
                    err_ini = "Inicial: incompleto — " + " · ".join(partes) + "."
                    if not _inicial_discord_done(prog):
                        err_ini += " " + MSG_TIP_INICIACION_AL_RECLAMAR
                    mensajes_error.append(err_ini)

        elif objetivo == "diaria":
            prog = db.get_progress_diaria(user_id)
            if prog["completado"] == 1:
                if tipo:
                    mensajes_error.append("Diaria: Ya reclamado hoy.")
                continue

            msg_n = int(prog.get("mensajes_servidor") or 0)
            rx_n = int(prog.get("reacciones_servidor") or 0)
            tr = int(prog.get("trampa_enviada") or 0)
            ts = int(prog.get("trampa_sin_objetivo") or 0)
            tr_ok = tr >= 1 or ts >= 1
            or_n = int(prog.get("oraculo_preguntas") or 0)
            or_ok = or_n >= 1
            if msg_n >= 10 and rx_n >= 3 and tr_ok and or_ok:
                recompensa = task_config["rewards"]["diaria"]
                db.modify_points(user_id, recompensa)
                _, bcol = db.modify_blisters(user_id, "trampa", 1)
                mensajes_exito.extend(bcol)
                db.claim_reward(user_id, "diaria")
                mensajes_exito.append(f"**Diaria:** {fmt_toque_sentence(int(recompensa))} + 1 Blister 🃏")
                reclamado_algo = True
            else:
                if tipo:
                    mensajes_error.append("Diaria: Tareas incompletas.")

        elif objetivo == "semanal":
            prog = db.get_progress_semanal(user_id)
            if prog["completado"] == 1:
                if tipo:
                    mensajes_error.append("Semanal: Ya reclamado esta semana.")
                continue

            if prog["debate_post"] >= 1 and prog["videos_reaccion"] >= 1 and prog["media_escrito"] >= 1:
                recompensa = task_config["rewards"]["semanal"]
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
            if int(prog.get("completado_especial") or 0) == 1:
                if tipo:
                    mensajes_error.append("Especial semanal: Ya reclamado.")
                continue
            ip = int(prog.get("impostor_partidas") or 0)
            iv = int(prog.get("impostor_victorias") or 0)
            if ip >= 3 and iv >= 1:
                rw = task_config["rewards"]
                pts = int(rw.get("especial_semanal", 400))
                bl = int(rw.get("especial_semanal_blisters", 2))
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
            if int(prog.get("completado_minijuegos") or 0) == 1:
                if tipo:
                    mensajes_error.append("Minijuegos semanal: Ya reclamado.")
                continue
            if (
                int(prog.get("mg_ret_roll_apuesta") or 0) >= 1
                and int(prog.get("mg_roll_casual") or 0) >= 1
                and int(prog.get("mg_duelo") or 0) >= 1
                and int(prog.get("mg_voto_dom") or 0) >= 1
            ):
                rw = task_config["rewards"]
                pts = int(rw.get("minijuegos_semanal", 150))
                bl = int(rw.get("minijuegos_semanal_blisters", 1))
                db.modify_points(user_id, pts)
                _, bcol = db.modify_blisters(user_id, "trampa", bl)
                mensajes_exito.extend(bcol)
                db.claim_reward(user_id, "semanal_minijuegos")
                mensajes_exito.append(f"**Minijuegos semanal:** {fmt_toque_sentence(pts)} + {bl} Blister(s) 🃏")
                reclamado_algo = True
            else:
                if tipo:
                    mensajes_error.append("Minijuegos: faltan reto con apuesta, roll casual, duelo y voto.")

    return reclamado_algo, mensajes_exito, mensajes_error
