# economy/diarias.py
import time

DAILY_TASK_COMMENT = "daily_comment5"
DAILY_TASK_VIDEO   = "daily_video_react"
DAILY_TASK_WORDLE  = "daily_wordle"

def today_key() -> str:
    return time.strftime("%Y-%m-%d")

async def incrementar_comentario(db_exec, db_commit, get_progress, set_progress, add_points,
                                 guild_id: int, user_id: int, target: int, reward_points: int):
    period = today_key()
    value, completed = await get_progress(guild_id, user_id, "daily", DAILY_TASK_COMMENT, period)
    if completed:
        return False
    value += 1
    done = value >= target
    await set_progress(guild_id, user_id, "daily", DAILY_TASK_COMMENT, period, value, done)
    if done:
        await add_points(guild_id, user_id, reward_points)
    return done

async def completar_video(db_exec, db_commit, get_progress, set_progress, add_points,
                          guild_id: int, user_id: int, reward_points: int):
    period = today_key()
    _, completed = await get_progress(guild_id, user_id, "daily", DAILY_TASK_VIDEO, period)
    if completed:
        return False
    await set_progress(guild_id, user_id, "daily", DAILY_TASK_VIDEO, period, 1, True)
    await add_points(guild_id, user_id, reward_points)
    return True

async def completar_wordle(get_progress, set_progress, add_points,
                           guild_id: int, user_id: int, reward_points: int):
    period = today_key()
    _, completed = await get_progress(guild_id, user_id, "daily", DAILY_TASK_WORDLE, period)
    if completed:
        return False
    await set_progress(guild_id, user_id, "daily", DAILY_TASK_WORDLE, period, 1, True)
    await add_points(guild_id, user_id, reward_points)
    return True

async def render_diarias(get_progress, guild_id: int, user_id: int,
                         target_comments: int, reward_comments: int,
                         video_channel_id: int, reward_video: int,
                         wordle_channel_id: int, wordle_reward: int) -> str:
    day = today_key()
    val_c, done_c = await get_progress(guild_id, user_id, "daily", DAILY_TASK_COMMENT, day)
    line_c = f"- **Comentar {target_comments} veces** ({val_c}/{target_comments}) — {'✅' if done_c else '❌'} (+{reward_comments})"

    if video_channel_id:
        _, done_v = await get_progress(guild_id, user_id, "daily", DAILY_TASK_VIDEO, day)
        line_v = f"- **Reaccionar a un video** en <#{video_channel_id}> — {'✅' if done_v else '❌'} (+{reward_video})"
    else:
        line_v = "- **Reaccionar a un video** — *(canal no configurado)*"

    if wordle_channel_id:
        _, done_w = await get_progress(guild_id, user_id, "daily", DAILY_TASK_WORDLE, day)
        line_w = f"- **Publicar el Wordle diario** en <#{wordle_channel_id}> — {'✅' if done_w else '❌'} (+{wordle_reward})"
    else:
        line_w = "- **Wordle diario** — *(canal no configurado)*"

    return "📅 **Diarias**\n" + "\n".join([line_c, line_v, line_w])
