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
    {"name": "Naruto Uzumaki", "slug": "naruto-uzumaki"},
    {"name": "Sasuke Uchiha", "slug": "sasuke-uchiha"},
    {"name": "Sakura Haruno", "slug": "sakura-haruno"},
    {"name": "Kakashi Hatake", "slug": "kakashi-hatake"},
    {"name": "Monkey D. Luffy", "slug": "monkey-d-luffy"},
    {"name": "Roronoa Zoro", "slug": "roronoa-zoro"},
    {"name": "Nami", "slug": "nami"},
    {"name": "Son Goku", "slug": "son-goku"},
    {"name": "Vegeta", "slug": "vegeta"},
    {"name": "Eren Yeager", "slug": "eren-yeager"},
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