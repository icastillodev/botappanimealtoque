# Embeds de progreso (inicial / diaria / semanal) compartidos por `?inicial`… y `/aat-progreso-*`.
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import discord

from .reclamar_service import (
    INICIAL_HATED_MIN,
    INICIAL_TOP_MIN,
    INICIAL_WISHLIST_MIN,
    PERFIL_HATED_CAP,
    PERFIL_TOP_CAP,
    PERFIL_WISHLIST_CAP,
    _inicial_discord_done,
    inicial_profile_ready,
)
from .toque_labels import fmt_toque_sentence


def _biling(es: str, en: str) -> str:
    """Nombre visible **ES** + *EN* (descripciones / cuerpo de embed)."""
    return f"**{es}** · *{en}*"


def _title_es_en(es: str, en: str, extra: str = "") -> str:
    """Título de embed (sin markdown; Discord no formatea bien negrita en title)."""
    tail = f" {extra}" if extra else ""
    return f"{es} ({en}){tail}".strip()


# Nombres de bloques (ES + EN). El prefijo `?diaria` sigue siendo el comando; en pantalla decimos **Diario**.
_LBL_INICIAL = _biling("Iniciación", "initial / onboarding")
_LBL_DIARIO = _biling("Diario", "daily")
_LBL_SEM_BASE = _biling("Semanal — premio base", "weekly — base reward")
_LBL_SEM_ESP = _biling("Semanal — especial Impostor", "weekly — special (Impostor)")
_LBL_SEM_MG = _biling("Semanal — minijuegos", "weekly — minigames")
_LBL_REC_MG = _biling("Recompensa minijuegos", "minigames reward")

_CMD_PROGRESS_HINT = (
    "**Para repasar tu estado:** `?inicial` · `?diaria` (*daily*) · `?semanal` (*weekly*) · `?progreso` "
    "— o `/aat-progreso-iniciacion` · `/aat-progreso-diaria` (*daily*) · `/aat-progreso-semanal` (*weekly*)."
)

_CMD_RECLAMAR = (
    "**Para cobrar premios:** `?reclamar inicial` · `?reclamar diaria` / `daily` · `?reclamar semanal` / `weekly` · "
    "`?reclamar especial` · `?reclamar minijuegos` — o **`/aat-reclamar`** y elegís el tipo."
)

_LEY_DIARIA = (
    "**Leyenda:** ✅ tarea del día lista · ☑ **todo el diario** listo para cobrar → **`?reclamar diaria`** · ☐ falta algo.\n"
    "_Si ya cobraste hoy, esta tarjeta se muestra en **azul**._\n\n"
)


def _tmark(done: bool) -> str:
    return "✅" if done else "☐"


def _tline(done: bool, label: str, detail: str = "") -> str:
    return f"{_tmark(done)} {label}" + (f" — {detail}" if detail else "")


def _resumen_glyphe(claimed: bool, ready: bool) -> str:
    """✅ ya cobrado · ☑ listo para cobrar · ☐ falta."""
    if claimed:
        return "✅"
    if ready:
        return "☑"
    return "☐"


def _resumen_line(glyph: str, label: str, detail: str = "") -> str:
    return f"{glyph} {label}" + (f" — {detail}" if detail else "")


def _diaria_trampa_section(tr: int, ts: int) -> str:
    """Bloque de texto: la trampa diaria es UNA tarea con dos formas válidas (XOR), no dos acumulables."""
    tr_ok = tr >= 1 or ts >= 1
    intro = (
        "**Trampa (*trap*):** **una** carta — **dirigida** (`?usar` + **@** mención) **o** **sin objetivo** (sola).\n"
        "**Regla:** es **una u otra** — alcanza **un** uso válido; **no** hace falta completar las dos líneas.\n\n"
    )
    if tr_ok:
        bits: List[str] = []
        if tr >= 1:
            bits.append("**con @ / mención** (*with mention*)")
        if ts >= 1:
            bits.append("**sin objetivo** (*no target*)")
        reg = " · ".join(bits)
        note = ""
        if tr >= 1 and ts >= 1:
            note = (
                "\n_Si ves las dos formas, es porque hubo registro de ambas en el día; "
                "para la diaria **igual alcanzaba con una sola**._\n"
            )
        return intro + f"✅ **Estado trampa:** lista — vía: {reg}.{note}\n"
    body = "\n".join(
        [
            "☐ **Estado trampa:** pendiente.",
            "",
            "**Dos formas** (*elegí **solo una**; con que una marque ✅, la trampa cuenta*):",
            _tline(tr >= 1, "**Con @** — dirigida (`?usar` + mención)", f"{tr}/1"),
            _tline(ts >= 1, "**Sin objetivo** — carta sola", f"{ts}/1"),
            "",
            "_Los **0/1** son referencia por tipo; **no** son dos trampas obligatorias._",
        ]
    )
    return intro + body + "\n"


