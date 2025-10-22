# Bot de Discord: Modo "Impostor"

Este bot implementa el modo de juego "Impostor", un juego de deducción social para tu servidor de Discord, construido con `discord.py`.

El juego está diseñado para 5 jugadores (humanos o bots). Un jugador es asignado como el **Impostor**, mientras que los otros 4 son **Sociales**. Los Sociales reciben un personaje secreto (ej: "Naruto Uzumaki"), pero el Impostor no.

El objetivo de los Sociales es descubrir al Impostor. El objetivo del Impostor es fingir que conoce al personaje y evitar ser descubierto.

## 1. Configuración del Entorno

### Requisitos

- Python 3.11+
- Las librerías de Python listadas en `requirements.txt`.

### Instalación de Librerías

1.  Crea un archivo `requirements.txt` en la raíz del proyecto con el siguiente contenido:

    ```txt
    discord.py>=2.3.0
    python-dotenv
    aiohttp
    ```

2.  Instala estas librerías usando pip:
    ```bash
    pip install -r requirements.txt
    # o si usas python3
    python3 -m pip install -r requirements.txt
    ```

### El archivo `.env`

Crea un archivo llamado `.env` en la misma carpeta que tu `main.py`. Este archivo guarda tus claves secretas y IDs de configuración.

Copia la siguiente plantilla y **rellena los valores** con los IDs correctos de tu servidor de Discord.

**Importante:** Para que el modo **Impostor** funcione, las variables cruciales que *debes* configurar son:
* `DISCORD_TOKEN`
* `IMPOSTOR_CATEGORY_ID` (El ID de la categoría donde se crearán las partidas)
* `IMPOSTOR_FEED_CHANNEL_ID` (El ID del canal donde irá la cartelera de lobbys)
* `IMPOSTOR_ADMIN_ROLE_IDS` (Roles que pueden usar comandos admin, ej: ID de tu rol "Admin")
* `IMPOSTOR_CHAR_SOURCE` (La URL de tu base de datos de personajes)

