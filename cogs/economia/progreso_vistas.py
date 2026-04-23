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
    _diaria_sub_claimed,
    _inicial_discord_done,
    _inicial_sub_claimed,
    diaria_actividad_ready,
    diaria_all_claimed,
    diaria_trampa_ready,
    inicial_all_claimed,
    inicial_perfil_max_ready,
    inicial_profile_ready,
)
from .toque_labels import fmt_toque_sentence


def _blister_phrase(n: int) -> str:
    if n <= 0:
        return ""
    return f"**{n}** blister{'es' if n != 1 else ''} 🃏"


def _reward_field_value(pts: int, blisters: int, cmd: str) -> str:
    bits: List[str] = []
    if pts > 0:
        bits.append(fmt_toque_sentence(pts))
    bp = _blister_phrase(blisters)
    if bp:
        bits.append(bp)
    body = " · ".join(bits) if bits else "*(revisá `.env` — puntos en 0)*"
    return f"{body}\n**Cobrar:** `{cmd}`"


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
    "— o `/aat-progreso-iniciacion` · `/aat-progreso-diaria` (*daily*) · `/aat-progreso-semanal` (*weekly*). "
    "**Leyenda / tips:** `?progresoayuda` · `/aat-progreso-ayuda`."
)

_CMD_RECLAMAR = (
    "**Para cobrar premios:** `?reclamar inicial 1` (Discord) · `inicial 2` (perfil mín.) · `inicial 3` (perfil completo) · "
    "`?reclamar diaria 1` (actividad+oráculo) · `diaria 2` (trampa) · "
    "`?reclamar semanal 1` (base) / `2` (especial) / `3` (minijuegos) · `especial 1` · `minijuegos 1` · "
    "códigos **`?reclamar 1`**…**`5`** — o **`/aat-reclamar`** (tipo + referencia)."
)

_LEY_DIARIA = (
    "**Leyenda:** ✅ tarea del día lista · ☑ **ese premio del diario** listo para cobrar (`?reclamar diaria 1` o `2`) · ☐ falta algo.\n"
    "_Son **dos premios** distintos por día; podés cobrar cada uno aparte._\n\n"
)


def _tmark(done: bool) -> str:
    return "✅" if done else "☐"


def _tline(done: bool, label: str, detail: str = "") -> str:
    return f"{_tmark(done)} {label}" + (f" — {detail}" if detail else "")


def _resumen_block_embed(block_title_plain: str, detail: str, *, claimed: bool, ready: bool) -> discord.Embed:
    """Un bloque del resumen `?progreso`: azul = ya cobraste, verde = listo para reclamar, gris = incompleto."""
    if claimed:
        color: discord.Color = discord.Color.blue()
    elif ready:
        color = discord.Color.green()
        detail = f"✅ {detail}"
    else:
        color = discord.Color.light_grey()
    return discord.Embed(
        title=block_title_plain[:256],
        description=detail[:4096],
        color=color,
    )


def build_progreso_ayuda_pages() -> List[List[discord.Embed]]:
    """Texto largo que antes iba en el primer embed de `?progreso` (leyenda, reclamar, slash)."""
    desc = (
        "**Colores en las tarjetas de `?progreso`:**\n"
        "• **Azul** — ya cobraste ese bloque (iniciación tiene **hasta 3** cobros; el diario **2** por día).\n"
        "• **Verde** — hay algo listo para **`?reclamar`** o el botón **Reclamar** del paginador.\n"
        "• **Gris** — falta algo; leé la tarjeta o **Siguiente ▶**.\n\n"
        "**En `?inicial` / `?diaria` / `?semanal` (marcas por ítem):**\n"
        "✅ ítem hecho · ☑ listo para cobrar esa parte · ☐ falta.\n\n"
        + _LEY_DIARIA.strip()
        + "\n\n"
        + _CMD_RECLAMAR
        + "\n\n"
        + _CMD_PROGRESS_HINT
    )
    emb = discord.Embed(
        title="?progresoayuda — Leyenda y comandos",
        description=desc[:4096],
        color=discord.Color.gold(),
    )
    return [[emb]]


