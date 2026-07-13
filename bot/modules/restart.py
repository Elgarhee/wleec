from asyncio import create_subprocess_exec, gather
from datetime import datetime
from os import execl as osexecl
from sys import executable

from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove
from pytz import timezone

from bot.version import get_version

from .. import LOGGER, intervals, sabnzbd_client, scheduler
from ..core.config_manager import Config, BinConfig
from ..core.jdownloader_booter import jdownloader
from ..core.tg_client import TgClient
from ..core.torrent_manager import TorrentManager
from ..helper.ext_utils.bot_utils import new_task
from ..helper.ext_utils.db_handler import database
from ..helper.ext_utils.files_utils import clean_all
from ..helper.listeners.mega_listener import mega_cleanup
from ..helper.telegram_helper import button_build
from ..helper.telegram_helper.message_utils import (
    delete_message,
    send_message,
)


@new_task
async def restart_bot(_, message):
    buttons = button_build.ButtonMaker()
    buttons.data_button("Yes!", "botrestart confirm")
    buttons.data_button("No!", "botrestart cancel")
    button = buttons.build_menu(2)
    await send_message(
        message, "<i>Are you really sure you want to restart the bot ?</i>", button
    )


@new_task
async def restart_sessions(_, message):
    buttons = button_build.ButtonMaker()
    buttons.data_button("Yes!", "sessionrestart confirm")
    buttons.data_button("No!", "sessionrestart cancel")
    button = buttons.build_menu(2)
    await send_message(
        message,
        "<i>Are you really sure you want to restart the session(s) ?!</>",
        button,
    )


async def send_incomplete_task_message(cid, msg_id, msg):
    try:
        if msg.startswith("⌬ <b><i>Restarted Successfully!</i></b>"):
            await TgClient.bot.edit_message_text(
                chat_id=cid,
                message_id=msg_id,
                text=msg,
                disable_web_page_preview=True,
            )
            await remove(".restartmsg")
        else:
            await TgClient.bot.send_message(
                chat_id=cid,
                text=msg,
                disable_web_page_preview=True,
                disable_notification=True,
            )
    except Exception as e:
        LOGGER.error(e)


import re

def parse_message_link(link: str):
    # Matches t.me/c/123456789/123 or t.me/username/123
    match = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', link)
    if not match:
        return None, None
    chat_identifier, message_id_str = match.groups()
    message_id = int(message_id_str)
    
    # If it's a private chat (digits only), prefix it with -100
    if chat_identifier.isdigit():
        chat_id = int(f"-100{chat_identifier}")
    else:
        chat_id = chat_identifier
        
    return chat_id, message_id


async def reprocess_task(link: str):
    from bot import bot_loop
    chat_id, message_id = parse_message_link(link)
    if not chat_id or not message_id:
        LOGGER.error(f"Could not parse message link: {link}")
        return
        
    try:
        message = await TgClient.bot.get_messages(chat_id, message_id)
    except Exception as e:
        LOGGER.error(f"Failed to fetch message for link {link}: {e}")
        return
        
    if not message:
        LOGGER.error(f"Fetched message is empty for link: {link}")
        return
        
    text = message.text or message.caption
    if not text:
        LOGGER.error(f"Message has no text or caption for link: {link}")
        return
        
    first_word = text.split(None, 1)[0].lower()
    if first_word.startswith("/"):
        cmd = first_word[1:]
        if Config.CMD_SUFFIX and cmd.endswith(Config.CMD_SUFFIX):
            cmd = cmd[:-len(Config.CMD_SUFFIX)]
        if "@" in cmd:
            cmd = cmd.split("@")[0]
    else:
        LOGGER.error(f"First word does not start with /: {first_word}")
        return

    from bot.modules.mirror_leech import (
        mirror, qb_mirror, jd_mirror, nzb_mirror,
        leech, qb_leech, jd_leech, nzb_leech
    )
    from bot.modules.ytdlp import ytdl, ytdl_leech
    from bot.modules.clone import clone_node
    
    handler = None
    if cmd in ["mirror", "m"]:
        handler = mirror
    elif cmd in ["qbmirror", "qm"]:
        handler = qb_mirror
    elif cmd in ["jdmirror", "jm"]:
        handler = jd_mirror
    elif cmd in ["nzbmirror", "nm"]:
        handler = nzb_mirror
    elif cmd in ["leech", "l"]:
        handler = leech
    elif cmd in ["qbleech", "ql"]:
        handler = qb_leech
    elif cmd in ["jdleech", "jl"]:
        handler = jd_leech
    elif cmd in ["nzbleech", "nl"]:
        handler = nzb_leech
    elif cmd in ["ytdl", "y"]:
        handler = ytdl
    elif cmd in ["ytdlleech", "yl"]:
        handler = ytdl_leech
    elif cmd in ["clone", "cl"]:
        handler = clone_node
        
    if handler:
        LOGGER.info(f"Re-processing task {link} with command /{cmd}")
        bot_loop.create_task(handler(TgClient.bot, message))
    else:
        LOGGER.warning(f"No handler mapped for command /{cmd} from link {link}")