def _diaria_trampa_resumen_line(tr: int, ts: int) -> str:
    """Una línea para el embed de diario ya reclamada."""
    tr_ok = tr >= 1 or ts >= 1
    if not tr_ok:
        return _tline(False, "**Trampa** (*trap*)", "pendiente (raro si ya reclamaste)")
    bits: List[str] = []
    if tr >= 1:
        bits.append("con @")
    if ts >= 1:
        bits.append("sin objetivo")
    return _tline(True, "**Trampa** (*trap*) — **una** vía alcanza", " · ".join(bits))


_INICIAL_DISCORD_TASKS: List[Tuple[str, str]] = [
    ("presentacion", "Post de **presentación**"),
    ("reaccion_pais", "**Reacción** en país / **autorol**"),
    ("reaccion_rol", "**Reacción** para rol (p. ej. pronombres)"),
    ("reaccion_social", "**Reacción** en redes / social"),
    ("reaccion_reglas", "**Reacción** en **reglas**"),
    ("general_mensaje", "**Al menos 1 mensaje** en **#general**"),
]


def flatten_embed_pages(pages: List[List[discord.Embed]]) -> List[discord.Embed]:
    """Une páginas de un solo embed cada una en una lista plana (máx. usar en un solo mensaje si ≤10)."""
    return [e for part in pages for e in part]


