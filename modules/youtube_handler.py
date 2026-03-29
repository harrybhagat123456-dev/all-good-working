import os
import subprocess
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from vars import CREDIT, cookies_file_path, AUTH_USERS
import globals
from saini import sanitize_filename

try:
    from download_history import (
        check_and_get_resume_info,
        update_download_progress,
        mark_download_completed,
        mark_download_paused,
        format_progress_message,
        get_user_history_list,
        clear_user_history,
        get_history,
    )
    HISTORY_ENABLED = True
    print("[YouTube Handler] History module loaded successfully")
except ImportError as e:
    print(f"[YouTube Handler] Warning: History module not available: {e}")
    HISTORY_ENABLED = False


# ---------------------------------------------------------------------------
# Cookies handlers
# ---------------------------------------------------------------------------

async def cookies_handler(client: Client, m: Message):
    editable = await m.reply_text("**Please upload the YouTube Cookies file (.txt format).**")
    try:
        input_message: Message = await client.listen(m.chat.id)
        if not input_message.document or not input_message.document.file_name.endswith(".txt"):
            await m.reply_text("Invalid file type. Please upload a .txt file.")
            return
        downloaded_path = await input_message.download()
        with open(downloaded_path, "r") as uploaded_file:
            cookies_content = uploaded_file.read()
        with open(cookies_file_path, "w") as target_file:
            target_file.write(cookies_content)
        await editable.delete()
        await input_message.delete()
        await m.reply_text("✅ Cookies updated successfully.\n📂 Saved in `youtube_cookies.txt`.")
    except Exception as e:
        await m.reply_text(f"__**Failed Reason**__\n<blockquote>{str(e)}</blockquote>")


async def getcookies_handler(client: Client, m: Message):
    try:
        await client.send_document(chat_id=m.chat.id, document=cookies_file_path,
                                   caption="Here is the `youtube_cookies.txt` file.")
    except Exception as e:
        await m.reply_text(f"⚠️ An error occurred: {str(e)}")


# ---------------------------------------------------------------------------
# /ytm — original simple YouTube music downloader (NO history)
# ---------------------------------------------------------------------------

