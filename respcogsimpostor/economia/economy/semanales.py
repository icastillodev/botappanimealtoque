# economy/semanales.py
import time
from typing import List

WEEKLY_TASK_THREAD = "weekly_open_thread"
WEEKLY_TASK_MEDIA  = "weekly_post_media"

def week_key() -> str:
    return time.strftime("%G-%V")

async def completar_thread(get_progress, set_progress, add_points,
                           guild_id: int, user_id: int, reward_points: int):
    period = week_key()
    _, completed = await get_progress(guild_id, user_id, "weekly", WEEKLY_TASK_THREAD, period)
    if completed:
        return False
    await set_progress(guild_id, user_id, "weekly", WEEKLY_TASK_THREAD, period, 1, True)
    await add_points(guild_id, user_id, reward_points)
    return True

async def completar_media(get_progress, set_progress, add_points,
                          guild_id: int, user_id: int, reward_points: int):
    period = week_key()
    _, completed = await get_progress(guild_id, user_id, "weekly", WEEKLY_TASK_MEDIA, period)
    if completed:
        return False
    await set_progress(guild_id, user_id, "weekly", WEEKLY_TASK_MEDIA, period, 1, True)
    await add_points(guild_id, user_id, reward_points)
    return True

async def render_semanales(get_progress, guild_id: int, user_id: int,
                           thread_channels: List[int], media_channels: List[int],
                           reward_thread: int, reward_media: int) -> str:
    wk = week_key()
    if thread_channels:
        _, done_t = await get_progress(guild_id, user_id, "weekly", WEEKLY_TASK_THREAD, wk)
        chs = " / ".join(f"<#{cid}>" for cid in thread_channels)
        line_t = f"- **Abrir un thread** en {chs} — {'✅' if done_t else '❌'} (+{reward_thread})"
    else:
        line_t = "- **Abrir un thread** — *(canales no configurados)*"

    if media_channels:
        _, done_m = await get_progress(guild_id, user_id, "weekly", WEEKLY_TASK_MEDIA, wk)
        chs2 = " / ".join(f"<#{cid}>" for cid in media_channels)
        line_m = f"- **Subir un meme/cosplay/dibujo** en {chs2} — {'✅' if done_m else '❌'} (+{reward_media})"
    else:
        line_m = "- **Subir un meme/cosplay/dibujo** — *(canales no configurados)*"

    return "🗓️ **Semanales**\n" + "\n".join([line_t, line_m])