def _plain_block_title(biling_label: str) -> str:
    return biling_label.replace("**", "").replace("*", "").replace(" · ", " — ")[:256]


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
    ini_claimed = inicial_all_claimed(ini)
    ini_ready = not ini_claimed and (
        (_inicial_discord_done(ini) and not _inicial_sub_claimed(ini, "completado_inicial_comunidad"))
        or (inicial_profile_ready(db, user_id) and not _inicial_sub_claimed(ini, "completado_inicial_perfil_min"))
        or (inicial_perfil_max_ready(db, user_id) and not _inicial_sub_claimed(ini, "completado_inicial_perfil_max"))
    )
    det_ini = (
        "los **3 premios** de iniciación ya cobrados"
        if ini_claimed
        else (
            "**podés cobrar** alguna parte → `?reclamar inicial 1` · `2` · `3` (o botón **Reclamar iniciación**)"
            if ini_ready
            else "incompleta — `?inicial`"
        )
    )

    dia_claimed = diaria_all_claimed(dia)
    di_ready = not dia_claimed and (
        (diaria_actividad_ready(dia) and not _diaria_sub_claimed(dia, "completado_diaria_actividad"))
        or (diaria_trampa_ready(dia) and not _diaria_sub_claimed(dia, "completado_diaria_trampa"))
    )
    det_dia = (
        f"hoy **ya cobraste** ambas partes ({fecha})"
        if dia_claimed
        else (
            "**podés cobrar** `?reclamar diaria 1` y/o `diaria 2` (o botón **Reclamar diario**)"
            if di_ready
            else f"incompleta — `?diaria` (*{fecha}*)"
        )
    )

    semb_claimed = int(sem.get("completado") or 0) == 1
    semb_ready = not semb_claimed and (
        int(sem.get("debate_post") or 0) >= 1
        and int(sem.get("videos_reaccion") or 0) >= 1
        and int(sem.get("media_escrito") or 0) >= 1
    )
    det_semb = (
        f"sem. **{sl}** — `?reclamar semanal` ya hecho"
        if semb_claimed
        else ("**podés cobrar** → `?reclamar semanal` / `weekly`" if semb_ready else "incompleta — `?semanal`")
    )

    sp_claimed = int(sem.get("completado_especial") or 0) == 1
    sp_ready = not sp_claimed and int(sem.get("impostor_partidas") or 0) >= 3 and int(sem.get("impostor_victorias") or 0) >= 1
    det_sp = (
        "`?reclamar especial` ya hecho"
        if sp_claimed
        else ("**podés cobrar** → `?reclamar especial` / `impostor`" if sp_ready else "incompleta — ver **Especial** en `?semanal`")
    )

    mg_claimed = int(sem.get("completado_minijuegos") or 0) == 1
    det_mg = (
        "`?reclamar minijuegos` ya hecho"
        if mg_claimed
        else (
            "**podés cobrar** → `?reclamar minijuegos` / `minigames`"
            if mg_marks
            else f"{_LBL_SEM_MG} — faltan marcas (ver `?semanal`)"
        )
    )

    blocks: List[discord.Embed] = [
        _resumen_block_embed(_plain_block_title(_LBL_INICIAL), det_ini, claimed=ini_claimed, ready=ini_ready),
        _resumen_block_embed(_plain_block_title(_LBL_DIARIO), det_dia, claimed=dia_claimed, ready=di_ready),
        _resumen_block_embed(_plain_block_title(_LBL_SEM_BASE), det_semb, claimed=semb_claimed, ready=semb_ready),
        _resumen_block_embed(_plain_block_title(_LBL_SEM_ESP), det_sp, claimed=sp_claimed, ready=sp_ready),
        _resumen_block_embed(
            _plain_block_title(f"{_LBL_SEM_MG} (4 marcas)"),
            det_mg,
            claimed=mg_claimed,
            ready=mg_marks and not mg_claimed,
        ),
    ]
    footer = discord.Embed(
        title="📊 Siguientes pasos",
        description=(
            "**Siguiente ▶** (paginador): detalle por bloque — `?inicial` · `?diaria` · `?semanal`.\n\n"
            "Leyenda de colores, diaria/trampa y cómo reclamar: **`?progresoayuda`** · **`/aat-progreso-ayuda`**"
        ),
        color=discord.Color.blurple(),
    )
    blocks.append(footer)
    return [blocks]


