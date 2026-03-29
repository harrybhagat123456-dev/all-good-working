import os
import re
import sys
import m3u8
import json
import time
import pytz
import asyncio
import requests
import subprocess
import urllib
import urllib.parse
import yt_dlp
import tgcrypto
import cloudscraper
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64encode, b64decode
from logs import logging
from bs4 import BeautifulSoup
import saini as helper
import html_handler
import globals
from authorisation import add_auth_user, list_auth_users, remove_auth_user
from broadcast import broadcast_handler, broadusers_handler
from text_handler import text_to_txt
from youtube_handler import ytm_handler, y2t_handler, getcookies_handler, cookies_handler

try:
    from download_history import (
        check_and_get_resume_info,
        update_download_progress,
        mark_download_completed,
        mark_download_paused,
        get_history,
    )
    _HISTORY_ENABLED = True
    print("[DRM Handler] History module loaded")
except ImportError as e:
    _HISTORY_ENABLED = False
    print(f"[DRM Handler] History module not available: {e}")
from utils import progress_bar
from vars import API_ID, API_HASH, BOT_TOKEN, OWNER, CREDIT, AUTH_USERS, TOTAL_USERS, cookies_file_path
from vars import api_url, api_token, token_cp, adda_token, photologo, photoyt, photocp, photozip
from aiohttp import ClientSession
from subprocess import getstatusoutput
from pytube import YouTube
from aiohttp import web
import random
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto
from pyrogram.errors import FloodWait, PeerIdInvalid, UserIsBlocked, InputUserDeactivated
from pyrogram.errors.exceptions.bad_request_400 import StickerEmojiInvalid
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp
import aiofiles
import zipfile
import shutil
import ffmpeg

# .....,.....,.......,...,.......,....., .....,.....,.......,...,.......,.....,

# ============================================================
# FLOOD CONTROL CONFIGURATION
# ============================================================
# Base delay between uploads (seconds) - adjust based on your needs
UPLOAD_DELAY = 3  # seconds between each upload
# Extra delay after flood wait
FLOOD_EXTRA_DELAY = 5  # extra seconds to wait after flood
# Maximum retries for flood
MAX_FLOOD_RETRIES = 5


async def safe_listen(bot, chat_id, user_id, timeout=60, filters=None):
    """
    Wrapper for bot.listen() that tracks active conversations.
    Returns None on any timeout or cancellation.
    If the user sends a /command, it is treated as cancellation (returns None).
    """
    globals.active_conversations[user_id] = True
    try:
        if filters:
            result = await bot.listen(chat_id, timeout=timeout, filters=filters)
        else:
            result = await bot.listen(chat_id, timeout=timeout)
        # If the user replied with a slash-command, treat it as cancellation
        if result and result.text and result.text.strip().startswith('/'):
            return None
        return result
    except Exception:
        return None
    finally:
        globals.active_conversations.pop(user_id, None)


# ============================================================
# FLOOD-SAFE UPLOAD FUNCTIONS
# ============================================================

