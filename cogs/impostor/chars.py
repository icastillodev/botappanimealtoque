# cogs/impostor/chars.py
import os
from typing import List, Tuple
import aiohttp
import asyncio
import random

CHAR_BASE = os.getenv("IMPOSTOR_CHAR_BASE", "https://animealtoque.com/personajes/").rstrip("/") + "/"
CHAR_ENDPOINT = os.getenv("IMPOSTOR_CHAR_ENDPOINT", "").strip()

_FALLBACK: List[Tuple[str, str]] = [
    # Naruto / Naruto Shippuden
    ("Naruto Uzumaki", "naruto-uzumaki"),
    ("Sasuke Uchiha", "sasuke-uchiha"),
    ("Sakura Haruno", "sakura-haruno"),
    ("Kakashi Hatake", "kakashi-hatake"),
    ("Itachi Uchiha", "itachi-uchiha"),
    ("Gaara", "gaara"),
    ("Hinata Hyuga", "hinata-hyuga"),
    ("Jiraiya", "jiraiya"),
    ("Minato Namikaze", "minato-namikaze"),
    ("Madara Uchiha", "madara-uchiha"),

    # Dragon Ball Z
    ("Goku", "goku"),
    ("Vegeta", "vegeta"),
    ("Gohan", "gohan"),
    ("Piccolo", "piccolo"),
    ("Krillin", "krillin"),
    ("Trunks", "trunks"),
    ("Frieza", "frieza"),
    ("Cell", "cell"),
    ("Majin Buu", "majin-buu"),
    ("Bulma", "bulma"),

    # One Piece
    ("Monkey D. Luffy", "monkey-d-luffy"),
    ("Roronoa Zoro", "roronoa-zoro"),
    ("Nami", "nami"),
    ("Usopp", "usopp"),
    ("Sanji", "sanji"),
    ("Tony Tony Chopper", "tony-tony-chopper"),
    ("Nico Robin", "nico-robin"),
    ("Franky", "franky"),
    ("Brook", "brook"),
    ("Jinbe", "jinbe"),

    # Attack on Titan
    ("Eren Yeager", "eren-yeager"),
    ("Mikasa Ackerman", "mikasa-ackerman"),
    ("Armin Arlert", "armin-arlert"),
    ("Levi Ackerman", "levi-ackerman"),
    ("Erwin Smith", "erwin-smith"),
    ("Hange Zoe", "hange-zoe"),
    ("Historia Reiss", "historia-reiss"),
    ("Reiner Braun", "reiner-braun"),
    ("Annie Leonhart", "annie-leonhart"),
    ("Zeke Yeager", "zeke-yeager"),

    # Demon Slayer
    ("Tanjiro Kamado", "tanjiro-kamado"),
    ("Nezuko Kamado", "nezuko-kamado"),
    ("Zenitsu Agatsuma", "zenitsu-agatsuma"),
    ("Inosuke Hashibira", "inosuke-hashibira"),
    ("Kanao Tsuyuri", "kanao-tsuyuri"),
    ("Giyu Tomioka", "giyu-tomioka"),
    ("Shinobu Kocho", "shinobu-kocho"),
    ("Kyojuro Rengoku", "kyojuro-rengoku"),
    ("Tengen Uzui", "tengen-uzui"),
    ("Muzan Kibutsuji", "muzan-kibutsuji"),

    # My Hero Academia
    ("Izuku Midoriya", "izuku-midoriya"),
    ("Katsuki Bakugo", "katsuki-bakugo"),
    ("Shoto Todoroki", "shoto-todoroki"),
    ("Ochaco Uraraka", "ochaco-uraraka"),
    ("Tenya Iida", "tenya-iida"),
    ("All Might", "all-might"),
    ("Endeavor", "endeavor"),
    ("Shota Aizawa", "shota-aizawa"),
    ("Tomura Shigaraki", "tomura-shigaraki"),
    ("Dabi", "dabi"),

    # Death Note
    ("Light Yagami", "light-yagami"),
    ("L", "l"),
    ("Misa Amane", "misa-amane"),
    ("Ryuk", "ryuk"),
    ("Near", "near"),
    ("Mello", "mello"),
    ("Soichiro Yagami", "soichiro-yagami"),
    ("Rem", "rem"),

    # Fullmetal Alchemist: Brotherhood
    ("Edward Elric", "edward-elric"),
    ("Alphonse Elric", "alphonse-elric"),
    ("Winry Rockbell", "winry-rockbell"),
    ("Roy Mustang", "roy-mustang"),
    ("Riza Hawkeye", "riza-hawkeye"),
    ("Maes Hughes", "maes-hughes"),
    ("Scar", "scar"),
    ("Ling Yao", "ling-yao"),
    ("King Bradley", "king-bradley"),
    ("Father", "father"),

    # Jujutsu Kaisen
    ("Yuji Itadori", "yuji-itadori"),
    ("Megumi Fushiguro", "megumi-fushiguro"),
    ("Nobara Kugisaki", "nobara-kugisaki"),
    ("Satoru Gojo", "satoru-gojo"),
    ("Suguru Geto", "suguru-geto"),
    ("Kento Nanami", "kento-nanami"),
    ("Maki Zenin", "maki-zenin"),
    ("Toge Inumaki", "toge-inumaki"),
    ("Panda", "panda"),
    ("Yuta Okkotsu", "yuta-okkotsu"),

    # Hunter x Hunter
    ("Gon Freecss", "gon-freecss"),
    ("Killua Zoldyck", "killua-zoldyck"),
    ("Kurapika", "kurapika"),
    ("Leorio Paradinight", "leorio-paradinight"),
    ("Hisoka Morow", "hisoka-morow"),
    ("Chrollo Lucilfer", "chrollo-lucilfer"),
    ("Meruem", "meruem"),
    ("Neferpitou", "neferpitou"),
    ("Netero", "netero"),

    # Bleach
    ("Ichigo Kurosaki", "ichigo-kurosaki"),
    ("Rukia Kuchiki", "rukia-kuchiki"),
    ("Renji Abarai", "renji-abarai"),
    ("Byakuya Kuchiki", "byakuya-kuchiki"),
    ("Toshiro Hitsugaya", "toshiro-hitsugaya"),
    ("Kenpachi Zaraki", "kenpachi-zaraki"),
    ("Yoruichi Shihoin", "yoruichi-shihoin"),
    ("Kisuke Urahara", "kisuke-urahara"),
    ("Aizen Sosuke", "aizen-sosuke"),
    ("Orihime Inoue", "orihime-inoue"),

    # Sword Art Online
    ("Kirito", "kirito"),
    ("Asuna Yuuki", "asuna-yuuki"),
    ("Sinon", "sinon"),
    ("Leafa", "leafa"),
    ("Klein", "klein"),
    ("Agil", "agil"),
    ("Alice Zuberg", "alice-zuberg"),
    ("Eugeo", "eugeo"),

    # Tokyo Ghoul
    ("Ken Kaneki", "ken-kaneki"),
    ("Touka Kirishima", "touka-kirishima"),
    ("Rize Kamishiro", "rize-kamishiro"),
    ("Juuzou Suzuya", "juuzou-suzuya"),
    ("Koutarou Amon", "koutarou-amon"),
    ("Arima Kishou", "arima-kishou"),
    ("Eto Yoshimura", "eto-yoshimura"),
    ("Tsukiyama Shuu", "tsukiyama-shuu"),

    # Chainsaw Man
    ("Denji", "denji"),
    ("Power", "power"),
    ("Aki Hayakawa", "aki-hayakawa"),
    ("Makima", "makima"),
    ("Himeno", "himeno"),
    ("Kishibe", "kishibe"),
    ("Pochita", "pochita"),
    ("Reze", "reze"),

    # One Punch Man
    ("Saitama", "saitama"),
    ("Genos", "genos"),
    ("Speed-o'-Sound Sonic", "speed-o-sound-sonic"),
    ("Mumen Rider", "mumen-rider"),
    ("Bang", "bang"),
    ("King", "king"),
    ("Tatsumaki", "tatsumaki"),
    ("Fubuki", "fubuki"),
    ("Garou", "garou"),
    ("Boros", "boros"),

    # Neon Genesis Evangelion
    ("Shinji Ikari", "shinji-ikari"),
    ("Rei Ayanami", "rei-ayanami"),
    ("Asuka Langley Soryu", "asuka-langley-soryu"),
    ("Misato Katsuragi", "misato-katsuragi"),
    ("Gendo Ikari", "gendo-ikari"),
    ("Kaworu Nagisa", "kaworu-nagisa"),

    # Spy x Family
    ("Loid Forger", "loid-forger"),
    ("Yor Forger", "yor-forger"),
    ("Anya Forger", "anya-forger"),
    ("Bond Forger", "bond-forger"),
    ("Damian Desmond", "damian-desmond"),
    ("Becky Blackbell", "becky-blackbell"),

    # Fairy Tail
    ("Natsu Dragneel", "natsu-dragneel"),
    ("Lucy Heartfilia", "lucy-heartfilia"),
    ("Gray Fullbuster", "gray-fullbuster"),
    ("Erza Scarlet", "erza-scarlet"),
    ("Wendy Marvell", "wendy-marvell"),
    ("Happy", "happy"),
    ("Juvia Lockser", "juvia-lockser"),
    ("Gajeel Redfox", "gajeel-redfox"),
    ("Makarov Dreyar", "makarov-dreyar"),
    ("Zeref Dragneel", "zeref-dragneel"),

    # Pokémon
    ("Ash Ketchum", "ash-ketchum"),
    ("Pikachu", "pikachu"),
    ("Misty", "misty"),
    ("Brock", "brock"),
    ("Team Rocket", "team-rocket"),
    ("Jessie", "jessie"),
    ("James", "james"),
    ("Meowth", "meowth"),
    ("Professor Oak", "professor-oak"),
    ("Gary Oak", "gary-oak"),

    # Black Clover
    ("Asta", "asta"),
    ("Yuno", "yuno"),
    ("Noelle Silva", "noelle-silva"),
    ("Charmy Pappitson", "charmy-pappitson"),
    ("Luck Voltia", "luck-voltia"),
    ("Magna Swing", "magna-swing"),
    ("Vanessa Enoteca", "vanessa-enoteca"),
    ("Yami Sukehiro", "yami-sukehiro"),
    ("Julius Novachrono", "julius-novachrono"),
    ("Mereoleona Vermillion", "mereoleona-vermillion"),
]


_cached: List[Tuple[str, str]] = []

async def _fetch_remote() -> List[Tuple[str, str]]:
    if not CHAR_ENDPOINT:
        return []
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.get(CHAR_ENDPOINT) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
                # Esperamos una lista de objetos con name/slug
                out: List[Tuple[str, str]] = []
                for item in data:
                    name = str(item.get("name") or item.get("nombre") or "").strip()
                    slug = str(item.get("slug") or item.get("url") or "").strip().strip("/")
                    if name and slug:
                        out.append((name, slug))
                return out
    except Exception:
        return []

async def ensure_cache():
    global _cached
    if _cached:
        return
    rem = await _fetch_remote()
    _cached = rem if rem else list(_FALLBACK)

def pick_random() -> Tuple[str, str]:
    if not _cached:
        # en caso extremo (llamar sin ensure)
        return random.choice(_FALLBACK)
    return random.choice(_cached)

def to_link(slug: str) -> str:
    return CHAR_BASE + slug
