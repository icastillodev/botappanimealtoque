# cogs/impostor/chars.py

import os
import aiohttp
import logging
import random
from typing import List, Optional, TypedDict
import asyncio  

log = logging.getLogger(__name__)

# --- Definición de Tipo ---

class Character(TypedDict):
    """Estructura esperada del JSON de cada personaje."""
    name: str
    slug: str

# --- Configuración y Fallback ---

def get_char_source_url() -> Optional[str]:
    return os.getenv("IMPOSTOR_CHAR_SOURCE")

def get_char_base_url() -> str:
    # Devuelve el prefijo o un string vacío si no está seteado
    return os.getenv("IMPOSTOR_CHAR_BASE", "")

# Lista de fallback si la API falla, como se solicitó.
_FALLBACK_CHARACTERS: List[Character] = [
    # Naruto / Naruto Shippuden
    {"name": "Naruto Uzumaki", "slug": "naruto-uzumaki"},
    {"name": "Sasuke Uchiha", "slug": "sasuke-uchiha"},
    {"name": "Sakura Haruno", "slug": "sakura-haruno"},
    {"name": "Kakashi Hatake", "slug": "kakashi-hatake"},
    {"name": "Itachi Uchiha", "slug": "itachi-uchiha"},
    {"name": "Gaara", "slug": "gaara"},
    {"name": "Hinata Hyuga", "slug": "hinata-hyuga"},
    {"name": "Jiraiya", "slug": "jiraiya"},
    {"name": "Minato Namikaze", "slug": "minato-namikaze"},
    {"name": "Madara Uchiha", "slug": "madara-uchiha"},

    # Dragon Ball Z
    {"name": "Son Goku", "slug": "son-goku"},
    {"name": "Vegeta", "slug": "vegeta"},
    {"name": "Gohan", "slug": "gohan"},
    {"name": "Piccolo", "slug": "piccolo"},
    {"name": "Krillin", "slug": "krillin"},
    {"name": "Trunks", "slug": "trunks"},
    {"name": "Frieza", "slug": "frieza"},
    {"name": "Cell", "slug": "cell"},
    {"name": "Majin Buu", "slug": "majin-buu"},
    {"name": "Bulma", "slug": "bulma"},

    # One Piece
    {"name": "Monkey D. Luffy", "slug": "monkey-d-luffy"},
    {"name": "Roronoa Zoro", "slug": "roronoa-zoro"},
    {"name": "Nami", "slug": "nami"},
    {"name": "Usopp", "slug": "usopp"},
    {"name": "Sanji", "slug": "sanji"},
    {"name": "Tony Tony Chopper", "slug": "tony-tony-chopper"},
    {"name": "Nico Robin", "slug": "nico-robin"},
    {"name": "Franky", "slug": "franky"},
    {"name": "Brook", "slug": "brook"},
    {"name": "Jinbe", "slug": "jinbe"},

    # Attack on Titan
    {"name": "Eren Yeager", "slug": "eren-yeager"},
    {"name": "Mikasa Ackerman", "slug": "mikasa-ackerman"},
    {"name": "Armin Arlert", "slug": "armin-arlert"},
    {"name": "Levi Ackerman", "slug": "levi-ackerman"},
    {"name": "Erwin Smith", "slug": "erwin-smith"},
    {"name": "Hange Zoe", "slug": "hange-zoe"},
    {"name": "Historia Reiss", "slug": "historia-reiss"},
    {"name": "Reiner Braun", "slug": "reiner-braun"},
    {"name": "Annie Leonhart", "slug": "annie-leonhart"},
    {"name": "Zeke Yeager", "slug": "zeke-yeager"},

    # Demon Slayer
    {"name": "Tanjiro Kamado", "slug": "tanjiro-kamado"},
    {"name": "Nezuko Kamado", "slug": "nezuko-kamado"},
    {"name": "Zenitsu Agatsuma", "slug": "zenitsu-agatsuma"},
    {"name": "Inosuke Hashibira", "slug": "inosuke-hashibira"},
    {"name": "Kanao Tsuyuri", "slug": "kanao-tsuyuri"},
    {"name": "Giyu Tomioka", "slug": "giyu-tomioka"},
    {"name": "Shinobu Kocho", "slug": "shinobu-kocho"},
    {"name": "Kyojuro Rengoku", "slug": "kyojuro-rengoku"},
    {"name": "Tengen Uzui", "slug": "tengen-uzui"},
    {"name": "Muzan Kibutsuji", "slug": "muzan-kibutsuji"},

    # My Hero Academia
    {"name": "Izuku Midoriya", "slug": "izuku-midoriya"},
    {"name": "Katsuki Bakugo", "slug": "katsuki-bakugo"},
    {"name": "Shoto Todoroki", "slug": "shoto-todoroki"},
    {"name": "Ochaco Uraraka", "slug": "ochaco-uraraka"},
    {"name": "Tenya Iida", "slug": "tenya-iida"},
    {"name": "All Might", "slug": "all-might"},
    {"name": "Endeavor", "slug": "endeavor"},
    {"name": "Shota Aizawa", "slug": "shota-aizawa"},
    {"name": "Tomura Shigaraki", "slug": "tomura-shigaraki"},
    {"name": "Dabi", "slug": "dabi"},

    # Death Note
    {"name": "Light Yagami", "slug": "light-yagami"},
    {"name": "L", "slug": "l"},
    {"name": "Misa Amane", "slug": "misa-amane"},
    {"name": "Ryuk", "slug": "ryuk"},
    {"name": "Near", "slug": "near"},
    {"name": "Mello", "slug": "mello"},
    {"name": "Soichiro Yagami", "slug": "soichiro-yagami"},
    {"name": "Rem", "slug": "rem"},

    # Fullmetal Alchemist: Brotherhood
    {"name": "Edward Elric", "slug": "edward-elric"},
    {"name": "Alphonse Elric", "slug": "alphonse-elric"},
    {"name": "Winry Rockbell", "slug": "winry-rockbell"},
    {"name": "Roy Mustang", "slug": "roy-mustang"},
    {"name": "Riza Hawkeye", "slug": "riza-hawkeye"},
    {"name": "Maes Hughes", "slug": "maes-hughes"},
    {"name": "Scar", "slug": "scar"},
    {"name": "Ling Yao", "slug": "ling-yao"},
    {"name": "King Bradley", "slug": "king-bradley"},
    {"name": "Father", "slug": "father"},

    # Jujutsu Kaisen
    {"name": "Yuji Itadori", "slug": "yuji-itadori"},
    {"name": "Megumi Fushiguro", "slug": "megumi-fushiguro"},
    {"name": "Nobara Kugisaki", "slug": "nobara-kugisaki"},
    {"name": "Satoru Gojo", "slug": "satoru-gojo"},
    {"name": "Suguru Geto", "slug": "suguru-geto"},
    {"name": "Kento Nanami", "slug": "kento-nanami"},
    {"name": "Maki Zenin", "slug": "maki-zenin"},
    {"name": "Toge Inumaki", "slug": "toge-inumaki"},
    {"name": "Panda", "slug": "panda"},
    {"name": "Yuta Okkotsu", "slug": "yuta-okkotsu"},

    # Hunter x Hunter
    {"name": "Gon Freecss", "slug": "gon-freecss"},
    {"name": "Killua Zoldyck", "slug": "killua-zoldyck"},
    {"name": "Kurapika", "slug": "kurapika"},
    {"name": "Leorio Paradinight", "slug": "leorio-paradinight"},
    {"name": "Hisoka Morow", "slug": "hisoka-morow"},
    {"name": "Chrollo Lucilfer", "slug": "chrollo-lucilfer"},
    {"name": "Meruem", "slug": "meruem"},
    {"name": "Neferpitou", "slug": "neferpitou"},
    {"name": "Isaac Netero", "slug": "isaac-netero"},

    # Bleach
    {"name": "Ichigo Kurosaki", "slug": "ichigo-kurosaki"},
    {"name": "Rukia Kuchiki", "slug": "rukia-kuchiki"},
    {"name": "Renji Abarai", "slug": "renji-abarai"},
    {"name": "Byakuya Kuchiki", "slug": "byakuya-kuchiki"},
    {"name": "Toshiro Hitsugaya", "slug": "toshiro-hitsugaya"},
    {"name": "Kenpachi Zaraki", "slug": "kenpachi-zaraki"},
    {"name": "Yoruichi Shihoin", "slug": "yoruichi-shihoin"},
    {"name": "Kisuke Urahara", "slug": "kisuke-urahara"},
    {"name": "Aizen Sosuke", "slug": "aizen-sosuke"},
    {"name": "Orihime Inoue", "slug": "orihime-inoue"},

    # Sword Art Online
    {"name": "Kirito", "slug": "kirito"},
    {"name": "Asuna Yuuki", "slug": "asuna-yuuki"},
    {"name": "Sinon", "slug": "sinon"},
    {"name": "Leafa", "slug": "leafa"},
    {"name": "Klein", "slug": "klein"},
    {"name": "Agil", "slug": "agil"},
    {"name": "Alice Zuberg", "slug": "alice-zuberg"},
    {"name": "Eugeo", "slug": "eugeo"},

    # Tokyo Ghoul
    {"name": "Ken Kaneki", "slug": "ken-kaneki"},
    {"name": "Touka Kirishima", "slug": "touka-kirishima"},
    {"name": "Rize Kamishiro", "slug": "rize-kamishiro"},
    {"name": "Juuzou Suzuya", "slug": "juuzou-suzuya"},
    {"name": "Koutarou Amon", "slug": "koutarou-amon"},
    {"name": "Arima Kishou", "slug": "arima-kishou"},
    {"name": "Eto Yoshimura", "slug": "eto-yoshimura"},
    {"name": "Tsukiyama Shuu", "slug": "tsukiyama-shuu"},

    # Chainsaw Man
    {"name": "Denji", "slug": "denji"},
    {"name": "Power", "slug": "power"},
    {"name": "Aki Hayakawa", "slug": "aki-hayakawa"},
    {"name": "Makima", "slug": "makima"},
    {"name": "Himeno", "slug": "himeno"},
    {"name": "Kishibe", "slug": "kishibe"},
    {"name": "Pochita", "slug": "pochita"},
    {"name": "Reze", "slug": "reze"},

    # One Punch Man
    {"name": "Saitama", "slug": "saitama"},
    {"name": "Genos", "slug": "genos"},
    {"name": "Speed-o'-Sound Sonic", "slug": "speed-o-sound-sonic"},
    {"name": "Mumen Rider", "slug": "mumen-rider"},
    {"name": "Bang", "slug": "bang"},
    {"name": "King", "slug": "king"},
    {"name": "Tatsumaki", "slug": "tatsumaki"},
    {"name": "Fubuki", "slug": "fubuki"},
    {"name": "Garou", "slug": "garou"},
    {"name": "Boros", "slug": "boros"},

    # Neon Genesis Evangelion
    {"name": "Shinji Ikari", "slug": "shinji-ikari"},
    {"name": "Rei Ayanami", "slug": "rei-ayanami"},
    {"name": "Asuka Langley Soryu", "slug": "asuka-langley-soryu"},
    {"name": "Misato Katsuragi", "slug": "misato-katsuragi"},
    {"name": "Gendo Ikari", "slug": "gendo-ikari"},
    {"name": "Kaworu Nagisa", "slug": "kaworu-nagisa"},

    # Spy x Family
    {"name": "Loid Forger", "slug": "loid-forger"},
    {"name": "Yor Forger", "slug": "yor-forger"},
    {"name": "Anya Forger", "slug": "anya-forger"},
    {"name": "Bond Forger", "slug": "bond-forger"},
    {"name": "Damian Desmond", "slug": "damian-desmond"},
    {"name": "Becky Blackbell", "slug": "becky-blackbell"},

    # Fairy Tail
    {"name": "Natsu Dragneel", "slug": "natsu-dragneel"},
    {"name": "Lucy Heartfilia", "slug": "lucy-heartfilia"},
    {"name": "Gray Fullbuster", "slug": "gray-fullbuster"},
    {"name": "Erza Scarlet", "slug": "erza-scarlet"},
    {"name": "Wendy Marvell", "slug": "wendy-marvell"},
    {"name": "Happy", "slug": "happy"},
    {"name": "Juvia Lockser", "slug": "juvia-lockser"},
    {"name": "Gajeel Redfox", "slug": "gajeel-redfox"},
    {"name": "Makarov Dreyar", "slug": "makarov-dreyar"},
    {"name": "Zeref Dragneel", "slug": "zeref-dragneel"},

    # Pokémon
    {"name": "Ash Ketchum", "slug": "ash-ketchum"},
    {"name": "Pikachu", "slug": "pikachu"},
    {"name": "Misty", "slug": "misty"},
    {"name": "Brock", "slug": "brock"},
    {"name": "Jessie", "slug": "jessie"},
    {"name": "James", "slug": "james"},
    {"name": "Meowth", "slug": "meowth"},
    {"name": "Professor Oak", "slug": "professor-oak"},
    {"name": "Gary Oak", "slug": "gary-oak"},
    {"name": "Cynthia", "slug": "cynthia"},

    # Black Clover
    {"name": "Asta", "slug": "asta"},
    {"name": "Yuno", "slug": "yuno"},
    {"name": "Noelle Silva", "slug": "noelle-silva"},
    {"name": "Charmy Pappitson", "slug": "charmy-pappitson"},
    {"name": "Luck Voltia", "slug": "luck-voltia"},
    {"name": "Vanessa Enoteca", "slug": "vanessa-enoteca"},
    {"name": "Yami Sukehiro", "slug": "yami-sukehiro"},
    {"name": "Julius Novachrono", "slug": "julius-novachrono"},
    {"name": "Mereoleona Vermillion", "slug": "mereoleona-vermillion"},
    {"name": "Fuegoleon Vermillion", "slug": "fuegoleon-vermillion"},
]