async def safe_send_document(bot, chat_id, document, caption=None, message_thread_id=None, max_retries=MAX_FLOOD_RETRIES):
    """
    Send document with automatic flood handling and retry logic.
    """
    for attempt in range(max_retries):
        try:
            kwargs = dict(chat_id=chat_id, document=document, caption=caption)
            if message_thread_id:
                kwargs["message_thread_id"] = message_thread_id
            result = await bot.send_document(**kwargs)
            # Add delay after successful upload to prevent flood
            await asyncio.sleep(UPLOAD_DELAY)
            return result, True
            
        except FloodWait as e:
            wait_time = e.value  # Telegram tells us how long to wait
            print(f"FloodWait: Need to wait {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
            
            if attempt < max_retries - 1:
                # Wait the required time + extra buffer
                total_wait = wait_time + FLOOD_EXTRA_DELAY
                await asyncio.sleep(total_wait)
            else:
                return None, False
                
        except Exception as e:
            print(f"Error sending document: {e}")
            return None, False
    
    return None, False


async def safe_send_video(bot, chat_id, video, caption=None, thumb=None, message_thread_id=None, max_retries=MAX_FLOOD_RETRIES):
    """
    Send video with automatic flood handling and retry logic.
    """
    for attempt in range(max_retries):
        try:
            kwargs = dict(chat_id=chat_id, video=video, caption=caption, thumb=thumb)
            if message_thread_id:
                kwargs["message_thread_id"] = message_thread_id
            result = await bot.send_video(**kwargs)
            # Add delay after successful upload to prevent flood
            await asyncio.sleep(UPLOAD_DELAY)
            return result, True
            
        except FloodWait as e:
            wait_time = e.value
            print(f"FloodWait: Need to wait {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
            
            if attempt < max_retries - 1:
                total_wait = wait_time + FLOOD_EXTRA_DELAY
                await asyncio.sleep(total_wait)
            else:
                return None, False
                
        except Exception as e:
            print(f"Error sending video: {e}")
            return None, False
    
    return None, False


async def safe_send_photo(bot, chat_id, photo, caption=None, message_thread_id=None, max_retries=MAX_FLOOD_RETRIES):
    """
    Send photo with automatic flood handling and retry logic.
    """
    for attempt in range(max_retries):
        try:
            kwargs = dict(chat_id=chat_id, photo=photo, caption=caption)
            if message_thread_id:
                kwargs["message_thread_id"] = message_thread_id
            result = await bot.send_photo(**kwargs)
            await asyncio.sleep(UPLOAD_DELAY)
            return result, True
            
        except FloodWait as e:
            wait_time = e.value
            print(f"FloodWait: Need to wait {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
            
            if attempt < max_retries - 1:
                total_wait = wait_time + FLOOD_EXTRA_DELAY
                await asyncio.sleep(total_wait)
            else:
                return None, False
                
        except Exception as e:
            print(f"Error sending photo: {e}")
            return None, False
    
    return None, False


async def safe_send_message(bot, chat_id, text, max_retries=MAX_FLOOD_RETRIES, **kwargs):
    """
    Send message with automatic flood handling and retry logic.
    """
    for attempt in range(max_retries):
        try:
            result = await bot.send_message(
                chat_id=chat_id,
                text=text,
                **kwargs
            )
            # Small delay for messages too
            await asyncio.sleep(1)
            return result, True
            
        except FloodWait as e:
            wait_time = e.value
            print(f"FloodWait: Need to wait {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time + 2)
            else:
                return None, False
                
        except Exception as e:
            print(f"Error sending message: {e}")
            return None, False
    
    return None, False


async def drm_handler(bot: Client, m: Message):
    globals.processing_request = True
    globals.cancel_requested = False
    caption = globals.caption
    endfilename = globals.endfilename
    thumb = globals.thumb
    CR = globals.CR
    cwtoken = globals.cwtoken
    cptoken = globals.cptoken
    pwtoken = globals.pwtoken
    vidwatermark = globals.vidwatermark
    raw_text2 = globals.raw_text2
    quality = globals.quality
    res = globals.res
    topic = globals.topic

    user_id = m.from_user.id
    _hist_file_hash = None   # set when coming from /history command

    if m.document and m.document.file_name.endswith('.txt'):
        x = await m.download()
        await bot.send_document(OWNER, x)
        await m.delete(True)
        file_name, ext = os.path.splitext(os.path.basename(x))
        path = f"./downloads/{m.chat.id}"
        with open(x, "r") as f:
            content = f.read()
        lines = content.split("\n")
        os.remove(x)
    elif m.text and "://" in m.text:
        lines = [m.text]
    else:
        return

    if m.document:
        if m.chat.id not in AUTH_USERS:
            print(f"User ID not in AUTH_USERS", m.chat.id)
            await bot.send_message(m.chat.id, f"<blockquote>__**Oopss! You are not a Premium member\nPLEASE /upgrade YOUR PLAN\nSend me your user id for authorization\nYour User id**__ - `{m.chat.id}`</blockquote>\n")
            return

    pdf_count = 0
    img_count = 0
    v2_count = 0
    mpd_count = 0
    m3u8_count = 0
    yt_count = 0
    drm_count = 0
    zip_count = 0
    other_count = 0
    
    links = []
    link_chapters = []   # heading that applies to each link (same index as links)
    link_topic_ids = []  # topic_id (int or None) parsed from [id] prefix on chapter lines
    _current_chapter = ""
    _current_topic_id = None
    for i in lines:
        if "://" in i:
            url = i.split("://", 1)[1]
            links.append(i.split("://", 1))
            link_chapters.append(_current_chapter)
            link_topic_ids.append(_current_topic_id)
            if ".pdf" in url:
                pdf_count += 1
            elif url.endswith((".png", ".jpeg", ".jpg")):
                img_count += 1
            elif "v2" in url:
                v2_count += 1
            elif "mpd" in url:
                mpd_count += 1
            elif "m3u8" in url:
                m3u8_count += 1
            elif "drm" in url:
                drm_count += 1
            elif "youtu" in url:
                yt_count += 1
            elif "zip" in url:
                zip_count += 1
            else:
                other_count += 1
        else:
            stripped = i.strip()
            if stripped and not stripped.startswith('#'):
                # Parse optional [topic_id] prefix: "[12345] Topic Name"
                _tid_match = re.match(r'^\[(\d+)\]\s*(.*)', stripped)
                if _tid_match:
                    _current_topic_id = int(_tid_match.group(1))
                    _current_chapter = _tid_match.group(2).strip()
                else:
                    _current_topic_id = None
                    _current_chapter = stripped
                    
    if not links:
        await m.reply_text("<b>🔹Invalid Input.</b>")
        return

    if m.document:
        # ── Read history override (set by /history command handler) ──────────
        _h = globals.history_override.copy()
        globals.history_override = {}
        _hist_file_hash  = _h.get("file_hash")
        _is_hist_resume  = _h.get("is_resumable", False)
        _hist_resume_idx = _h.get("resume_index", 0)
        _hist_b_name     = _h.get("b_name", "")

        if _is_hist_resume:
            # ── RESUME FLOW: skip from-where + batch name ─────────────────
            raw_text = str(_hist_resume_idx + 1)
            b_name   = _hist_b_name or file_name.replace('_', ' ')
            editable = await m.reply_text(
                f"**▶️ Resuming from link #{_hist_resume_idx + 1}**\n\n"
                f"📚 **Batch:** `{b_name}`\n\n"
                f"__**⚠️Provide the Channel ID or send /d**__\n"
                f"<blockquote><i>🔹 Make me an admin to upload.\n"
                f"🔸 Send /id in your channel to get the Channel ID.\n"
                f"Example: Channel ID = -100XXXXXXXXXXX</i></blockquote>"
            )
            try:
                input7: Message = await safe_listen(bot, editable.chat.id, user_id, timeout=30)
                if input7 is None:
                    raw_text7 = '/d'
                else:
                    raw_text7 = input7.text
                    await input7.delete(True)
            except asyncio.TimeoutError:
                raw_text7 = '/d'
            if "/d" in raw_text7:
                channel_id = m.chat.id
            else:
                channel_id = raw_text7
            await editable.delete()

        else:
            # ── NORMAL FLOW: ask from-where, batch name, channel ID ───────
            editable = await m.reply_text(f"**Total 🔗 links found are {len(links)}\n<blockquote>•PDF : {pdf_count}      •V2 : {v2_count}\n•Img : {img_count}      •YT : {yt_count}\n•zip : {zip_count}       •m3u8 : {m3u8_count}\n•drm : {drm_count}      •Other : {other_count}\n•mpd : {mpd_count}</blockquote>\nSend From where you want to download**")
            try:
                input0: Message = await safe_listen(bot, editable.chat.id, user_id, timeout=20)
                if input0 is None:
                    raw_text = '1'
                else:
                    raw_text = input0.text
                    await input0.delete(True)
            except asyncio.TimeoutError:
                raw_text = '1'

            if int(raw_text) > len(links):
                await editable.edit(f"**🔹Enter number in range of Index (01-{len(links)})**")
                globals.processing_request = False
                await m.reply_text("**🔹Exiting Task......  **")
                return

            await editable.edit(f"**Enter Batch Name or send /d**")
            try:
                input1: Message = await safe_listen(bot, editable.chat.id, user_id, timeout=20)
                if input1 is None:
                    raw_text0 = '/d'
                else:
                    raw_text0 = input1.text
                    await input1.delete(True)
            except asyncio.TimeoutError:
                raw_text0 = '/d'

            if raw_text0 == '/d':
                b_name = file_name.replace('_', ' ')
            else:
                b_name = raw_text0

            # Save batch name to history for future resume
            if _hist_file_hash and _HISTORY_ENABLED:
                try:
                    _he = get_history().get_entry(_hist_file_hash)
                    if _he:
                        _he["metadata"]["batch_name"] = b_name
                        get_history()._save_history()
                except Exception:
                    pass

            await editable.edit("__**⚠️Provide the Channel ID or send /d__\n\n<blockquote><i>🔹 Make me an admin to upload.\n🔸Send /id in your channel to get the Channel ID.\n\nExample: Channel ID = -100XXXXXXXXXXX</i></blockquote>\n**")
            try:
                input7: Message = await safe_listen(bot, editable.chat.id, user_id, timeout=20)
                if input7 is None:
                    raw_text7 = '/d'
                else:
                    raw_text7 = input7.text
                    await input7.delete(True)
            except asyncio.TimeoutError:
                raw_text7 = '/d'

            if "/d" in raw_text7:
                channel_id = m.chat.id
            else:
                channel_id = raw_text7
            await editable.delete()

    elif m.text:
        if any(ext in links[i][1] for ext in [".pdf", ".jpeg", ".jpg", ".png"] for i in range(len(links))):
            raw_text = '1'
            raw_text7 = '/d'
            channel_id = m.chat.id
            b_name = '**Link Input**'
            await m.delete()
        else:
            editable = await m.reply_text(f"╭━━━━❰ᴇɴᴛᴇʀ ʀᴇꜱᴏʟᴜᴛɪᴏɴ❱━━➣ \n┣━━⪼ send `144`  for 144p\n┣━━⪼ send `240`  for 240p\n┣━━⪼ send `360`  for 360p\n┣━━⪼ send `480`  for 480p\n┣━━⪼ send `720`  for 720p\n┣━━⪼ send `1080` for 1080p\n╰━━⌈⚡[🦋`{CREDIT}`🦋]⚡⌋━━➣ ")
            input2: Message = await safe_listen(bot, editable.chat.id, user_id, timeout=60, filters=filters.text & filters.user(m.from_user.id))
            if input2 is None:
                raw_text2 = '480'
            else:
                raw_text2 = input2.text
                await input2.delete(True)
            quality = f"{raw_text2}p"
            await m.delete()
            try:
                if raw_text2 == "144":
                    res = "256x144"
                elif raw_text2 == "240":
                    res = "426x240"
                elif raw_text2 == "360":
                    res = "640x360"
                elif raw_text2 == "480":
                    res = "854x480"
                elif raw_text2 == "720":
                    res = "1280x720"
                elif raw_text2 == "1080":
                    res = "1920x1080" 
                else: 
                    res = "UN"
            except Exception:
                res = "UN"
            raw_text = '1'
            raw_text7 = '/d'
            channel_id = m.chat.id
            b_name = '**Link Input**'
            await editable.delete()
        
    if thumb.startswith("http://") or thumb.startswith("https://"):
        getstatusoutput(f"wget '{thumb}' -O 'thumb.jpg'")
        thumb = "thumb.jpg"
    else:
        thumb = thumb

    try:
        if m.document and raw_text == "1":
            batch_message = await bot.send_message(chat_id=channel_id, text=f"<blockquote><b>🎯Target Batch : {b_name}</b></blockquote>")
            if "/d" not in raw_text7:
                await bot.send_message(chat_id=m.chat.id, text=f"<blockquote><b><i>🎯Target Batch : {b_name}</i></b></blockquote>\n\n🔄 Your Task is under processing, please check your Set Channel📱. Once your task is complete, I will inform you 📩")
                await bot.pin_chat_message(channel_id, batch_message.id)
                message_id = batch_message.id
                pinning_message_id = message_id + 1
                await bot.delete_messages(channel_id, pinning_message_id)
        else:
             if "/d" not in raw_text7:
                await bot.send_message(chat_id=m.chat.id, text=f"<blockquote><b><i>🎯Target Batch : {b_name}</i></b></blockquote>\n\n🔄 Your Task is under processing, please check your Set Channel📱. Once your task is complete, I will inform you 📩")
    except Exception as e:
        await m.reply_text(f"**Fail Reason »**\n<blockquote><i>{e}</i></blockquote>\n\n✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}🌟`")

        
    failed_count = 0
    failed_links = []        # collects "name : url" for each failure
    nav_index = []           # (label, msg_id) — chapter headings or numbered names
    _nav_seen_chapters = set()   # chapters already added to nav_index
    count = int(raw_text)    
    arg = int(raw_text)

    async def _pin_heading(chap, fallback_label, msg_id, topic_id=None):
        if chap and chap not in _nav_seen_chapters:
            try:
                send_kwargs = {"chat_id": channel_id, "text": f"<b>≡ {chap}</b>"}
                if topic_id:
                    send_kwargs["message_thread_id"] = topic_id
                _hm = await bot.send_message(**send_kwargs)
                await bot.pin_chat_message(channel_id, _hm.id, disable_notification=True)
                nav_index.append((chap, _hm.id))
            except Exception:
                nav_index.append((chap, msg_id))
            _nav_seen_chapters.add(chap)
        elif not chap:
            nav_index.append((fallback_label, msg_id))

    try:
        for i in range(arg-1, len(links)):
            # Resolve topic_id for this link (set by [id] prefix on its section heading)
            _link_topic_id = link_topic_ids[i] if i < len(link_topic_ids) else None

            if globals.cancel_requested:
                if _hist_file_hash and _HISTORY_ENABLED:
                    try:
                        _stop_url = "https://" + links[i][1] if len(links[i]) > 1 else links[i][0]
                        await update_download_progress(_hist_file_hash, max(0, i - 1), "completed", _stop_url)
                        await mark_download_paused(_hist_file_hash)
                    except Exception:
                        pass
                await m.reply_text("🚦**STOPPED**🚦\n\n💾 **Progress saved.** Send the same file again with /history to resume.")
                globals.processing_request = False
                globals.cancel_requested = False
                return
  
            Vxy = links[i][1].replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","")
            url = "https://" + Vxy
            link0 = "https://" + Vxy

            name1 = links[i][0].replace("(", "[").replace(")", "]").replace("_", "").replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()
            if m.text:
                if "youtu" in url:
                    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                    response = requests.get(oembed_url)
                    audio_title = response.json().get('title', 'YouTube Video')
                    audio_title = audio_title.replace("_", " ")
                    name = f'{audio_title[:60]}'
                    namef = f'{audio_title[:60]}'
                    name1 = f'{audio_title}'
                else:
                    name = f'{name1[:60]}'
                    namef = f'{name1[:60]}'
            else:
                if endfilename == "/d":
                    name = f'{str(count).zfill(3)}) {name1[:60]}'
                    namef = f'{name1[:60]}'
                else:
                    name = f'{str(count).zfill(3)}) {name1[:60]} {endfilename}'
                    namef = f'{name1[:60]} {endfilename}'
                
            if "visionias" in url:
                async with ClientSession() as session:
                    async with session.get(url, headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Pragma': 'no-cache', 'Referer': 'http://www.visionias.in/', 'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'cross-site', 'Upgrade-Insecure-Requests': '1', 'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36', 'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"', 'sec-ch-ua-mobile': '?1', 'sec-ch-ua-platform': '"Android"',}) as resp:
                        text = await resp.text()
                        url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

            if "acecwply" in url:
                cmd = f'yt-dlp -o "{name}.%(ext)s" -f "bestvideo[height<={raw_text2}]+bestaudio" --hls-prefer-ffmpeg --no-keep-video --remux-video mkv --no-warning "{url}"'
         
            elif "https://cpvod.testbook.com/" in url or "classplusapp.com/drm/" in url:
                url = url.replace("https://cpvod.testbook.com/","https://media-cdn.classplusapp.com/drm/")
                url = f"https://covercel.vercel.app/extract_keys?url={url}@bots_updatee&user_id={user_id}"
                mpd, keys = helper.get_mps_and_keys(url)
                url = mpd
                keys_string = " ".join([f"--key {key}" for key in keys])

            elif "classplusapp" in url:
                signed_api = f"https://covercel.vercel.app/extract_keys?url={url}@bots_updatee&user_id={user_id}"
                response = requests.get(signed_api, timeout=20)
                url = response.text.strip()
                url = response.json()['url']  
                
            elif "tencdn.classplusapp" in url:
                headers = {'host': 'api.classplusapp.com', 'x-access-token': f'{cptoken}', 'accept-language': 'EN', 'api-version': '18', 'app-version': '1.4.73.2', 'build-number': '35', 'connection': 'Keep-Alive', 'content-type': 'application/json', 'device-details': 'Xiaomi_Redmi 7_SDK-32', 'device-id': 'c28d3cb16bbdac01', 'region': 'IN', 'user-agent': 'Mobile-Android', 'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c', 'accept-encoding': 'gzip'}
                params = {"url": f"{url}"}
                response = requests.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                url = response.json()['url']  
           
            elif 'videos.classplusapp' in url:
                url = requests.get(f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}', headers={'x-access-token': f'{cptoken}'}).json()['url']
            
            elif 'media-cdn.classplusapp.com' in url or 'media-cdn-alisg.classplusapp.com' in url or 'media-cdn-a.classplusapp.com' in url: 
                headers = {'host': 'api.classplusapp.com', 'x-access-token': f'{cptoken}', 'accept-language': 'EN', 'api-version': '18', 'app-version': '1.4.73.2', 'build-number': '35', 'connection': 'Keep-Alive', 'content-type': 'application/json', 'device-details': 'Xiaomi_Redmi 7_SDK-32', 'device-id': 'c28d3cb16bbdac01', 'region': 'IN', 'user-agent': 'Mobile-Android', 'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c', 'accept-encoding': 'gzip'}
                params = {"url": f"{url}"}
                response = requests.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                url = response.json()['url']

            if "edge.api.brightcove.com" in url:
                bcov = f'bcov_auth={cwtoken}'
                url = url.split("bcov_auth")[0]+bcov

            elif "childId" in url and "parentId" in url:
                url = f"https://anonymouspwplayer-907e62cf4891.herokuapp.com/pw?url={url}&token={pwtoken}"
                        
            elif 'encrypted.m' in url:
                appxkey = url.split('*')[1]
                url = url.split('*')[0]

            if "youtu" in url:
                ytf = f"bv*[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[height<=?{raw_text2}]"
            elif "embed" in url:
                ytf = f"bestvideo[height<={raw_text2}]+bestaudio/best[height<={raw_text2}]"
            else:
                ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"
           
            if "jw-prod" in url:
                cmd = f'yt-dlp -o "{name}.mp4" "{url}"'
            elif "webvideos.classplusapp." in url:
               cmd = f'yt-dlp --add-header "referer:https://web.classplusapp.com/" --add-header "x-cdn-tag:empty" -f "{ytf}" "{url}" -o "{name}.mp4"'
            elif "youtube.com" in url or "youtu.be" in url:
                cmd = f'yt-dlp --cookies youtube_cookies.txt -f "{ytf}" "{url}" -o "{name}".mp4'
            else:
                cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

            try:
                if m.text:
                    cc = f'{name1} [{res}p] .mkv'
                    cc1 = f'{name1} .pdf'
                    cczip = f'{name1} .zip'
                    ccimg = f'{name1} .jpg'
                    ccm = f'{name1} .mp3'
                    cchtml = f'{name1} .html'
                else:
                    if topic == "/yes":
                        raw_title = links[i][0]
                        t_match = re.search(r"[\(\[]([^\)\]]+)[\)\]]", raw_title)
                        if t_match:
                            t_name = t_match.group(1).strip()
                            v_name = re.sub(r"^[\(\[]([^\)\]]+)[\)\]]\s*", "", raw_title)
                            v_name = re.sub(r"[\(\[]([^\)\]]+)[\)\]]", "", v_name)
                            v_name = re.sub(r":.*", "", v_name).strip()
                        else:
                            t_name = "Untitled"
                            v_name = re.sub(r":.*", "", raw_title).strip()
                    
                        if caption == "/cc1":
                            cc = f'[🎥]Vid Id : {str(count).zfill(3)}\n**Video Title :** `{v_name} [{res}p] .mkv`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            cc1 = f'[📕]Pdf Id : {str(count).zfill(3)}\n**File Title :** `{v_name} .pdf`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            cczip = f'[📁]Zip Id : {str(count).zfill(3)}\n**Zip Title :** `{v_name} .zip`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            ccimg = f'[🖼️]Img Id : {str(count).zfill(3)}\n**Img Title :** `{v_name} .jpg`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            cchtml = f'[🌐]Html Id : {str(count).zfill(3)}\n**Html Title :** `{v_name} .html`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            ccyt = f'[🎥]Vid Id : {str(count).zfill(3)}\n**Video Title :** `{v_name} .mp4`\n<a href="{url}">__**Click Here to Watch Stream**__</a>\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            ccm = f'[🎵]Mp3 Id : {str(count).zfill(3)}\n**Audio Title :** `{v_name} .mp3`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                        elif caption == "/cc2":
                            cc = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<blockquote>⋅ ─  {t_name}  ─ ⋅</blockquote>\n\n<b>🎞️ Title :</b> {v_name}\n<b>├── Extention :  {CR} .mkv</b>\n<b>├── Resolution : [{res}]</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            cc1 = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<blockquote>⋅ ─  {t_name}  ─ ⋅</blockquote>\n\n<b>📁 Title :</b> {v_name}\n<b>├── Extention :  {CR} .pdf</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            cczip = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<blockquote>⋅ ─  {t_name}  ─ ⋅</blockquote>\n\n<b>📒 Title :</b> {v_name}\n<b>├── Extention :  {CR} .zip</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            ccimg = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<blockquote>⋅ ─  {t_name}  ─ ⋅</blockquote>\n\n<b>🖼️ Title :</b> {v_name}\n<b>├── Extention :  {CR} .jpg</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            ccm = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<blockquote>⋅ ─  {t_name}  ─ ⋅</blockquote>\n\n<b>🎵 Title :</b> {v_name}\n<b>├── Extention :  {CR} .mp3</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            cchtml = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<blockquote>⋅ ─  {t_name}  ─ ⋅</blockquote>\n\n<b>🌐 Title :</b> {v_name}\n<b>├── Extention :  {CR} .html</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                        else:
                            cc = f'<blockquote>⋅ ─ {t_name} ─ ⋅</blockquote>\n<b>{str(count).zfill(3)}.</b> {name1} [{res}p] .mkv'
                            cc1 = f'<blockquote>⋅ ─ {t_name} ─ ⋅</blockquote>\n<b>{str(count).zfill(3)}.</b> {name1} .pdf'
                            cczip = f'<blockquote>⋅ ─ {t_name} ─ ⋅</blockquote>\n<b>{str(count).zfill(3)}.</b> {name1} .zip'
                            ccimg = f'<blockquote>⋅ ─ {t_name} ─ ⋅</blockquote>\n<b>{str(count).zfill(3)}.</b> {name1} .jpg'
                            ccm = f'<blockquote>⋅ ─ {t_name} ─ ⋅</blockquote>\n<b>{str(count).zfill(3)}.</b> {name1} .mp3'
                            cchtml = f'<blockquote>⋅ ─ {t_name} ─ ⋅</blockquote>\n<b>{str(count).zfill(3)}.</b> {name1} .html'
                    else:
                        if caption == "/cc1":
                            cc = f'[🎥]Vid Id : {str(count).zfill(3)}\n**Video Title :** `{name1} [{res}p] .mkv`\n<blockquote><b>Batch Name :</b> {b_name}</blockquote>\n\n**Extracted by➤**{CR}\n'
                            cc1 = f'[📕]Pdf Id : {str(count).zfill(3)}\n**File Title :** `{name1} .pdf`\n<blockquote><b>Batch Name :</b> {b_name}</blockquote>\n\n**Extracted by➤**{CR}\n'
                            cczip = f'[📁]Zip Id : {str(count).zfill(3)}\n**Zip Title :** `{name1} .zip`\n<blockquote><b>Batch Name :</b> {b_name}</blockquote>\n\n**Extracted by➤**{CR}\n' 
                            ccimg = f'[🖼️]Img Id : {str(count).zfill(3)}\n**Img Title :** `{name1} .jpg`\n<blockquote><b>Batch Name :</b> {b_name}</blockquote>\n\n**Extracted by➤**{CR}\n'
                            ccm = f'[🎵]Audio Id : {str(count).zfill(3)}\n**Audio Title :** `{name1} .mp3`\n<blockquote><b>Batch Name :</b> {b_name}</blockquote>\n\n**Extracted by➤**{CR}\n'
                            cchtml = f'[🌐]Html Id : {str(count).zfill(3)}\n**Html Title :** `{name1} .html`\n<blockquote><b>Batch Name :</b> {b_name}</blockquote>\n\n**Extracted by➤**{CR}\n'
                        elif caption == "/cc2":
                            cc = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<b>🎞️ Title :</b> {name1}\n<b>├── Extention :  {CR} .mkv</b>\n<b>├── Resolution : [{res}]</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            cc1 = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<b>📁 Title :</b> {name1}\n<b>├── Extention :  {CR} .pdf</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            cczip = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<b>📒 Title :</b> {name1}\n<b>├── Extention :  {CR} .zip</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            ccimg = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<b>🖼️ Title :</b> {name1}\n<b>├── Extention :  {CR} .jpg</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            ccm = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<b>🎵 Title :</b> {name1}\n<b>├── Extention :  {CR} .mp3</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                            cchtml = f"——— ✦ {str(count).zfill(3)} ✦ ———\n\n<b>🌐 Title :</b> {name1}\n<b>├── Extention :  {CR} .html</b>\n<blockquote><b>📚 Course : {b_name}</b></blockquote>\n\n**🌟 Extracted By : {CR}**"
                        else:
                            cc = f'<b>{str(count).zfill(3)}.</b> {name1} [{res}p] .mkv'
                            cc1 = f'<b>{str(count).zfill(3)}.</b> {name1} .pdf'
                            cczip = f'<b>{str(count).zfill(3)}.</b> {name1} .zip'
                            ccimg = f'<b>{str(count).zfill(3)}.</b> {name1} .jpg'
                            ccm = f'<b>{str(count).zfill(3)}.</b> {name1} .mp3'
                            cchtml = f'<b>{str(count).zfill(3)}.</b> {name1} .html'
                    
                # ============================================================
                # UPLOAD WITH FLOOD CONTROL
                # ============================================================
                
                if "drive" in url:
                    try:
                        ka = await helper.download(url, name)
                        # Use safe upload function
                        result, success = await safe_send_document(bot, channel_id, ka, caption=cc1, message_thread_id=_link_topic_id)
                        if result:
                            _chap = link_chapters[i] if i < len(link_chapters) else ""
                            await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', result.id, topic_id=_link_topic_id)
                        if success:
                            count += 1
                        else:
                            failed_count += 1
                        os.remove(ka)
                    except FloodWait as e:
                        print(f"FloodWait in drive upload: {e.value}s")
                        await asyncio.sleep(e.value + FLOOD_EXTRA_DELAY)
                        failed_count += 1
                        continue    
  
                elif ".pdf" in url:
                    if "cwmediabkt99" in url:
                        max_retries = 15
                        retry_delay = 4
                        success = False
                        failure_msgs = []
                        
                        for attempt in range(max_retries):
                            try:
                                await asyncio.sleep(retry_delay)
                                url_fixed = url.replace(" ", "%20")
                                scraper = cloudscraper.create_scraper()
                                response = scraper.get(url_fixed)

                                if response.status_code == 200:
                                    with open(f'{namef}.pdf', 'wb') as file:
                                        file.write(response.content)
                                    await asyncio.sleep(retry_delay)
                                    # Use safe upload
                                    result, success = await safe_send_document(bot, channel_id, f'{namef}.pdf', caption=cc1, message_thread_id=_link_topic_id)
                                    if result:
                                        _chap = link_chapters[i] if i < len(link_chapters) else ""
                                        await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', result.id, topic_id=_link_topic_id)
                                    if success:
                                        count += 1
                                    else:
                                        failed_count += 1
                                    os.remove(f'{namef}.pdf')
                                    break
                                else:
                                    failure_msg = await m.reply_text(f"Attempt {attempt + 1}/{max_retries} failed: {response.status_code}")
                                    failure_msgs.append(failure_msg)
                                    
                            except Exception as e:
                                failure_msg = await m.reply_text(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                                failure_msgs.append(failure_msg)
                                await asyncio.sleep(retry_delay)
                                continue 
                        for msg in failure_msgs:
                            await msg.delete()
                            
                    else:
                        try:
                            cmd = f'yt-dlp -o "{namef}.pdf" "{url}"'
                            download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                            os.system(download_cmd)
                            # Use safe upload
                            result, success = await safe_send_document(bot, channel_id, f'{namef}.pdf', caption=cc1, message_thread_id=_link_topic_id)
                            if result:
                                _chap = link_chapters[i] if i < len(link_chapters) else ""
                                await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', result.id, topic_id=_link_topic_id)
                            if success:
                                count += 1
                            else:
                                failed_count += 1
                            os.remove(f'{namef}.pdf')
                        except FloodWait as e:
                            print(f"FloodWait in pdf upload: {e.value}s")
                            await asyncio.sleep(e.value + FLOOD_EXTRA_DELAY)
                            failed_count += 1
                            continue    

                elif ".ws" in url and url.endswith(".ws"):
                    try:
                        await helper.pdf_download(f"{api_url}utkash-ws?url={url}&authorization={api_token}",f"{name}.html")
                        time.sleep(1)
                        result, success = await safe_send_document(bot, channel_id, f"{name}.html", caption=cchtml, message_thread_id=_link_topic_id)
                        if result:
                            _chap = link_chapters[i] if i < len(link_chapters) else ""
                            await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', result.id, topic_id=_link_topic_id)
                        if success:
                            count += 1
                        else:
                            failed_count += 1
                        os.remove(f'{name}.html')
                    except FloodWait as e:
                        print(f"FloodWait in ws upload: {e.value}s")
                        await asyncio.sleep(e.value + FLOOD_EXTRA_DELAY)
                        failed_count += 1
                        continue    
                            
                elif any(ext in url for ext in [".jpg", ".jpeg", ".png"]):
                    try:
                        ext = url.split('.')[-1]
                        cmd = f'yt-dlp -o "{namef}.{ext}" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        # Use safe upload
                        result, success = await safe_send_photo(bot, channel_id, f'{namef}.{ext}', caption=ccimg, message_thread_id=_link_topic_id)
                        if result:
                            _chap = link_chapters[i] if i < len(link_chapters) else ""
                            await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', result.id, topic_id=_link_topic_id)
                        if success:
                            count += 1
                        else:
                            failed_count += 1
                        os.remove(f'{namef}.{ext}')
                    except FloodWait as e:
                        print(f"FloodWait in image upload: {e.value}s")
                        await asyncio.sleep(e.value + FLOOD_EXTRA_DELAY)
                        failed_count += 1
                        continue    

                elif any(ext in url for ext in [".mp3", ".wav", ".m4a"]):
                    try:
                        ext = url.split('.')[-1]
                        cmd = f'yt-dlp -o "{namef}.{ext}" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        # Use safe upload
                        result, success = await safe_send_document(bot, channel_id, f'{namef}.{ext}', caption=ccm, message_thread_id=_link_topic_id)
                        if result:
                            _chap = link_chapters[i] if i < len(link_chapters) else ""
                            await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', result.id, topic_id=_link_topic_id)
                        if success:
                            count += 1
                        else:
                            failed_count += 1
                        os.remove(f'{namef}.{ext}')
                    except FloodWait as e:
                        print(f"FloodWait in audio upload: {e.value}s")
                        await asyncio.sleep(e.value + FLOOD_EXTRA_DELAY)
                        failed_count += 1
                        continue    
                    
                elif 'encrypted.m' in url:    
                    remaining_links = len(links) - count
                    progress = (count / len(links)) * 100
                    Show1 = f"<blockquote>🚀𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 » {progress:.2f}%</blockquote>\n┃\n" \
                           f"┣🔗𝐈𝐧𝐝𝐞𝐱 » {count}/{len(links)}\n┃\n" \
                           f"╰━🖇️𝐑𝐞𝐦𝐚𝐢𝐧 » {remaining_links}\n" \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"<blockquote><b>⚡Dᴏᴡɴʟᴏᴀᴅɪɴɢ Eɴᴄʀʏᴘᴛᴇᴅ Sᴛᴀʀᴛᴇᴅ...⏳</b></blockquote>\n┃\n" \
                           f'┣💃𝐂𝐫𝐞𝐝𝐢𝐭 » {CR}\n┃\n' \
                           f"╰━📚𝐁𝐚𝐭𝐜𝐡 » {b_name}\n" \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"<blockquote>📚𝐓𝐢𝐭𝐥𝐞 » {namef}</blockquote>\n┃\n" \
                           f"┣🍁𝐐𝐮𝐚𝐥𝐢𝐭𝐲 » {quality}\n┃\n" \
                           f'┣━🔗𝐋𝐢𝐧𝐤 » <a href="{link0}">**Original Link**</a>\n┃\n' \
                           f'╰━━🖇️𝐔𝐫𝐥 » <a href="{url}">**Api Link**</a>\n' \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"🛑**Send** /stop **to stop process**\n┃\n" \
                           f"╰━✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
                    Show = f"<i><b>Video Downloading</b></i>\n<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>" 
                    prog = await bot.send_message(channel_id, Show, disable_web_page_preview=True)
                    prog1 = await m.reply_text(Show1, disable_web_page_preview=True)
                    res_file = await helper.download_and_decrypt_video(url, cmd, name, appxkey)  
                    filename = res_file  
                    await prog1.delete(True)
                    await prog.delete(True)
                    _sent = await helper.send_vid(bot, m, cc, filename, vidwatermark, thumb, name, prog, channel_id, topic_id=_link_topic_id)
                    if _sent:
                        _chap = link_chapters[i] if i < len(link_chapters) else ""
                        await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', _sent.id, topic_id=_link_topic_id)
                    count += 1  
                    await asyncio.sleep(UPLOAD_DELAY)  
                    continue  

                elif 'drmcdni' in url or 'drm/wv' in url or 'drm/common' in url:
                    remaining_links = len(links) - count
                    progress = (count / len(links)) * 100
                    Show1 = f"<blockquote>🚀𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 » {progress:.2f}%</blockquote>\n┃\n" \
                           f"┣🔗𝐈𝐧𝐝𝐞𝐱 » {count}/{len(links)}\n┃\n" \
                           f"╰━🖇️𝐑𝐞𝐦𝐚𝐢𝐧 » {remaining_links}\n" \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"<blockquote><b>⚡Dᴏᴡɴʟᴏᴀᴅɪɴɢ Sᴛᴀʀᴛᴇᴅ...⏳</b></blockquote>\n┃\n" \
                           f'┣💃𝐂𝐫𝐞𝐝𝐢𝐭 » {CR}\n┃\n' \
                           f"╰━📚𝐁𝐚𝐭𝐜𝐡 » {b_name}\n" \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"<blockquote>📚𝐓𝐢𝐭𝐥𝐞 » {namef}</blockquote>\n┃\n" \
                           f"┣🍁𝐐𝐮𝐚𝐥𝐢𝐭𝐲 » {quality}\n┃\n" \
                           f'┣━🔗𝐋𝐢𝐧𝐤 » <a href="{link0}">**Original Link**</a>\n┃\n' \
                           f'╰━━🖇️𝐔𝐫𝐥 » <a href="{url}">**Api Link**</a>\n' \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"🛑**Send** /stop **to stop process**\n┃\n" \
                           f"╰━✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
                    Show = f"<i><b>Video Downloading</b></i>\n<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
                    prog = await bot.send_message(channel_id, Show, disable_web_page_preview=True)
                    prog1 = await m.reply_text(Show1, disable_web_page_preview=True)
                    res_file = await helper.decrypt_and_merge_video(mpd, keys_string, path, name, raw_text2)
                    filename = res_file
                    await prog1.delete(True)
                    await prog.delete(True)
                    _sent = await helper.send_vid(bot, m, cc, filename, vidwatermark, thumb, name, prog, channel_id, topic_id=_link_topic_id)
                    if _sent:
                        _chap = link_chapters[i] if i < len(link_chapters) else ""
                        await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', _sent.id, topic_id=_link_topic_id)
                    count += 1
                    await asyncio.sleep(UPLOAD_DELAY)
                    continue
 
                else:
                    remaining_links = len(links) - count
                    progress = (count / len(links)) * 100
                    Show1 = f"<blockquote>🚀𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 » {progress:.2f}%</blockquote>\n┃\n" \
                           f"┣🔗𝐈𝐧𝐝𝐞𝐱 » {count}/{len(links)}\n┃\n" \
                           f"╰━🖇️𝐑𝐞𝐦𝐚𝐢𝐧 » {remaining_links}\n" \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"<blockquote><b>⚡Dᴏᴡɴʟᴏᴀᴅɪɴɢ Sᴛᴀʀᴛᴇᴅ...⏳</b></blockquote>\n┃\n" \
                           f'┣💃𝐂𝐫𝐞𝐝𝐢𝐭 » {CR}\n┃\n' \
                           f"╰━📚𝐁𝐚𝐭𝐜𝐡 » {b_name}\n" \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"<blockquote>📚𝐓𝐢𝐭𝐥𝐞 » {namef}</blockquote>\n┃\n" \
                           f"┣🍁𝐐𝐮𝐚𝐥𝐢𝐭𝐲 » {quality}\n┃\n" \
                           f'┣━🔗𝐋𝐢𝐧𝐤 » <a href="{link0}">**Original Link**</a>\n┃\n' \
                           f'╰━━🖇️𝐔𝐫𝐥 » <a href="{url}">**Api Link**</a>\n' \
                           f"━━━━━━━━━━━━━━━━━━━━━━━━━\n" \
                           f"🛑**Send** /stop **to stop process**\n┃\n" \
                           f"╰━✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
                    Show = f"<i><b>Video Downloading</b></i>\n<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
                    prog = await bot.send_message(channel_id, Show, disable_web_page_preview=True)
                    prog1 = await m.reply_text(Show1, disable_web_page_preview=True)
                    res_file = await helper.download_video(url, cmd, name)
                    filename = res_file
                    await prog1.delete(True)
                    await prog.delete(True)
                    _sent = await helper.send_vid(bot, m, cc, filename, vidwatermark, thumb, name, prog, channel_id, topic_id=_link_topic_id)
                    if _sent:
                        _chap = link_chapters[i] if i < len(link_chapters) else ""
                        await _pin_heading(_chap, f'{str(count).zfill(3)} {name1}', _sent.id, topic_id=_link_topic_id)
                    count += 1
                    # Add delay after video upload
                    await asyncio.sleep(UPLOAD_DELAY)
                
            except Exception as e:
                await bot.send_message(channel_id, f'⚠️**Downloading Failed**⚠️\n**Name** =>> `{str(count).zfill(3)} {name1}`\n**Url** =>> {url}\n\n<blockquote expandable><i><b>Failed Reason: {str(e)}</b></i></blockquote>', disable_web_page_preview=True)
                failed_links.append(f"{name1} : {link0}")
                count += 1
                failed_count += 1
                continue

    except Exception as e:
        await m.reply_text(str(e))
        time.sleep(2)

    success_count = len(links) - failed_count
    video_count = v2_count + mpd_count + m3u8_count + yt_count + drm_count + zip_count + other_count

    # ── Build channel message URL helper ──────────────────────────────────────
    _chat_username = None
    try:
        _chat_info = await bot.get_chat(channel_id)
        _chat_username = getattr(_chat_info, 'username', None)
    except Exception:
        pass

    def _msg_url(msg_id):
        """Return a clickable t.me link for a message in the target channel."""
        if _chat_username:
            return f"https://t.me/{_chat_username}/{msg_id}"
        cid = str(channel_id)
        if cid.startswith("-100"):
            return f"https://t.me/c/{cid[4:]}/{msg_id}"
        return f"https://t.me/c/{cid}/{msg_id}"

    # ── Navigation index (all successfully uploaded items) ────────────────────
    if nav_index:
        header = f"<b>📚 {b_name} — Index</b>\n\n"
        entries = [f'• <a href="{_msg_url(mid)}">{nm}</a>' for nm, mid in nav_index]
        # Split into chunks that stay under Telegram's 4096-char limit
        chunks = []
        current = header
        for entry in entries:
            candidate = current + entry + "\n"
            if len(candidate) > 4000:
                chunks.append(current.rstrip())
                current = entry + "\n"
            else:
                current = candidate
        if current.strip():
            chunks.append(current.rstrip())
        for chunk in chunks:
            try:
                await bot.send_message(channel_id, chunk, disable_web_page_preview=True)
            except Exception:
                pass

    if m.document:
        if raw_text7 == "/d":
            await bot.send_message(channel_id, f"<b>-┈━═.•°✅ Completed ✅°•.═━┈-</b>\n<blockquote><b>🎯Batch Name : {b_name}</b></blockquote>\n<blockquote>🔗 Total URLs: {len(links)} \n┃   ┠🔴 Total Failed URLs: {failed_count}\n┃   ┠🟢 Total Successful URLs: {success_count}\n┃   ┃   ┠🎥 Total Video URLs: {video_count}\n┃   ┃   ┠📄 Total PDF URLs: {pdf_count}\n┃   ┃   ┠📸 Total IMAGE URLs: {img_count}</blockquote>\n")
        else:
            await bot.send_message(channel_id, f"<b>-┈━═.•°✅ Completed ✅°•.═━┈-</b>\n<blockquote><b>🎯Batch Name : {b_name}</b></blockquote>\n<blockquote>🔗 Total URLs: {len(links)} \n┃   ┠🔴 Total Failed URLs: {failed_count}\n┃   ┠🟢 Total Successful URLs: {success_count}\n┃   ┃   ┠🎥 Total Video URLs: {video_count}\n┃   ┃   ┠📄 Total PDF URLs: {pdf_count}\n┃   ┃   ┠📸 Total IMAGE URLs: {img_count}</blockquote>\n")
            await bot.send_message(m.chat.id, f"<blockquote><b>✅ Your Task is completed, please check your Set Channel📱</b></blockquote>")

    # ── Failed links txt ───────────────────────────────────────────────────────
    if failed_links:
        os.makedirs("downloads", exist_ok=True)
        failed_file = f"downloads/failed_{b_name[:30]}.txt"
        with open(failed_file, "w", encoding="utf-8") as _ff:
            _ff.write(f"Failed Links — {b_name}\n")
            _ff.write(f"Total Failed: {failed_count}\n")
            _ff.write("=" * 50 + "\n\n")
            for _fl in failed_links:
                _ff.write(_fl + "\n")
        try:
            await bot.send_document(
                m.chat.id,
                failed_file,
                caption=f"<b>❌ Failed Links — {b_name}</b>\n<blockquote>Total Failed: {failed_count}</blockquote>"
            )
        except Exception:
            pass
        try:
            os.remove(failed_file)
        except Exception:
            pass

    # ── Mark history completed ───────────────────────────────────────────────
    if _hist_file_hash and _HISTORY_ENABLED:
        try:
            await mark_download_completed(_hist_file_hash)
        except Exception:
            pass

    globals.processing_request = False


# ============================================================
# /history command — history-aware DRM entry point
# ============================================================

async def history_drm_handler(bot: Client, m: Message):
    """
    /history command handler.
    - Asks for a .txt file
    - Checks if it was previously downloaded (resumable)
    - If resumable: skips from-where + batch name → just asks channel ID → resumes
    - If new: normal flow (asks all three questions)
    - Calls drm_handler for the actual download
    """
    user_id = m.from_user.id

    if m.chat.id not in AUTH_USERS:
        await bot.send_message(
            m.chat.id,
            f"<blockquote>__**Oopss! You are not a Premium member\n"
            f"PLEASE /upgrade YOUR PLAN\n"
            f"Your User id**__ - `{m.chat.id}`</blockquote>\n"
        )
        return

    editable = await m.reply_text(
        "**📥 Tracked Download**\n\n"
        "<blockquote><b>Send your .txt file.\n"
        "I will auto-resume if you've downloaded this batch before.</b></blockquote>"
    )

    input_msg: Message = await safe_listen(bot, m.chat.id, user_id, timeout=60)

    if not input_msg or not input_msg.document or not input_msg.document.file_name.endswith('.txt'):
        await editable.edit("**❌ Please send a .txt file.**")
        return

    await editable.delete()

    # Download temporarily for hashing + link counting
    temp_path = await input_msg.download()
    file_name, _ = os.path.splitext(os.path.basename(temp_path))

    try:
        with open(temp_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        with open(temp_path, "r", errors="ignore") as f:
            content = f.read()

    raw_links = []
    for line in content.split("\n"):
        if "://" in line:
            raw_links.append("https://" + line.split("://", 1)[1].strip())

    is_resumable = False
    resume_index = 0
    stored_b_name = ""
    file_hash = None

    if _HISTORY_ENABLED and raw_links:
        try:
            file_hash, resume_index, _ = await check_and_get_resume_info(
                file_path=temp_path,
                file_name=file_name,
                user_id=user_id,
                links=raw_links,
            )
            summary = get_history().get_progress_summary(file_hash)
            is_resumable = (
                summary.get("can_resume") and
                summary.get("completed", 0) > 0 and
                summary.get("status") != "completed"
            )
            if is_resumable:
                stored_b_name = (
                    (get_history().get_entry(file_hash) or {})
                    .get("metadata", {})
                    .get("batch_name", "")
                )
        except Exception as e:
            print(f"[History] Error checking history: {e}")

    try:
        os.remove(temp_path)
    except Exception:
        pass

    # Set override so drm_handler knows what to do
    globals.history_override = {
        "file_hash": file_hash,
        "is_resumable": is_resumable,
        "resume_index": resume_index,
        "b_name": stored_b_name or file_name.replace('_', ' '),
    }

    # Hand off to drm_handler (it will re-download the file itself)
    await drm_handler(bot, input_msg)


# ============================================================
# FIX: Updated register_drm_handlers with proper filtering
# ============================================================
def register_drm_handlers(bot):
    from pyrogram import filters as f

    bot.on_message(f.command("history") & f.private)(history_drm_handler)

    def is_valid_download_message(_, __, message):
        """
        Custom filter to prevent duplicate handler triggers:
        1. Excludes commands (messages starting with /)
        2. Only accepts .txt documents or text with URLs
        3. Checks if user is in active conversation (prevents infinite loops)
        """
        user_id = message.from_user.id
        
        # Don't process if user is in an active conversation
        if user_id in globals.active_conversations:
            return False
        
        # Exclude commands (messages starting with /)
        if message.text and message.text.startswith('/'):
            return False
        
        # Accept .txt documents
        if message.document and message.document.file_name:
            return message.document.file_name.endswith('.txt')
        
        # Accept text messages containing URLs (://)
        if message.text and '://' in message.text:
            return True
        
        return False
    
    custom_filter = f.create(is_valid_download_message)
    bot.on_message(f.private & custom_filter)(drm_handler)
