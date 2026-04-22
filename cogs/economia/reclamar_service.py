# Lógica compartida de /aat_reclamar (una sola implementación).
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

TipoReclamo = Optional[Literal["inicial", "diaria", "semanal", "semanal_especial", "semanal_minijuegos"]]


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

            if all(prog[key] >= 1 for key in ["presentacion", "reaccion_pais", "reaccion_rol", "reaccion_social", "reaccion_reglas", "general_mensaje"]):
                recompensa = task_config["rewards"]["inicial"]
                db.modify_points(user_id, recompensa)
                db.modify_blisters(user_id, "trampa", 3)
                db.claim_reward(user_id, "inicial")
                mensajes_exito.append(f"**Inicial:** {recompensa} Puntos + 3 Blisters 🃏")
                reclamado_algo = True
            else:
                if tipo:
                    mensajes_error.append("Inicial: Tareas incompletas.")

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
            tr_ok = tr >= 1 or ts >= 2
            if msg_n >= 10 and rx_n >= 3 and tr_ok:
                recompensa = task_config["rewards"]["diaria"]
                db.modify_points(user_id, recompensa)
                db.modify_blisters(user_id, "trampa", 1)
                db.claim_reward(user_id, "diaria")
                mensajes_exito.append(f"**Diaria:** {recompensa} Puntos + 1 Blister 🃏")
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
                db.modify_blisters(user_id, "trampa", 1)
                db.claim_reward(user_id, "semanal")
                mensajes_exito.append(f"**Semanal:** {recompensa} Puntos + 1 Blister 🃏")
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
                db.modify_blisters(user_id, "trampa", bl)
                db.claim_reward(user_id, "semanal_especial")
                mensajes_exito.append(f"**Especial semanal:** {pts} Puntos + {bl} Blisters 🃏")
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
                db.modify_blisters(user_id, "trampa", bl)
                db.claim_reward(user_id, "semanal_minijuegos")
                mensajes_exito.append(f"**Minijuegos semanal:** {pts} Puntos + {bl} Blister(s) 🃏")
                reclamado_algo = True
            else:
                if tipo:
                    mensajes_error.append("Minijuegos: faltan reto con apuesta, roll casual, duelo y voto.")

    return reclamado_algo, mensajes_exito, mensajes_error