def build_progreso_resumen_pages(db: Any, task_config: Dict[str, Any], user_id: int) -> List[List[discord.Embed]]:
    """Primera pantalla de `?progreso`: qué bloques ya están bien / reclamados."""
    fecha, semana = db.get_current_date_keys()
    sl = semana.split("-")[-1]
    ini = db.get_progress_inicial(user_id)
    dia = db.get_progress_diaria(user_id)
    sem = db.get_progress_semanal(user_id)
    mg_marks = (
        int(sem.get("mg_ret_roll_apuesta") or 0) >= 1
        and int(sem.get("mg_roll_casual") or 0) >= 1
        and int(sem.get("mg_duelo") or 0) >= 1
        and int(sem.get("mg_voto_dom") or 0) >= 1
    )
    ini_claimed = int(ini.get("completado") or 0) == 1
    ini_ready = not ini_claimed and _inicial_discord_done(ini) and inicial_profile_ready(db, user_id)
    g_ini = _resumen_glyphe(ini_claimed, ini_ready)
    det_ini = (
        "premio **ya cobrado** (`?reclamar inicial` no aplica)"
        if ini_claimed
        else ("**podés cobrar** → `?reclamar inicial`" if ini_ready else "incompleta — `?inicial`")
    )

    dia_claimed = int(dia.get("completado") or 0) == 1
    di_ready = not dia_claimed and (
        int(dia.get("mensajes_servidor") or 0) >= 10
        and int(dia.get("reacciones_servidor") or 0) >= 3
        and int(dia.get("oraculo_preguntas") or 0) >= 1
        and (int(dia.get("trampa_enviada") or 0) >= 1 or int(dia.get("trampa_sin_objetivo") or 0) >= 1)
    )
    g_dia = _resumen_glyphe(dia_claimed, di_ready)
    det_dia = (
        f"hoy **ya cobraste** ({fecha}) — `?reclamar diaria` no aplica"
        if dia_claimed
        else ("**podés cobrar** → `?reclamar diaria` / `daily` o botón **Reclamar diario**" if di_ready else f"incompleta — `?diaria` (*{fecha}*)")
    )

    semb_claimed = int(sem.get("completado") or 0) == 1
    semb_ready = not semb_claimed and (
        int(sem.get("debate_post") or 0) >= 1
        and int(sem.get("videos_reaccion") or 0) >= 1
        and int(sem.get("media_escrito") or 0) >= 1
    )
    g_semb = _resumen_glyphe(semb_claimed, semb_ready)
    det_semb = (
        f"sem. **{sl}** — `?reclamar semanal` ya hecho"
        if semb_claimed
        else ("**podés cobrar** → `?reclamar semanal` / `weekly`" if semb_ready else "incompleta — `?semanal`")
    )

    sp_claimed = int(sem.get("completado_especial") or 0) == 1
    sp_ready = not sp_claimed and int(sem.get("impostor_partidas") or 0) >= 3 and int(sem.get("impostor_victorias") or 0) >= 1
    g_sp = _resumen_glyphe(sp_claimed, sp_ready)
    det_sp = (
        "`?reclamar especial` ya hecho"
        if sp_claimed
        else ("**podés cobrar** → `?reclamar especial` / `impostor`" if sp_ready else "incompleta — ver **Especial** en `?semanal`")
    )

    mg_claimed = int(sem.get("completado_minijuegos") or 0) == 1
    g_mg = _resumen_glyphe(mg_claimed, mg_marks and not mg_claimed)
    det_mg = (
        "`?reclamar minijuegos` ya hecho"
        if mg_claimed
        else (
            "**podés cobrar** → `?reclamar minijuegos` / `minigames`"
            if mg_marks
            else f"{_LBL_SEM_MG} — faltan marcas (ver `?semanal`)"
        )
    )

    lines = [
        _resumen_line(g_ini, _LBL_INICIAL, det_ini),
        _resumen_line(g_dia, _LBL_DIARIO, det_dia),
        _resumen_line(g_semb, _LBL_SEM_BASE, det_semb),
        _resumen_line(g_sp, _LBL_SEM_ESP, det_sp),
        _resumen_line(g_mg, f"{_LBL_SEM_MG} (4 marcas)", det_mg),
    ]
    body = (
        "**Leyenda:** ✅ ya cobraste ese premio · ☑ **listo para cobrar** (usá el comando o el botón verde) · ☐ falta tarea.\n\n"
        + "\n".join(lines)
        + "\n\n**Siguiente ▶** detalle con marcas por ítem en `?inicial`, `?diaria` y `?semanal`.\n\n"
        + _CMD_RECLAMAR
        + "\n\n"
        + _CMD_PROGRESS_HINT
    )
    emb = discord.Embed(title="📊 Progreso — resumen", description=body, color=discord.Color.dark_green())
    return [[emb]]