async def ytm_handler(bot: Client, m: Message):
    globals.processing_request = True
    globals.cancel_requested = False
    editable = await m.reply_text(
        "**Input Type**\n\n<blockquote><b>01 •Send me the .txt file containing YouTube links\n"
        "02 •Send Single link or Set of YouTube multiple links</b></blockquote>"
    )
    input: Message = await bot.listen(editable.chat.id)
    if input.document and input.document.file_name.endswith(".txt"):
        x = await input.download()
        file_name, ext = os.path.splitext(os.path.basename(x))
        playlist_name = file_name.replace('_', ' ')
        try:
            with open(x, "r") as f:
                content = f.read()
            content = content.split("\n")
            links = []
            for i in content:
                if i.strip():
                    links.append(i.split("://", 1))
            os.remove(x)
        except Exception:
            await m.reply_text("**Invalid file input.**")
            if os.path.exists(x):
                os.remove(x)
            globals.processing_request = False
            return

        await editable.edit(
            f"**•ᴛᴏᴛᴀʟ 🔗 ʟɪɴᴋs ғᴏᴜɴᴅ ᴀʀᴇ --__{len(links)}__--\n"
            f"•sᴇɴᴅ ғʀᴏᴍ ᴡʜᴇʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ...**"
        )
        try:
            input0: Message = await bot.listen(editable.chat.id, timeout=20)
            raw_text = input0.text if (input0 and input0.text) else '1'
            await input0.delete(True)
        except asyncio.TimeoutError:
            raw_text = '1'

        await editable.delete()
        try:
            arg = int(raw_text)
        except (TypeError, ValueError):
            arg = 1
        count = arg

        try:
            if arg == 1:
                playlist_message = await m.reply_text(
                    f"<blockquote><b>⏯️Playlist : {playlist_name}</b></blockquote>"
                )
                await bot.pin_chat_message(m.chat.id, playlist_message.id)
                await bot.delete_messages(m.chat.id, playlist_message.id + 1)
        except Exception:
            pass

    elif input.text:
        content = input.text.strip()
        content = content.split("\n")
        links = []
        for i in content:
            if i.strip():
                links.append(i.split("://", 1))
        count = 1
        arg = 1
        await editable.delete()
        await input.delete(True)
    else:
        await m.reply_text("**Invalid input. Send either a .txt file or YouTube links set**")
        globals.processing_request = False
        return

    try:
        for i in range(arg - 1, len(links)):
            if globals.cancel_requested:
                await m.reply_text("🚦**STOPPED**🚦")
                globals.processing_request = False
                globals.cancel_requested = False
                return

            link = links[i][1] if len(links[i]) > 1 else links[i][0]

            if "youtube.com/embed/" in link or "youtube-nocookie.com/embed/" in link:
                video_id = link.split("/embed/")[1].split("?")[0].split("/")[0]
                Vxy = f"www.youtube.com/watch?v={video_id}"
            elif "youtu.be/" in link:
                Vxy = link
            else:
                Vxy = link

            url = Vxy if (Vxy.startswith("http://") or Vxy.startswith("https://")) else "https://" + Vxy

            try:
                cmd_title = f'yt-dlp --get-title --cookies {cookies_file_path} "{url}"'
                result = subprocess.run(cmd_title, shell=True, capture_output=True, text=True, timeout=10)
                audio_title = result.stdout.strip()[:80] if (result.returncode == 0 and result.stdout.strip()) else f"YouTube_Video_{count:03d}"
            except Exception:
                audio_title = f"YouTube_Video_{count:03d}"

            audio_title = audio_title.replace("_", " ")
            name = f'{audio_title[:60]} {CREDIT}'
            name1 = f'{audio_title} {CREDIT}'
            clean_name = sanitize_filename(name)

            if "youtube.com" in url or "youtu.be" in url:
                prog = await m.reply_text(
                    f"<i><b>Audio Downloading</b></i>\n"
                    f"<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
                )
                output_template = f"{str(count).zfill(3)} {clean_name}"
                cmd = (f'yt-dlp -x --audio-format mp3 --cookies {cookies_file_path} '
                       f'"{url}" -o "{output_template}.%(ext)s" -R 10 --fragment-retries 10')
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                expected_file = f'{output_template}.mp3'
                if os.path.exists(expected_file):
                    await prog.delete(True)
                    try:
                        await bot.send_document(
                            chat_id=m.chat.id, document=expected_file,
                            caption=f'**🎵 Title : **[{str(count).zfill(3)}] - {name1}.mp3\n\n'
                                    f'🔗**Video link** : {url}\n\n🌟** Extracted By **: {CREDIT}'
                        )
                        os.remove(expected_file)
                    except Exception as e:
                        await m.reply_text(
                            f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n'
                            f'**Url** =>> {url}\n**Error** =>> {str(e)}',
                            disable_web_page_preview=True
                        )
                else:
                    await prog.delete(True)
                    await m.reply_text(
                        f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n'
                        f'**Url** =>> {url}\n**File not found after download**',
                        disable_web_page_preview=True
                    )
                count += 1

    except Exception as e:
        await m.reply_text(f"<b>Failed Reason:</b>\n<blockquote><b>{str(e)}</b></blockquote>")
    finally:
        globals.processing_request = False
        await m.reply_text("<blockquote><b>All YouTube Music Download Successfully</b></blockquote>")


# ---------------------------------------------------------------------------
# /history — tracked download command (auto-detects resume)
# ---------------------------------------------------------------------------