# --- Caché en Memoria ---

# Usamos 'None' para saber si ya intentamos la carga.
# Si es 'None', no hemos intentado.
# Si es una lista, es la lista válida (de API o fallback).
_character_cache: Optional[List[Character]] = None
_cache_lock = asyncio.Lock()


# --- Lógica Principal ---

async def fetch_characters() -> List[Character]:
    """
    Obtiene la lista de personajes desde la API o el fallback.
    Utiliza una caché en memoria.
    """
    global _character_cache
    
    # 1. Revisar caché
    async with _cache_lock:
        if _character_cache is not None:
            # log.debug("Usando lista de personajes cacheada.")
            return _character_cache

    # 2. Si no hay caché, intentar fetch
    url = get_char_source_url()
    if not url:
        log.warning("IMPOSTOR_CHAR_SOURCE no está definido. Usando fallback.")
        _character_cache = _FALLBACK_CHARACTERS
        return _character_cache

    log.info(f"Obteniendo lista de personajes desde: {url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Validación simple del formato (lista de dicts con 'name' y 'slug')
                    if isinstance(data, list) and all(
                        isinstance(item, dict) and 'name' in item and 'slug' in item for item in data
                    ):
                        log.info(f"Éxito: Se cargaron {len(data)} personajes desde la API.")
                        _character_cache = data
                        return _character_cache
                    else:
                        log.error(f"Formato JSON inesperado de {url}. Usando fallback.")
                        _character_cache = _FALLBACK_CHARACTERS
                        return _character_cache
                else:
                    log.error(f"Error {response.status} al obtener personajes de {url}. Usando fallback.")
                    _character_cache = _FALLBACK_CHARACTERS
                    return _character_cache

    except aiohttp.ClientConnectorError:
        log.error(f"Error de conexión al intentar alcanzar {url}. Usando fallback.")
    except aiohttp.ContentTypeError:
        log.error(f"La respuesta de {url} no fue JSON válido. Usando fallback.")
    except Exception as e:
        log.exception(f"Error inesperado al obtener personajes: {e}. Usando fallback.")
    
    # 3. Si todo falla, usar y cachear el fallback
    async with _cache_lock:
        _character_cache = _FALLBACK_CHARACTERS
    return _character_cache


async def get_random_character() -> Character:
    """
    Devuelve un personaje aleatorio de la lista (API o fallback).
    """
    # Asegurarnos de que la lista esté cargada
    char_list = await fetch_characters()
    
    if not char_list:
        # Esto no debería pasar si el fallback está bien definido
        log.error("¡Lista de personajes y fallback están vacíos!")
        return {"name": "Error", "slug": "error"}
        
    return random.choice(char_list)


def get_character_url(slug: str) -> str:
    """
    Construye la URL completa a la ficha del personaje.
    """
    base = get_char_base_url()
    # Asegurarnos de que la URL base termine en / si no está vacía
    if base and not base.endswith('/'):
        base += '/'
    
    # Quitar / inicial del slug si existe, para evitar URL dobles
    slug = slug.lstrip('/')
    
    return base + slug