async def restart_notification():
    if await aiopath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
    else:
        chat_id, msg_id = 0, 0

    now = datetime.now(timezone("Asia/Kolkata"))

    if Config.INCOMPLETE_TASK_NOTIFIER and Config.DATABASE_URL:
        if notifier_dict := await database.get_incomplete_tasks():
            from bot import bot_loop
            for cid, data in notifier_dict.items():
                msg = f"""⌬ <b><i>{"Restarted Successfully!" if cid == chat_id else "Bot Restarted!"}</i></b>
┟ <b>Date:</b> {now.strftime("%d/%m/%y")}
┠ <b>Time:</b> {now.strftime("%I:%M:%S %p")}
┠ <b>TimeZone:</b> Asia/Kolkata
┖ <b>Version:</b> {get_version()}
┖ <b>Status:</b> Re-processing incomplete tasks..."""
                for tag, links in data.items():
                    msg += f"\n\n{tag}: "
                    for index, link in enumerate(links, start=1):
                        msg += f" <a href='{link}'>{index}</a> |"
                        bot_loop.create_task(reprocess_task(link))
                        if len(msg.encode()) > 4000:
                            await send_incomplete_task_message(cid, msg_id, msg)
                            msg = ""
                if msg:
                    await send_incomplete_task_message(cid, msg_id, msg)

    if await aiopath.isfile(".restartmsg"):
        try:
            await TgClient.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"""⌬ <b><i>Restarted Successfully!</i></b>
┟ <b>Date:</b> {now.strftime("%d/%m/%y")}
┠ <b>Time:</b> {now.strftime("%I:%M:%S %p")}
┠ <b>TimeZone:</b> Asia/Kolkata
┖ <b>Version:</b> {get_version()}""",
            )
        except Exception as e:
            LOGGER.error(e)
        await remove(".restartmsg")



@new_task
async def confirm_restart(_, query):
    await query.answer()
    data = query.data.split()
    message = query.message
    reply_to = message.reply_to_message
    await delete_message(message)
    if data[1] == "confirm":
        intervals["stopAll"] = True
        restart_message = await send_message(reply_to, "<i>Restarting...</i>")
        await delete_message(message)
        await TgClient.stop()
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if qb := intervals["qb"]:
            qb.cancel()
        if jd := intervals["jd"]:
            jd.cancel()
        if nzb := intervals["nzb"]:
            nzb.cancel()
        if st := intervals["status"]:
            for intvl in list(st.values()):
                intvl.cancel()
        await mega_cleanup()
        await clean_all()
        await TorrentManager.close_all()
        if sabnzbd_client.LOGGED_IN:
            await gather(
                sabnzbd_client.pause_all(),
                sabnzbd_client.delete_job("all", True),
                sabnzbd_client.purge_all(True),
                sabnzbd_client.delete_history("all", delete_files=True),
            )
            await sabnzbd_client.close()
        if jdownloader.is_connected:
            await gather(
                jdownloader.device.downloadcontroller.stop_downloads(),
                jdownloader.device.linkgrabber.clear_list(),
                jdownloader.device.downloads.cleanup(
                    "DELETE_ALL",
                    "REMOVE_LINKS_AND_DELETE_FILES",
                    "ALL",
                ),
            )
            await jdownloader.close()
        proc1 = await create_subprocess_exec(
            "pkill",
            "-9",
            "-f",
            f"gunicorn|{BinConfig.ARIA2_NAME}|{BinConfig.QBIT_NAME}|{BinConfig.FFMPEG_NAME}|{BinConfig.RCLONE_NAME}|java|{BinConfig.SABNZBD_NAME}|7z|split",
        )
        proc2 = await create_subprocess_exec("python3", "update.py")
        await gather(proc1.wait(), proc2.wait())
        async with aiopen(".restartmsg", "w") as f:
            await f.write(f"{restart_message.chat.id}\n{restart_message.id}\n")
        osexecl(executable, executable, "-m", "bot")
    else:
        await delete_message(message, reply_to)