async def history_handler(bot: Client, m: Message):
    """
    Tracked YouTube music downloader with auto-resume.
    - If same file was downloaded before and stopped → auto-resumes
    - If new file → normal flow (ask starting number)
    """
    if not HISTORY_ENABLED:
        await m.reply_text("**❌ History feature is not available.**")
        return

    globals.processing_request = True
    globals.cancel_requested = False

    editable = await m.reply_text(
        "**📥 Tracked Download**\n\n"
        "<blockquote><b>Send me the .txt file containing YouTube links.\n"
        "I will auto-resume if you've downloaded this file before.</b></blockquote>"
    )

    input_msg: Message = await bot.listen(editable.chat.id)

    if not (input_msg.document and input_msg.document.file_name.endswith(".txt")):
        await editable.edit("**❌ Please send a .txt file.**")
        globals.processing_request = False
        return

    x = await input_msg.download()
    file_name_orig, _ = os.path.splitext(os.path.basename(x))
    playlist_name = file_name_orig.replace('_', ' ')

    try:
        with open(x, "r") as f:
            content = f.read()
        links = []
        for line in content.split("\n"):
            if line.strip():
                links.append(line.strip().split("://", 1))
    except Exception as e:
        await editable.edit(f"**❌ Could not read file.**\nError: {str(e)}")
        if os.path.exists(x):
            os.remove(x)
        globals.processing_request = False
        return

    # Check history
    file_hash, resume_index, history_entry = await check_and_get_resume_info(
        file_path=x,
        file_name=file_name_orig,
        user_id=m.from_user.id,
        links=[lnk[1] if len(lnk) > 1 else lnk[0] for lnk in links]
    )
    os.remove(x)

    summary = get_history().get_progress_summary(file_hash)
    completed_so_far = summary.get("completed", 0)
    is_resumable = summary.get("exists") and summary.get("can_resume") and completed_so_far > 0

    if is_resumable:
        # Auto-resume — no buttons, no questions
        await editable.edit(
            f"**▶️ Resuming Previous Download**\n\n"
            f"📂 **File:** `{file_name_orig}`\n"
            f"📊 **Progress:** {summary.get('progress_percent', 0)}% "
            f"({completed_so_far}/{summary.get('total_links', len(links))})\n"
            f"⏩ **Continuing from link #{resume_index + 1}...**"
        )
        arg = resume_index + 1
        count = resume_index + 1
        await editable.delete()

        try:
            if arg == 1:
                playlist_message = await m.reply_text(
                    f"<blockquote><b>⏯️Playlist : {playlist_name}</b></blockquote>"
                )
                await bot.pin_chat_message(m.chat.id, playlist_message.id)
                await bot.delete_messages(m.chat.id, playlist_message.id + 1)
        except Exception:
            pass

    else:
        # New file or completed before — ask starting point
        await editable.edit(
            f"**📝 New file: {len(links)} links found**\n\n"
            f"**Send from which number to start downloading (default: 1):**"
        )
        try:
            input0: Message = await bot.listen(editable.chat.id, timeout=20)
            raw_text = input0.text if (input0 and input0.text) else '1'
            await input0.delete(True)
        except asyncio.TimeoutError:
            raw_text = '1'

        await editable.delete()
        try:
            arg = int(raw_text)
        except (TypeError, ValueError):
            arg = 1
        count = arg

        try:
            if arg == 1:
                playlist_message = await m.reply_text(
                    f"<blockquote><b>⏯️Playlist : {playlist_name}</b></blockquote>"
                )
                await bot.pin_chat_message(m.chat.id, playlist_message.id)
                await bot.delete_messages(m.chat.id, playlist_message.id + 1)
        except Exception:
            pass

    # ---- Download loop ----
    try:
        for i in range(arg - 1, len(links)):
            if globals.cancel_requested:
                await mark_download_paused(file_hash)
                await m.reply_text(
                    "🚦**STOPPED**🚦\n\n"
                    f"💾 **Progress saved:** {count - arg} links done this session.\n"
                    "Send the same file again with /history to resume."
                )
                globals.processing_request = False
                globals.cancel_requested = False
                return

            link = links[i][1] if len(links[i]) > 1 else links[i][0]

            if "youtube.com/embed/" in link or "youtube-nocookie.com/embed/" in link:
                video_id = link.split("/embed/")[1].split("?")[0].split("/")[0]
                Vxy = f"www.youtube.com/watch?v={video_id}"
            elif "youtu.be/" in link:
                Vxy = link
            else:
                Vxy = link

            url = Vxy if (Vxy.startswith("http://") or Vxy.startswith("https://")) else "https://" + Vxy

            try:
                cmd_title = f'yt-dlp --get-title --cookies {cookies_file_path} "{url}"'
                result = subprocess.run(cmd_title, shell=True, capture_output=True, text=True, timeout=10)
                audio_title = result.stdout.strip()[:80] if (result.returncode == 0 and result.stdout.strip()) else f"YouTube_Video_{count:03d}"
            except Exception:
                audio_title = f"YouTube_Video_{count:03d}"

            audio_title = audio_title.replace("_", " ")
            name = f'{audio_title[:60]} {CREDIT}'
            name1 = f'{audio_title} {CREDIT}'
            clean_name = sanitize_filename(name)

            if "youtube.com" in url or "youtu.be" in url:
                prog = await m.reply_text(
                    f"<i><b>Audio Downloading</b></i>\n"
                    f"<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
                )
                output_template = f"{str(count).zfill(3)} {clean_name}"
                cmd = (f'yt-dlp -x --audio-format mp3 --cookies {cookies_file_path} '
                       f'"{url}" -o "{output_template}.%(ext)s" -R 10 --fragment-retries 10')
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                expected_file = f'{output_template}.mp3'
                if os.path.exists(expected_file):
                    await prog.delete(True)
                    try:
                        await bot.send_document(
                            chat_id=m.chat.id, document=expected_file,
                            caption=(f'**🎵 Title : **[{str(count).zfill(3)}] - {name1}.mp3\n\n'
                                     f'🔗**Video link** : {url}\n\n🌟** Extracted By **: {CREDIT}')
                        )
                        os.remove(expected_file)
                        await update_download_progress(file_hash, i, "completed", url)
                    except Exception as e:
                        await m.reply_text(
                            f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n'
                            f'**Url** =>> {url}\n**Error** =>> {str(e)}',
                            disable_web_page_preview=True
                        )
                        await update_download_progress(file_hash, i, "failed", url)
                else:
                    await prog.delete(True)
                    await m.reply_text(
                        f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n'
                        f'**Url** =>> {url}\n**File not found after download**',
                        disable_web_page_preview=True
                    )
                    await update_download_progress(file_hash, i, "failed", url)
                count += 1

    except Exception as e:
        await m.reply_text(f"<b>Failed Reason:</b>\n<blockquote><b>{str(e)}</b></blockquote>")
    finally:
        await mark_download_completed(file_hash)
        globals.processing_request = False
        await m.reply_text("<blockquote><b>All YouTube Music Download Successfully</b></blockquote>")