def build_pages_inicial(db: Any, task_config: Dict[str, Any], user_id: int) -> List[List[discord.Embed]]:
    prog = db.get_progress_inicial(user_id)
    ini_pts = int((task_config.get("rewards") or {}).get("inicial") or 0)
    pie = f"Premio: {fmt_toque_sentence(ini_pts)} + 3 blisters → **`?reclamar inicial`** (Discord + perfil)."
    discord_lines = "\n".join(
        _tline(int(prog.get(key) or 0) == 1, label) for key, label in _INICIAL_DISCORD_TASKS
    )
    wl = int(db.wishlist_total_filled(user_id))
    top10 = int(db.anime_top_count_filled(user_id, INICIAL_TOP_MIN))
    hat = int(db.hated_total_filled(user_id))
    wl_ok = wl >= INICIAL_WISHLIST_MIN
    top_ok = top10 >= INICIAL_TOP_MIN
    hat_ok = hat >= INICIAL_HATED_MIN
    perfil_lines = "\n".join(
        [
            _tline(wl_ok, f"**Wishlist** (mín. {INICIAL_WISHLIST_MIN})", f"{wl}/{INICIAL_WISHLIST_MIN}"),
            _tline(top_ok, f"**Top favoritos** (pos. 1–{INICIAL_TOP_MIN})", f"{top10}/{INICIAL_TOP_MIN}"),
            _tline(hat_ok, f"**Odiados** (mín. {INICIAL_HATED_MIN})", f"{hat}/{INICIAL_HATED_MIN}"),
        ]
    )
    top_cap = int(db.anime_top_count_filled(user_id, PERFIL_TOP_CAP))
    wl_show = min(wl, PERFIL_WISHLIST_CAP)
    hat_show = min(hat, PERFIL_HATED_CAP)
    perfil_amp_lines = "\n".join(
        [
            _tline(wl_show >= PERFIL_WISHLIST_CAP, "**Wishlist** (tope opcional)", f"{wl_show}/{PERFIL_WISHLIST_CAP}"),
            _tline(top_cap >= PERFIL_TOP_CAP, "**Top anime** (tope opcional)", f"{top_cap}/{PERFIL_TOP_CAP}"),
            _tline(hat_show >= PERFIL_HATED_CAP, "**Odiados** (tope opcional)", f"{hat_show}/{PERFIL_HATED_CAP}"),
        ]
    )
    hint = f"\n\n{_CMD_PROGRESS_HINT}"

    if int(prog.get("completado") or 0) == 1:
        done = discord.Embed(
            title=_title_es_en("Iniciación", "initial / onboarding"),
            description=(
                "✅ **Ya reclamaste** la iniciación (premio cobrado con **`?reclamar inicial`**).\n\n"
                "**Último registro del bot (Discord):**\n"
                f"{discord_lines}\n\n"
                "**Perfil (mínimo, al momento de reclamar):**\n"
                f"{perfil_lines}\n\n"
                f"{_CMD_PROGRESS_HINT}"
            ),
            color=discord.Color.green(),
        )
        return [[done]]

    e1 = discord.Embed(
        title=_title_es_en("Iniciación", "initial / onboarding", "— Discord"),
        description=(
            "**Marcá con reacciones / mensajes** lo que pida el staff en cada canal (presentación, autorol, redes, reglas, #general).\n\n"
            f"{discord_lines}\n\n"
            f"_{pie}_{hint}"
        ),
        color=discord.Color.blue(),
    )
    e2 = discord.Embed(
        title=_title_es_en("Iniciación", "initial / onboarding", "— perfil (mínimo para reclamar)"),
        description=(
            "**Completá en el perfil** (slash o `?topset` / listas) antes de reclamar:\n\n"
            f"{perfil_lines}\n\n"
            f"_{pie}_{hint}"
        ),
        color=discord.Color.dark_blue(),
    )
    e3 = discord.Embed(
        title="Perfil ampliado (opcional)",
        description=(
            "Solo **progreso** hacia el tope del perfil; **no suma otra misión** aparte del mínimo de arriba.\n\n"
            f"{perfil_amp_lines}\n\n"
            "_Bonos del top 10 / 30: `/aat-anime-top-guia`._\n"
            f"{hint}"
        ),
        color=discord.Color.teal(),
    )
    return [[e1], [e2], [e3]]


