# Checklist backlog — Bot Anime Altoque (archivado)

**Cerrado:** 2026-05-28. Todos los ítems del pedido original (trivia, impostor, presentaciones, jueves, pala) quedaron implementados en `cogs/`.

**Checklist activo / ideas nuevas:** [`../CHECKLIST-BACKLOG-BOT.md`](../CHECKLIST-BACKLOG-BOT.md)  
**Env Impostor:** [`../ENV-IMPOSTOR.md`](../ENV-IMPOSTOR.md)

---

Lista histórica. Marcar `[x]` al cerrar en código/staging.

**Última actualización:** 2026-05-28
---

## Trivia

- [x] Ventana horaria **07:00–21:00** (America/Montevideo) para sorteos automáticos *(antes 12:00–22:00)*
- [x] Preguntas más difíciles (AniList: `TRIVIA_ANILIST_DIFFICULTY` default 0.55)
- [x] Seguir usando AniList como fuente principal (`TRIVIA_USE_ANILIST`, `trivia_anilist.py`)

---

## Impostor — reglas y balance

- [x] **Varios impostores:** botón +/- en lobby; máx. `min(n-2, n// 3)` (4→1, 6→2, 9→3…)
- [x] Fin de partida si **salen todos los impostores** o impostores vivos con **≤2 sociales**
- [x] Mínimo configurable (`IMPOSTOR_MIN_PLAYERS`, default 4, **piso 3**); máximo por env/cupo
- [x] Cuenta regresiva al pulsar **Comenzar:** **10 s** (`IMPOSTOR_PRESTART_SECONDS`)
- [x] Cuenta regresiva tras **Listo** (roles vistos): **5 s** (`IMPOSTOR_ROLE_REVIEW_SECONDS`)
- [x] Antes de repartir roles: anunciar **N impostores / N sociales** y **condiciones de victoria**
- [x] Campo **`detalle`** en el secreto/rol (embed efímero)

---

## Impostor — lobby y UX

- [x] Al crear lobby: mensaje fijo con **cómo se juega**
- [x] **Un lobby por usuario:** `get_lobby_by_user` en `/crearsimpostor` y `/entrar`
- [x] Host: **forzar inicio** (botón ⚡; el Ready de roles **no** se fuerza)
- [x] Al terminar: host **Cerrar sala** → borra canal
- [x] Host **Cerrar sala** en lobby (antes de jugar) y al terminar partida
- [x] Último humano sale → canal borrado; host que sale transfiere rol

---

## Impostor — chat y turnos

- [x] Fase de pista: solo quien tiene el turno (resto: mensajes borrados)
- [x] Pista: `/palabra` **o** 1–5 palabras sin comando
- [x] Eliminados: sin chat en principal + **hilo** `Eliminados — ronda N`
- [x] Al declarar ganador: permisos de escritura restaurados
- [x] Votación: botones **o** `/votar` / `/vote`

---

## Impostor — ranking (global + personal)

- [x] BD: tabla `impostor_stats`
- [x] `/impostor-stats` y `/impostor-ranking`
- [x] Registrar al finalizar en `endgame` / `db_manager`

---

## Presentaciones

- [x] Quien **escribe** en `PRESENTACION_CHANNEL_ID` (chat) → Chūnin
- [x] Env: `PRESENTACION_CHANNEL_ID` (alias legacy `TRIGGER_CHANNEL_ID_PRESENTACION`)

---

## Feliz Jueves

- [x] Cada **jueves 08:00** Uruguay → `#general` + short YouTube
- [x] Reply al post → ~50 frases aleatorias
- [x] Persistencia vía `economia_db.bot_meta`

---

## Pala (`?pala` / palabra “pala”)

- [x] **100** frases en `data/pala_respuestas.py`
- [x] **20** preguntas (~14% de probabilidad)
- [x] Cooldown actual mantenido

---

## Impostor — polish (env ya en servidor)

- [x] `IMPOSTOR_SOUND_URL` / `SOCIAL_SOUND_URL` al ver rol (MP3 ephemeral o enlace)
- [x] `IMPOSTOR_SIMPLE_BOTS` — pistas variadas por temática (0 = bots “inteligentes”)
- [x] Log staff cuando el host **cierra sala** manualmente

---

## Post-partida y anti-grief

- [x] Botón **Revancha (host)** — reinicia lobby en la misma sala (`reset_for_rematch`)
- [x] **Quiero revancha** — mayoría de humanos reinicia sin esperar al host
- [x] `/revancha` y `?revancha` (solo host, fase fin)
- [x] Ventana `IMPOSTOR_REMATCH_WINDOW_SECONDS` antes del auto-cleanup
- [x] `IMPOSTOR_MIN_STAY_SECONDS` — no salir antes de X s (join o inicio de partida; host exento)

---

## Mantenimiento / ops

- [x] Cierre automático de lobby **inactivo** (`IMPOSTOR_LOBBY_IDLE_CLOSE_SECONDS`, default 300s)
- [x] Log de partida en canal staff (`IMPOSTOR_STAFF_LOG_CHANNEL_ID`)
- [x] Log staff también al cerrar lobby por **inactividad**
- [x] Ayuda `/helpimpostor` actualizada (reglas 2026)
- [x] `?impostorrang` — ranking por prefijo
- [x] `?helpimpostor` — ayuda por prefijo
- [x] `IMPOSTOR_MIN_PLAYERS=3` respetado (sin forzar mínimo 4)
- [x] `respcogsimpostor/` marcado como copia legacy (no cargada)

---

## Referencia rápida de archivos

| Área | Archivos |
|------|----------|
| Trivia | `cogs/economia/trivia_cog.py`, `trivia_anilist.py` |
| Impostor | `cogs/impostor/*.py` |
| Presentaciones | `cogs/presentaciones.py` |
| Pala | `cogs/pala_cog.py`, `data/pala_respuestas.py` |
| Jueves | `cogs/jueves_cog.py` |

---

## Progreso de esta sesión

- [x] Checklist creado
- [x] Trivia 7–21, impostor UX/timer/chat, jueves, pala, presentación **chat**, detalle rol
- [x] Multi-impostor, ranking BD, cerrar lobby host
- [x] `IMPOSTOR_MAX_PLAYERS=0` → sin tope (muestra ∞ en HUD/cartelera)
- [x] Idle close, staff log, ayuda 2026, `?impostorrang`
- [x] Min jugadores 3 vía env, `?helpimpostor`, log idle staff
- [x] Revancha host + MIN_STAY anti-salida rápida
- [x] Sonidos de rol, bots con pistas, log cierre host
- [x] Revancha por mayoría, `/revancha`, log cierre lobby idle

---

## Limpieza repo

- [x] Eliminado código duplicado en `respcogsimpostor/impostor/` y `respcogsimpostor/economia/` (queda `README.md`)