# ---------------------------------------------------------------------------
# /viewhistory — show list of tracked downloads
# ---------------------------------------------------------------------------

async def viewhistory_handler(bot: Client, m: Message):
    if not HISTORY_ENABLED:
        await m.reply_text("**❌ History feature is not available.**")
        return

    user_id = m.from_user.id
    history_list = get_user_history_list(user_id)

    if not history_list:
        await m.reply_text(
            "**📜 No download history yet.**\n\n"
            "Use /history and upload a .txt file to start tracking downloads!"
        )
        return

    msg = "**📜 Your Download History:**\n\n"
    for idx, entry in enumerate(history_list[:10], 1):
        if entry.get("exists"):
            status_emoji = {
                "pending": "⏳", "in_progress": "🔄",
                "completed": "✅", "paused": "⏸️"
            }.get(entry.get("status", "pending"), "❓")
            msg += (
                f"{idx}. {status_emoji} `{entry['file_name']}`\n"
                f"   📊 {entry['progress_percent']}% ({entry['completed']}/{entry['total_links']})\n"
            )
            if entry.get("can_resume") and entry.get("completed", 0) > 0:
                msg += "   💾 Resumable — send same file via /history\n"
            msg += "\n"

    if len(history_list) > 10:
        msg += f"_... and {len(history_list) - 10} more_"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Clear My History", callback_data="clear_my_history")]
    ])
    await m.reply_text(msg, reply_markup=keyboard)


async def clear_history_callback(bot: Client, callback_query):
    if not HISTORY_ENABLED:
        await callback_query.answer("History unavailable.", show_alert=True)
        return
    cleared = clear_user_history(user_id=callback_query.from_user.id)
    await callback_query.answer(f"Cleared {cleared} entries.", show_alert=True)
    await callback_query.message.edit_text(f"**🗑️ Cleared {cleared} history entries.**")