def build_pages_diaria(db: Any, task_config: Dict[str, Any], user_id: int) -> List[List[discord.Embed]]:
    fecha, _ = db.get_current_date_keys()
    prog = db.get_progress_diaria(user_id)
    msg_n = int(prog.get("mensajes_servidor") or 0)
    rx_n = int(prog.get("reacciones_servidor") or 0)
    tr = int(prog.get("trampa_enviada") or 0)
    ts = int(prog.get("trampa_sin_objetivo") or 0)
    or_n = int(prog.get("oraculo_preguntas") or 0)
    or_ok = or_n >= 1
    msg_ok = msg_n >= 10
    rx_ok = rx_n >= 3
    actividad_ok = msg_ok and rx_ok and or_ok
    tr_ok = tr >= 1 or ts >= 1
    diario_tareas_ok = actividad_ok and tr_ok
    rw_pts = int((task_config.get("rewards") or {}).get("diaria") or 0)
    premio_txt = (
        f"Premio del día: **{fmt_toque_sentence(rw_pts)}** + 1 blister — cobrá con **`?reclamar diaria`** / `daily` "
        f"o el botón **Reclamar diario** (solo cuando **☑** abajo)."
    )
    hint = f"\n\n{_CMD_RECLAMAR}\n\n{_CMD_PROGRESS_HINT}"

    if int(prog.get("completado") or 0) == 1:
        e_done = discord.Embed(
            title=_title_es_en("Diario", "daily", f"· {fecha} · ya cobrado"),
            description=(
                "**Estado:** ✅ **Ya reclamaste** el diario de hoy (*daily claimed*).\n\n"
                "**Leyenda de abajo:** ✅ hecho hoy · ☑ sería listo para cobrar (ya no aplica) · ☐ no aplica.\n\n"
                "**Checklist del día (histórico):**\n"
                f"{_tline(msg_ok, '**10 mensajes** en el servidor', f'{msg_n}/10')}\n"
                f"{_tline(rx_ok, '**3 reacciones** en el servidor', f'{rx_n}/3')}\n"
                f"{_tline(or_ok, '**1× oráculo**', f'{or_n}/1')}\n"
                f"{_diaria_trampa_resumen_line(tr, ts)}\n\n"
                f"{hint.strip()}"
            ),
            color=discord.Color.blue(),
        )
        return [[e_done]]

    act_lines = "\n".join(
        [
            _tline(msg_ok, "**10 mensajes** en el servidor (cualquier canal que cuente)", f"{msg_n}/10"),
            _tline(rx_ok, "**3 reacciones** en el servidor", f"{rx_n}/3"),
            _tline(
                or_ok,
                "**1 consulta al oráculo** (@bot + pregunta · `?pregunta` · `/aat-consulta`)",
                f"{or_n}/1",
            ),
        ]
    )
    trap_lines = _diaria_trampa_section(tr, ts)
    bloque_listo = (
        f"{_tmark(actividad_ok)} **Bloque actividad + oráculo** — listo cuando las tres líneas están en ✅.\n"
        f"{_tmark(tr_ok)} **Bloque trampa** — listo con **una** carta (**con @** y/o **sin objetivo**; alcanza una vía).\n"
        f"{_tmark(diario_tareas_ok)} **Todo el diario** — cuando los dos bloques están en ✅ → **`?reclamar diaria`**."
    )
    desc = (
        f"{_LEY_DIARIA}"
        f"**Parte 1 — Actividad y oráculo**\n{act_lines}\n\n"
        f"**Parte 2 — Trampa (una carta)**\n{trap_lines}\n\n"
        f"{bloque_listo}\n\n"
        f"_{premio_txt}_"
        f"{hint}"
    )
    if len(desc) > 4000:
        desc = desc[:3997] + "…"
    e_full = discord.Embed(
        title=_title_es_en("Diario", "daily", f"— checklist · {fecha}"),
        description=desc,
        color=discord.Color.orange(),
    )
    return [[e_full]]