```env
# ========================
# Credenciales del bot
# ========================

# Token del bot (OBLIGATORIO)
DISCORD_TOKEN=AQUITUTOKENSECRETO

# Guild (Server) ID donde probás/sincronizás
GUILD_ID=1361043697260822621

# ========================
# Presentaciones / Roles
# ========================
TRIGGER_CHANNEL_ID_PRESENTACION=1426968063026397295
BOT_ROLE_ID=1426970337530347563
HOKAGE_ROLE_ID=1426968325841489980
ANBU_ROLE_ID=1426977638639206400
SANIN_ROLE_ID=1426977662332833812
AKATSUKI_ROLE_ID=1426977797405937785
CHUNIN_ROLE_ID=1426968362344386590
JONIN_ROLE_ID=1426977756067135720

############## ECONOMIA -----------------
#######################################
ECONOMY_DB_PATH=./data/economy.db
ECONOMY_CURRENCY=🌀
ECONOMY_CHANNEL_ID=1426984140019994856

POINTS_PER_MESSAGE=1
MESSAGE_POINTS_COOLDOWN_SECONDS=60
POINTS_PER_REACTION=0
STARTING_BALANCE=0
LEADERBOARD_SIZE=10
DAILY_EARN_CAP=0

# ---- DIARIAS ----
DAILY_COMMENT_TARGET=5
DAILY_COMMENT_POINTS=50
DAILY_VIDEO_CHANNEL_ID=1426986895250030752
DAILY_VIDEO_REACT_POINTS=30

# ---- SEMANALES ----
WEEKLY_THREAD_CHANNEL_IDS=1426986922328330341,1426986940049264791
WEEKLY_MEDIA_CHANNEL_IDS=1426986977198342306,1426987004016590949,1426987038254563381
WEEKLY_THREAD_POINTS=80
WEEKLY_MEDIA_POINTS=80

# ====== WORDLE (diaria) ======
WORDLE_CHANNEL_ID=1427000708233691228
WORDLE_POINTS=50

# ====== INICIACIÓN (one-shot, +50 c/u) ======
INIT_PRESENTED_POINTS=50
INIT_SOCIALS_MESSAGE_ID=1427000940602327123
INIT_SOCIALS_POINTS=50
INIT_THREAD_CHANNEL_IDS=1426986922328330341,1426986940049264791
INIT_THREAD_POINTS=50
INIT_MEDIA_CHANNEL_IDS=1426986977198342306,1426987004016590949,1426987038254563381
INIT_MEDIA_POINTS=50
INIT_RULES_MESSAGE_ID=1427000925846896731
INIT_RULES_POINTS=50
INIT_RULES_CHANNEL_ID=1427000897766166551
INIT_SOCIALS_CHANNEL_ID=1427000769600553102

## RECOMPENSAS-------------------------------
#############################################
GENERAL_CHANNEL_ID=1427006977896091709
VOTING_CHANNEL_ID=1427006998632861746
AKATSUKI_ROLE_ID=1426977797405937785
JONIN_ROLE_ID=1426977756067135720
SHOP_PRICE_ROLE_AKATSUKI=
SHOP_PRICE_ROLE_JONIN=
SHOP_PRICE_PIN_MESSAGE=
SHOP_PRICE_POLL_PROPOSE=
SUGGESTIONS_CHANNEL_ID=1427008958547103805

# ========================
# Reacciones
# ========================
TOJITOOK_EMOJI_NAME=tojitook

# ========================
# Opcionales / Avanzado
# ========================
MAX_SCAN_PER_CHANNEL=300

## CODIGO DE FUNDADOR
FOUNDER_ROLE_ID=1427037704771862578
FOUNDER_INVITE_CODES=gXWcjSUVk7

##  IMPOSTOR  ## (OBLIGATORIOS PARA EL JUEGO)
################
#----------------------------------------# 

# Impostor: dónde crear canales y dónde publicar la cartelera
IMPOSTOR_CATEGORY_ID=1429076246465351740
IMPOSTOR_FEED_CHANNEL_ID=1429345649672982661

# Roles que cuentan como admin del modo (Hokage/Anbu u otros)
IMPOSTOR_ADMIN_ROLE_IDS=1426968325841489980,1426977638639206400

# DB y fuente de personajes
IMPOSTOR_DB_PATH=./data/impostor.db
IMPOSTOR_CHAR_SOURCE=[https://animealtoque.com/personajes/bdpersonajes.php](https://animealtoque.com/personajes/bdpersonajes.php)
IMPOSTOR_CHAR_BASE=[https://animealtoque.com/personajes/](https://animealtoque.com/personajes/)

# Tiempos / reglas
IMPOSTOR_MAX_PLAYERS=5
IMPOSTOR_LOBBY_IDLE_CLOSE_SECONDS=300
IMPOSTOR_MIN_STAY_SECONDS=30 
IMPOSTOR_TURN_SECONDS=50
IMPOSTOR_VOTE_SECONDS=180
IMPOSTOR_ROLE_REVIEW_SECONDS=20

# Canal para logs internos del modo impostor
IMPOSTOR_STAFF_LOG_CHANNEL_ID=1429334190972997662

# Cadencia de actualización del HUD (segundos)
IMPOSTOR_HUD_EDIT_INTERVAL=5

# Ventana para pedir revancha (segundos después de terminar la partida)
IMPOSTOR_REMATCH_WINDOW_SECONDS=60

IMPOSTOR_SOUND_URL=[https://animealtoque.com/sounds/impostor.mp3](https://animealtoque.com/sounds/impostor.mp3)
SOCIAL_SOUND_URL=[https://animealtoque.com/sounds/social.mp3](https://animealtoque.com/sounds/social.mp3)

IMPOSTOR_MAX_ROUNDS=4
IMPOSTOR_SIMPLE_BOTS=1

# Limpieza al arrancar (all | none)
IMPOSTOR_STARTUP_CLEANUP=all