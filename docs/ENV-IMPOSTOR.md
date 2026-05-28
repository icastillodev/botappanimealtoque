# Variables de entorno — Modo Impostor

Referencia rápida para operadores. El código activo está en `cogs/impostor/`.

## Obligatorias en producción

| Variable | Uso |
|----------|-----|
| `IMPOSTOR_CATEGORY_ID` | Categoría donde se crean canales de lobby |
| `IMPOSTOR_FEED_CHANNEL_ID` | Cartelera de partidas abiertas |
| `IMPOSTOR_ADMIN_ROLE_IDS` | Roles que pueden comandos admin del modo |

## Jugadores y cupo

| Variable | Default | Notas |
|----------|---------|--------|
| `IMPOSTOR_MIN_PLAYERS` | 4 | Piso del código: **3** |
| `IMPOSTOR_MAX_PLAYERS` | 50 | **0** = sin tope en UI (∞) |
| `IMPOSTOR_DEFAULT_SLOTS` | — | Cupo al crear sin argumento `jugadores` |

## Tiempos (segundos)

| Variable | Default |
|----------|---------|
| `IMPOSTOR_PRESTART_SECONDS` | 10 |
| `IMPOSTOR_ROLE_REVIEW_SECONDS` | 5 |
| `IMPOSTOR_TURN_SECONDS` | 50 |
| `IMPOSTOR_VOTE_SECONDS` | 180 |
| `IMPOSTOR_REMATCH_WINDOW_SECONDS` | 60 |
| `IMPOSTOR_REMATCH_VOTE_PERCENT` | 50 |
| `IMPOSTOR_MIN_STAY_SECONDS` | 30 |
| `IMPOSTOR_LOBBY_IDLE_CLOSE_SECONDS` | 300 |

## Ops y staff

| Variable | Uso |
|----------|-----|
| `IMPOSTOR_STAFF_LOG_CHANNEL_ID` | Fin de partida, cierres, inactividad |
| `IMPOSTOR_STARTUP_CLEANUP` | `all` limpia canales huérfanos al arrancar |
| `IMPOSTOR_ANNOUNCE_GENERAL` | `1` avisa en #general al crear sala |

## Opcionales

| Variable | Uso |
|----------|-----|
| `IMPOSTOR_SOUND_URL` / `SOCIAL_SOUND_URL` | MP3 al ver rol |
| `IMPOSTOR_SIMPLE_BOTS` | `1` pistas genéricas; `0` derivadas del secreto |
| `IMPOSTOR_CHAR_SOURCE` / `IMPOSTOR_CHAR_BASE` | Banco de personajes |
| `IMPOSTOR_NOTIFY_ROLE_ID` | Rol para @ al llamar jugadores |

## Ranking

Las estadísticas van a `impostor_stats` y el historial reciente a `impostor_game_log` en la **BD de economía** (`economia_db`).

`IMPOSTOR_DB_PATH` en `.env` antiguo **no se usa** — podés borrarlo del servidor.

## Comandos útiles

- Cartelera: canal `IMPOSTOR_FEED_CHANNEL_ID` o `?impostor` / `?lobbys`
- Crear / unirse (desde feed, #general o canal del bot): `?crearsimpostor <nombre>` · `?entrar <nombre>` · `?salir`
- Lista en memoria: `/impostor-activos` · `?impostoractivos`
- Stats: `?impostorstats` · `?impostorrang` · `?impostorhistorial`
- Ayuda: `/helpimpostor` · `?helpimpostor`
- Revancha: host `/revancha` · jugadores `?quierorevancha` o botón **Quiero revancha**

**Economía:** en **#general** (`GENERAL_CHANNEL_ID`), lobbies, cartelera y categoría Impostor no funcionan `?diario`, `?progreso`, `?reclamar` ni `/aat-progreso-*` — usá `BOT_CHANNEL_ID`.

Ver checklist histórico: `docs/checklist-finalizados/CHECKLIST-BACKLOG-BOT-2026-05.md`