def build_pages_inicial(db: Any, task_config: Dict[str, Any], user_id: int) -> List[List[discord.Embed]]:
    prog = db.get_progress_inicial(user_id)
    rw = task_config.get("rewards") or {}
    b1 = int(rw.get("inicial_comunidad_blisters") or 1)
    b2 = int(rw.get("inicial_perfil_min_blisters") or 1)
    b3 = int(rw.get("inicial_perfil_max_blisters") or 1)
    p1, p2, p3 = int(rw.get("inicial_comunidad") or 0), int(rw.get("inicial_perfil_min") or 0), int(rw.get("inicial_perfil_max") or 0)
    total_pts = int(rw.get("inicial") or (p1 + p2 + p3))
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

    if inicial_all_claimed(prog):
        done = discord.Embed(
            title=_title_es_en("Iniciación", "initial / onboarding", "— completada"),
            description=(
                "Todo listo: **comunidad Discord**, **perfil mínimo** y **perfil al tope** ya tienen su premio cobrado.\n\n"
                "**Discord (registro del bot)**\n"
                f"{discord_lines}\n\n"
                "**Perfil mínimo**\n"
                f"{perfil_lines}\n\n"
                "**Perfil al tope (opcional)**\n"
                f"{perfil_amp_lines}\n\n"
                f"{_CMD_PROGRESS_HINT}"
            ),
            color=discord.Color.dark_green(),
        )
        done.set_footer(text="Iniciación · 3/3 partes cobradas · Gracias por completar el onboarding")
        return [[done]]

    e1 = discord.Embed(
        title=_title_es_en("Iniciación", "initial / onboarding", "1/3 — Comunidad"),
        description=(
            "Cuando tengas **todas** las marcas de abajo en ✅, cobrá con el comando del recuadro **Recompensa**.\n\n"
            "**Checklist — Discord**\n"
            f"{discord_lines}"
            f"{hint}"
        ),
        color=discord.Color.blue(),
    )
    e1.add_field(
        name="Recompensa · parte 1",
        value=_reward_field_value(p1, b1, "?reclamar inicial 1"),
        inline=False,
    )
    e1.set_footer(text=f"Iniciación 1/3 · Toque total guía: ~{fmt_toque_sentence(total_pts)} (3 cobros)")

    e2 = discord.Embed(
        title=_title_es_en("Iniciación", "initial / onboarding", "2/3 — Perfil mínimo"),
        description=(
            "**Wishlist, top favoritos y odiados** al mínimo que pide el servidor (no hace falta el tope todavía).\n\n"
            "**Checklist — perfil mínimo**\n"
            f"{perfil_lines}"
            f"{hint}"
        ),
        color=discord.Color.dark_blue(),
    )
    e2.add_field(
        name="Recompensa · parte 2",
        value=_reward_field_value(p2, b2, "?reclamar inicial 2"),
        inline=False,
    )
    e2.set_footer(text="Iniciación 2/3 · Podés cobrar 1 y 2 en cualquier orden cuando cumplan")

    e3 = discord.Embed(
        title=_title_es_en("Iniciación", "initial / onboarding", "3/3 — Perfil completo"),
        description=(
            "Opcional pero con premio: llevá las tres listas hasta el **tope** (wishlist / top / odiados).\n\n"
            "**Progreso hacia el tope**\n"
            f"{perfil_amp_lines}\n\n"
            "_Bonos aparte por top 10 / 30: `/aat-anime-top-guia`._"
            f"{hint}"
        ),
        color=discord.Color.teal(),
    )
    e3.add_field(
        name="Recompensa · parte 3",
        value=_reward_field_value(p3, b3, "?reclamar inicial 3"),
        inline=False,
    )
    e3.set_footer(text="Iniciación 3/3 · Cada parte se cobra cuando cumple su checklist (orden libre salvo Discord = parte 1)")
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
    rw = task_config.get("rewards") or {}
    rw_act = int(rw.get("diaria_actividad") or rw.get("diaria") or 0)
    rw_tr = int(rw.get("diaria_trampa") or 0)
    bl_act = int(rw.get("diaria_actividad_blisters") or 0)
    bl_tr = int(rw.get("diaria_trampa_blisters") or 0)
    hint = f"\n\n{_CMD_RECLAMAR}\n\n{_CMD_PROGRESS_HINT}"
    total_dia = int(rw.get("diaria") or (rw_act + rw_tr))

    if diaria_all_claimed(prog):
        e_done = discord.Embed(
            title=_title_es_en("Diario", "daily", f"{fecha} · listo"),
            description=(
                "Hoy ya cobraste **los dos premios**: actividad + oráculo, y trampa.\n\n"
                "**Resumen del día**\n"
                f"{_tline(msg_ok, 'Mensajes en el servidor', f'{msg_n}/10')}\n"
                f"{_tline(rx_ok, 'Reacciones en el servidor', f'{rx_n}/3')}\n"
                f"{_tline(or_ok, 'Oráculo', f'{or_n}/1')}\n"
                f"{_diaria_trampa_resumen_line(tr, ts)}\n\n"
                f"{hint.strip()}"
            ),
            color=discord.Color.blue(),
        )
        e_done.set_footer(text=f"Diario · {fecha} · ~{fmt_toque_sentence(total_dia)} Toque en total (2 cobros) — ya aplicados")
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
        f"{_tmark(actividad_ok)} **Actividad + oráculo** → listo: **`?reclamar diaria 1`**\n"
        f"{_tmark(tr_ok)} **Trampa** (una carta, con @ o sin objetivo) → **`?reclamar diaria 2`**\n"
        f"{_tmark(diario_tareas_ok)} **Tip:** `?reclamar diaria` sin número cobra **ambas** partes si ya podés."
    )
    desc = (
        f"{_LEY_DIARIA}"
        "**Actividad + oráculo**\n"
        f"{act_lines}\n\n"
        "**Trampa**\n"
        f"{trap_lines}\n\n"
        f"{bloque_listo}"
        f"{hint}"
    )
    if len(desc) > 4000:
        desc = desc[:3997] + "…"
    e_full = discord.Embed(
        title=_title_es_en("Diario", "daily", f"checklist · {fecha}"),
        description=desc,
        color=discord.Color.orange(),
    )
    e_full.add_field(
        name="Premio 1 · Actividad + oráculo",
        value=_reward_field_value(rw_act, bl_act, "?reclamar diaria 1"),
        inline=True,
    )
    e_full.add_field(
        name="Premio 2 · Trampa",
        value=_reward_field_value(rw_tr, bl_tr, "?reclamar diaria 2"),
        inline=True,
    )
    e_full.set_footer(text=f"Diario · ~{fmt_toque_sentence(total_dia)} Toque en total (2 cobros) · Ver `.env` REWARD_DIARIA_*")
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