def build_pages_semanal(db: Any, task_config: Dict[str, Any], user_id: int) -> List[List[discord.Embed]]:
    _, semana = db.get_current_date_keys()
    prog = db.get_progress_semanal(user_id)
    rw = task_config.get("rewards") or {}
    chans = task_config.get("channels") or {}
    vid_id = int(chans.get("videos") or 0)
    vid_mention = f"<#{vid_id}>" if vid_id else ""
    sl = semana.split("-")[-1]
    ip = int(prog.get("impostor_partidas") or 0)
    iv = int(prog.get("impostor_victorias") or 0)
    media_n = int(prog.get("media_escrito") or 0)
    media_ok = media_n >= 1
    df = int(prog.get("debate_post") or 0)
    dv = int(prog.get("videos_reaccion") or 0)
    df_ok = df >= 1
    dv_ok = dv >= 1
    base_ok = media_ok and df_ok and dv_ok
    sem_done = int(prog.get("completado") or 0) == 1
    pie_sem = (
        "✅ Premio **semanal base** (*weekly base*) ya reclamado (`?reclamar semanal`)."
        if sem_done
        else f"**Premio base (una vez)** — *weekly base*: {fmt_toque_sentence(int(rw.get('semanal') or 0))} + 1 blister — **`?reclamar semanal`** cuando las tres tareas estén en ✅."
    )
    hint = f"\n\n{_CMD_PROGRESS_HINT}"
    e1 = discord.Embed(
        title=_title_es_en("Semanal", "weekly", f"— memes / fanart (sem. {sl})"),
        description=(
            f"{_tline(media_ok, '**Media:** publicación en memes / fanarts / creación (según el servidor)', f'{media_n}/1')}\n\n"
            f"_{pie_sem}_{hint}"
        ),
        color=discord.Color.purple(),
    )
    e1.set_footer(text="Cobrar premio base: ?reclamar semanal · /aat-reclamar → semanal")
    foro_vid = "\n".join(
        [
            _tline(df_ok, "**Foro:** hilo en debate (anime o manga)", f"{df}/1"),
            _tline(
                dv_ok,
                f"{vid_mention} — reaccionar a **un** mensaje" if vid_mention else "**#videos-nuevos** — reaccionar a **un** mensaje",
                f"{dv}/1",
            ),
            _tline(base_ok, "**Las tres** (media + foro + **#videos-nuevos**) listas para el premio base", ""),
        ]
    )
    e2 = discord.Embed(
        title=_title_es_en("Semanal", "weekly", f"— foro y #videos-nuevos (sem. {sl})"),
        description=(
            f"{foro_vid}\n\n"
            f"_{pie_sem}_{hint}"
        ),
        color=discord.Color.dark_purple(),
    )
    e2.set_footer(text="Cobrar premio base: ?reclamar semanal · /aat-reclamar → semanal")
    imp_done = int(prog.get("completado_especial") or 0) == 1
    pie_imp = (
        "✅ **Especial Impostor** (*weekly special*) ya reclamado (`?reclamar especial`)."
        if imp_done
        else f"**Premio aparte** — *special*: {fmt_toque_sentence(int(rw.get('especial_semanal', 400)))} — completá las dos líneas y **`?reclamar especial`** (alias `impostor`)."
    )
    ip_ok = ip >= 3
    iv_ok = iv >= 1
    imp_lines = "\n".join(
        [
            _tline(ip_ok, "**3 partidas** de Impostor (terminadas)", f"{ip}/3"),
            _tline(iv_ok, "**1 victoria** como **impostor**", f"{iv}/1"),
        ]
    )
    e3 = discord.Embed(
        title=_title_es_en("Semanal — especial Impostor", "weekly special", f"· sem. {sl}"),
        description=(
            f"{imp_lines}\n\n"
            f"_{pie_imp}_{hint}"
        ),
        color=discord.Color.dark_red(),
    )
    e3.set_footer(text="Cobrar especial: ?reclamar especial · /aat-reclamar → semanal_especial")
    ra = int(prog.get("mg_ret_roll_apuesta") or 0)
    rc = int(prog.get("mg_roll_casual") or 0)
    du = int(prog.get("mg_duelo") or 0)
    vo = int(prog.get("mg_voto_dom") or 0)
    pie_mg = (
        "✅ **Minijuegos** (*minigames*) ya reclamados (`?reclamar minijuegos`)."
        if int(prog.get("completado_minijuegos") or 0) == 1
        else (
            f"**Premio aparte** — *minigames*: {fmt_toque_sentence(int(rw.get('minijuegos_semanal', 150)))} + {rw.get('minijuegos_semanal_blisters', 1)} blister(s) — "
            "**`?reclamar minijuegos`** cuando las cuatro marcas estén en ✅."
        )
    )
    mg_lines = "\n".join(
        [
            _tline(ra >= 1, "Reto con apuesta (roll / duelo)", "`/aat-roll-retar` o `/aat-duelo-retar`"),
            _tline(rc >= 1, "Roll casual", "`/aat-roll` o `?roll`"),
            _tline(du >= 1, "Duelo completado", "`/aat-duelo-aceptar`"),
            _tline(vo >= 1, "Voto semanal", "`/aat-voto-semanal`"),
        ]
    )
    e4 = discord.Embed(
        title=_title_es_en("Semanal — minijuegos", "weekly minigames", f"(sem. {sl})"),
        description=(
            f"{mg_lines}\n\n"
            f"_{pie_mg}_{hint}"
        ),
        color=discord.Color.teal(),
    )
    e4.set_footer(text="Cobrar minijuegos: ?reclamar minijuegos · /aat-reclamar → semanal_minijuegos")
    return [[e1], [e2], [e3], [e4]]