async def clearhistory_handler(bot: Client, m: Message):
    if not HISTORY_ENABLED:
        await m.reply_text("**❌ History feature is not available.**")
        return
    cleared = clear_user_history(user_id=m.from_user.id)
    await m.reply_text(f"**🗑️ Cleared {cleared} history entries.**")


async def allhistory_handler(bot: Client, m: Message):
    if not HISTORY_ENABLED:
        await m.reply_text("**❌ History feature is not available.**")
        return
    from vars import OWNER
    if m.from_user.id != OWNER:
        await m.reply_text("**❌ Owner only command.**")
        return
    all_entries = get_history().get_all_history()
    if not all_entries:
        await m.reply_text("**📜 No download history found.**")
        return
    msg = f"**📜 All History ({len(all_entries)} entries):**\n\n"
    for idx, entry in enumerate(all_entries[:15], 1):
        if entry.get("exists"):
            status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "paused": "⏸️"}.get(entry.get("status"), "❓")
            msg += f"{idx}. {status_emoji} `{entry['file_name']}` — {entry['progress_percent']}% ({entry['completed']}/{entry['total_links']})\n"
    if len(all_entries) > 15:
        msg += f"\n_... and {len(all_entries) - 15} more_"
    await m.reply_text(msg)


async def resetallhistory_handler(bot: Client, m: Message):
    if not HISTORY_ENABLED:
        await m.reply_text("**❌ History feature is not available.**")
        return
    from vars import OWNER
    if m.from_user.id != OWNER:
        await m.reply_text("**❌ Owner only command.**")
        return
    cleared = clear_user_history()
    await m.reply_text(f"**🗑️ Cleared all {cleared} history entries.**")


# ---------------------------------------------------------------------------
# /y2t handler
# ---------------------------------------------------------------------------

async def y2t_handler(bot: Client, message: Message):
    editable = await message.reply_text(
        "<blockquote><b>Send YouTube Website/Playlist link for convert in .txt file</b></blockquote>"
    )
    input_message: Message = await bot.listen(message.chat.id)
    youtube_link = input_message.text.strip()
    await input_message.delete(True)
    await editable.delete(True)

    ydl_opts = {
        'quiet': True, 'extract_flat': True, 'skip_download': True,
        'force_generic_extractor': True, 'forcejson': True,
        'cookies': 'youtube_cookies.txt'
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(youtube_link, download=False)
            title = result.get('title', 'youtube_playlist' if 'entries' in result else 'youtube_video')
        except yt_dlp.utils.DownloadError as e:
            await message.reply_text(f"<blockquote>{str(e)}</blockquote>")
            return

    videos = []
    if 'entries' in result:
        for entry in result['entries']:
            videos.append(f"{entry.get('title', 'No title')}: {entry['url']}")
    else:
        videos.append(f"{result.get('title', 'No title')}: {result['url']}")

    txt_file = os.path.join("downloads", f'{title}.txt')
    os.makedirs(os.path.dirname(txt_file), exist_ok=True)
    with open(txt_file, 'w') as f:
        f.write('\n'.join(videos))

    await message.reply_document(
        document=txt_file,
        caption=f'<a href="{youtube_link}">__**Click Here to Open Link**__</a>\n<blockquote>{title}.txt</blockquote>\n'
    )
    os.remove(txt_file)


# ---------------------------------------------------------------------------
# Register handlers
# ---------------------------------------------------------------------------

def register_youtube_handlers(bot):
    bot.on_message(filters.command("cookies") & filters.private)(cookies_handler)
    bot.on_message(filters.command("getcookies") & filters.private)(getcookies_handler)
    bot.on_message(filters.command(["ytm"]))(ytm_handler)
    bot.on_message(filters.command(["y2t"]))(y2t_handler)
    bot.on_message(filters.command(["viewhistory"]))(viewhistory_handler)
    bot.on_message(filters.command(["clearhistory"]))(clearhistory_handler)
    bot.on_message(filters.command(["allhistory"]))(allhistory_handler)
    bot.on_message(filters.command(["resetallhistory"]))(resetallhistory_handler)
    bot.on_callback_query(filters.regex(r"^clear_my_history$"))(clear_history_callback)
    print("[YouTube Handler] Handlers registered. /ytm=simple YT, /viewhistory=list, /clearhistory")
