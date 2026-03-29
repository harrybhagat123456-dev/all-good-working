"""
Telegram Forum Topics Handler
==============================
Handles automatic topic creation and message routing to specific topics
in Telegram groups/channels with the Topics feature enabled.
"""

import os
import json
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import BadRequest, Forbidden, FloodWait, ChatAdminRequired, TopicDeleted
from vars import OWNER

try:
    from txt_topic_parser import parse_txt_file, get_topics_from_txt, get_content_for_topic
    TXT_PARSER_AVAILABLE = True
except ImportError:
    TXT_PARSER_AVAILABLE = False

TOPIC_CONFIG_FILE = "topic_config.json"

DEFAULT_TOPICS = {
    "notices": {"name": "📢 Notices", "icon": "📢"},
    "uploads": {"name": "📤 Uploads", "icon": "📤"},
    "videos": {"name": "🎥 Videos", "icon": "🎥"},
    "pdfs": {"name": "📄 PDFs", "icon": "📄"},
    "general": {"name": "💬 General", "icon": "💬"},
}

CATEGORY_TOPICS = {
    "video": "videos",
    "pdf": "pdfs",
    "notice": "notices",
    "upload": "uploads",
}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_topic_config() -> dict:
    if os.path.exists(TOPIC_CONFIG_FILE):
        try:
            with open(TOPIC_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_topic_config(config: dict):
    with open(TOPIC_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_chat_config(chat_id: int) -> dict:
    config = load_topic_config()
    key = str(chat_id)
    if key not in config:
        config[key] = {
            "topics": {},
            "txt_topics": {},
            "default_topic": None,
            "auto_create": True,
            "category_mapping": CATEGORY_TOPICS.copy(),
        }
        save_topic_config(config)
    return config[key]


def update_chat_config(chat_id: int, chat_config: dict):
    config = load_topic_config()
    config[str(chat_id)] = chat_config
    save_topic_config(config)


# ---------------------------------------------------------------------------
# Core topic operations
# ---------------------------------------------------------------------------

async def create_forum_topic(client: Client, chat_id: int, topic_name: str, icon_color: int = None):
    """Create a forum topic using the raw API for reliability.
    Returns (topic_id, error_str) — topic_id is the message thread ID on success.
    """
    from pyrogram import raw as pyrogram_raw

    async def _do_create():
        peer = await client.resolve_peer(chat_id)
        r = await client.invoke(
            pyrogram_raw.functions.messages.CreateForumTopic(
                channel=peer,
                title=topic_name,
                random_id=client.rnd_id(),
                icon_color=icon_color,
            )
        )
        # Walk all updates to find the service message — its ID is the topic ID
        for update in r.updates:
            msg = getattr(update, "message", None)
            if msg and getattr(msg, "id", None):
                return msg.id
        # Fallback: try updates[1] if the walk found nothing
        if len(r.updates) > 1:
            msg = getattr(r.updates[1], "message", None)
            if msg:
                return msg.id
        return None

    try:
        topic_id = await _do_create()
        if topic_id:
            return topic_id, None
        return None, "Could not extract topic ID from Telegram response"
    except FloodWait as e:
        print(f"[TopicHandler] FloodWait {e.value}s creating '{topic_name}' — waiting...")
        await asyncio.sleep(e.value + 1)
        try:
            topic_id = await _do_create()
            if topic_id:
                return topic_id, None
            return None, "FloodWait retry: could not extract topic ID"
        except Exception as retry_err:
            return None, f"FloodWait retry failed: {retry_err}"
    except ChatAdminRequired:
        return None, "Bot needs Admin + Manage Topics permission"
    except Forbidden as e:
        return None, f"Forbidden: {e}"
    except BadRequest as e:
        return None, f"BadRequest: {e}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


async def get_or_create_topic(client: Client, chat_id: int, topic_name: str,
                               topic_key: str, content_type: str = "video"):
    """Return (topic_id, error) — topic_id is None if creation failed."""
    chat_config = get_chat_config(chat_id)

    if topic_key in chat_config["txt_topics"]:
        return chat_config["txt_topics"][topic_key], None

    try:
        async for topic in client.get_forum_topics(chat_id):
            clean = topic.title.lower().lstrip("🎥📄📁📢📤💬 ").strip()
            if clean == topic_name.lower().lstrip("🎥📄📁📢📤💬 ").strip():
                chat_config["txt_topics"][topic_key] = topic.id
                update_chat_config(chat_id, chat_config)
                return topic.id, None
    except Exception as e:
        print(f"[TopicHandler] get_forum_topics failed: {e}")

    topic_id, err = await create_forum_topic(client, chat_id, topic_name)
    if topic_id:
        chat_config["txt_topics"][topic_key] = topic_id
        update_chat_config(chat_id, chat_config)
    return topic_id, err


async def setup_topics_from_txt(client: Client, chat_id: int, txt_file_path: str) -> tuple:
    """Parse txt file and create topics.
    Returns (created_topics dict, parsed_count int, errors list).
    """
    if not TXT_PARSER_AVAILABLE:
        return {}, 0, ["TXT parser module not available"]

    topics = parse_txt_file(txt_file_path)
    parsed_count = len(topics)
    if not topics:
        return {}, 0, []

    created_topics = {}
    errors = []
    for topic_key, topic in topics.items():
        topic_id, err = await get_or_create_topic(
            client, chat_id, topic.topic_name, topic_key, topic.content_type
        )
        if topic_id:
            created_topics[topic_key] = {
                "topic_id": topic_id,
                "topic_name": topic.topic_name,
                "content_type": topic.content_type,
                "content_count": len(topic.contents),
            }
        else:
            errors.append(f"'{topic.topic_name}': {err or 'unknown error'}")
    return created_topics, parsed_count, errors


async def setup_default_topics(client: Client, chat_id: int) -> dict:
    """Create default topics (notices, uploads, videos, pdfs, general)."""
    chat_config = get_chat_config(chat_id)
    created_topics = {}

    for topic_key, topic_info in DEFAULT_TOPICS.items():
        if topic_key in chat_config["topics"]:
            created_topics[topic_key] = chat_config["topics"][topic_key]
            continue

        topic_id, err = await create_forum_topic(client, chat_id, topic_info["name"])
        if topic_id:
            created_topics[topic_key] = topic_id
            chat_config["topics"][topic_key] = topic_id
        elif err:
            print(f"[TopicHandler] Failed to create default topic '{topic_info['name']}': {err}")

    if "general" in created_topics and not chat_config.get("default_topic"):
        chat_config["default_topic"] = created_topics["general"]

    update_chat_config(chat_id, chat_config)
    return created_topics


async def send_to_topic(client: Client, chat_id: int, topic_name: str, **kwargs):
    """Send a message/document/video to a named topic (falls back gracefully)."""
    chat_config = get_chat_config(chat_id)
    topic_id = (
        chat_config.get("txt_topics", {}).get(topic_name)
        or chat_config["topics"].get(topic_name)
    )
    if topic_id:
        kwargs["message_thread_id"] = topic_id

    async def _send():
        if "video" in kwargs:
            return await client.send_video(chat_id, **kwargs)
        elif "document" in kwargs:
            return await client.send_document(chat_id, **kwargs)
        elif "photo" in kwargs:
            return await client.send_photo(chat_id, **kwargs)
        else:
            return await client.send_message(chat_id, **kwargs)

    try:
        return await _send()
    except Exception as e:
        print(f"[TopicHandler] Error sending to topic: {e}")
        kwargs.pop("message_thread_id", None)
        try:
            return await _send()
        except Exception:
            return None


def get_topic_id_for_category(chat_id: int, category: str):
    chat_config = get_chat_config(chat_id)
    mapping = chat_config.get("category_mapping", CATEGORY_TOPICS)
    topic_name = mapping.get(category.lower())
    if topic_name:
        return (
            chat_config.get("txt_topics", {}).get(topic_name)
            or chat_config["topics"].get(topic_name)
        )
    return chat_config.get("default_topic")


def get_topic_id_for_txt_topic(chat_id: int, txt_topic_key: str):
    chat_config = get_chat_config(chat_id)
    return chat_config.get("txt_topics", {}).get(txt_topic_key)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def create_topic_command(client: Client, message: Message):
    """Command: /createtopic <name>"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text(
            "**Usage:** `/createtopic <topic_name>`\n\n"
            "**Example:** `/createtopic 📢 Announcements`"
        )
        return

    topic_name = args[1]
    topic_id, err = await create_forum_topic(client, message.chat.id, topic_name)

    if topic_id:
        chat_config = get_chat_config(message.chat.id)
        topic_key = topic_name.lower().replace(" ", "_")
        topic_key = ''.join(c for c in topic_key if c.isalnum() or c == '_')
        chat_config["topics"][topic_key] = topic_id
        update_chat_config(message.chat.id, chat_config)
        await message.reply_text(
            f"**✅ Topic Created!**\n\n"
            f"**Name:** {topic_name}\n"
            f"**ID:** `{topic_id}`\n"
            f"**Key:** `{topic_key}`"
        )
    else:
        await message.reply_text(
            f"**❌ Failed to create topic.**\n\n"
            f"**Reason:** `{err}`\n\n"
            "Make sure:\n"
            "• This group has Topics enabled\n"
            "• Bot is admin with Manage Topics permission"
        )


async def list_topics_command(client: Client, message: Message):
    """Command: /topics — list all configured topics"""
    chat_config = get_chat_config(message.chat.id)
    has_topics = bool(chat_config["topics"]) or bool(chat_config.get("txt_topics", {}))

    if not has_topics:
        await message.reply_text(
            "**📋 No topics configured.**\n\n"
            "• `/createtopic <name>` — create a topic\n"
            "• `/setuptopics` — create default topics\n"
            "• Reply to a txt file with `/parsetxt <channel_id>` — create from file"
        )
        return

    text = "**📋 Configured Topics:**\n\n"

    if chat_config["topics"]:
        text += "**Default Topics:**\n"
        for topic_key, topic_id in chat_config["topics"].items():
            text += f"• `{topic_key}` → `{topic_id}`\n"

    if chat_config.get("txt_topics"):
        text += "\n**TXT-Generated Topics:**\n"
        for topic_key, topic_id in chat_config["txt_topics"].items():
            text += f"• `{topic_key}` → `{topic_id}`\n"

    if chat_config.get("default_topic"):
        text += f"\n**Default Topic:** `{chat_config['default_topic']}`"

    await message.reply_text(text)


async def set_topic_command(client: Client, message: Message):
    """Command: /settopic <category> <topic_id>"""
    if message.from_user and message.from_user.id != OWNER:
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply_text(
            "**Usage:** `/settopic <category> <topic_id>`\n\n"
            "**Categories:** video, pdf, notice, upload\n\n"
            "**Example:** `/settopic video 12345`"
        )
        return

    category = args[1].lower()
    try:
        topic_id = int(args[2])
    except ValueError:
        await message.reply_text("**❌ Topic ID must be a number.**")
        return

    if category not in CATEGORY_TOPICS:
        await message.reply_text(
            f"**❌ Invalid category.**\n\nValid: {', '.join(CATEGORY_TOPICS.keys())}"
        )
        return

    chat_config = get_chat_config(message.chat.id)
    chat_config["topics"][category] = topic_id
    update_chat_config(message.chat.id, chat_config)

    await message.reply_text(
        f"**✅ Topic Mapping Updated!**\n\n"
        f"**Category:** {category}\n"
        f"**Topic ID:** `{topic_id}`"
    )


async def setup_topics_command(client: Client, message: Message):
    """Command: /setuptopics — auto-create default topics"""
    if message.from_user and message.from_user.id != OWNER:
        return

    status = await message.reply_text("**🔄 Setting up default topics...**")
    created = await setup_default_topics(client, message.chat.id)

    if created:
        text = "**✅ Topics Created!**\n\n"
        for topic_key, topic_id in created.items():
            info = DEFAULT_TOPICS.get(topic_key, {"name": topic_key})
            text += f"• {info['name']} → `{topic_id}`\n"
        await status.edit(text)
    else:
        await status.edit(
            "**❌ Failed to create topics.**\n\n"
            "Make sure:\n"
            "• This group has Topics enabled\n"
            "• Bot has 'Manage Topics' permission"
        )


async def parse_txt_command(client: Client, message: Message):
    """Command: /parsetxt <channel_id> — then send txt file when prompted"""
    if message.from_user and message.from_user.id != OWNER:
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text(
            "**Usage:** `/parsetxt -1001234567890`\n\n"
            "Replace with your actual channel/group ID.\n"
            "Bot will then ask you to send the txt file."
        )
        return

    try:
        channel_id = int(args[1].strip())
    except ValueError:
        await message.reply_text("**❌ Invalid channel ID. Must be a number like `-1001234567890`**")
        return

    prompt = await message.reply_text(
        f"**📂 Send your `.txt` file now.**\n\n"
        f"Channel/Group ID: `{channel_id}`\n"
        f"_Waiting 60 seconds..._"
    )

    try:
        file_msg = await client.listen(message.chat.id, timeout=60)
    except Exception:
        await prompt.edit("**❌ Timed out. Please run `/parsetxt` again.**")
        return

    if not file_msg or not file_msg.document:
        await prompt.edit("**❌ No document received. Please run `/parsetxt` again and send a .txt file.**")
        return

    if not file_msg.document.file_name.endswith('.txt'):
        await prompt.edit("**❌ That is not a `.txt` file. Please run `/parsetxt` again.**")
        return

    await prompt.edit("**📥 Downloading txt file...**")
    txt_path = await file_msg.download()
    await prompt.edit("**🔍 Parsing txt file...**")

    created, parsed_count, errors = await setup_topics_from_txt(client, channel_id, txt_path)

    try:
        os.remove(txt_path)
    except Exception:
        pass

    if parsed_count == 0:
        await prompt.edit(
            "**❌ No topic headings found in the txt file.**\n\n"
            "The file must have lines like:\n"
            "`Notices Videos videos`\n"
            "`Mentorship Session videos`\n"
            "`Batch PDFs notes`\n\n"
            "These lines (without `://`) mark the start of a new topic section."
        )
        return

    if created:
        text = (
            f"**✅ Topics Created in Channel!**\n\n"
            f"**Channel ID:** `{channel_id}`\n"
            f"**Parsed:** {parsed_count} topics | **Created:** {len(created)}\n\n"
        )
        for key, info in created.items():
            text += (
                f"• {info['topic_name']}\n"
                f"  ID: `{info['topic_id']}` | Type: {info['content_type']} | Files: {info['content_count']}\n"
            )
        if errors:
            text += f"\n**⚠️ {len(errors)} topic(s) failed:**\n"
            for e in errors[:5]:
                text += f"• {e}\n"
        await prompt.edit(text)
    else:
        err_sample = errors[0] if errors else "unknown"
        await prompt.edit(
            f"**❌ Found {parsed_count} topics in file but all failed to create.**\n\n"
            f"**First error:** `{err_sample}`\n\n"
            "Make sure:\n"
            "• The group/channel has Topics (Forum mode) enabled\n"
            "• Bot is admin with **Manage Topics** permission\n"
            "• The channel ID is correct (negative number like `-1001234567890`)"
        )


async def set_default_topic_command(client: Client, message: Message):
    """Command: /defaulttopic <topic_id>"""
    if message.from_user and message.from_user.id != OWNER:
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("**Usage:** `/defaulttopic <topic_id>`\n\nExample: `/defaulttopic 12345`")
        return

    try:
        topic_id = int(args[1])
        chat_config = get_chat_config(message.chat.id)
        chat_config["default_topic"] = topic_id
        update_chat_config(message.chat.id, chat_config)
        await message.reply_text(f"**✅ Default topic set to:** `{topic_id}`")
    except ValueError:
        await message.reply_text("**❌ Invalid topic ID. Must be a number.**")


async def get_topic_id_command(client: Client, message: Message):
    """Command: /topicid — get current topic ID"""
    if message.message_thread_id:
        await message.reply_text(
            f"**📌 Current Topic Info:**\n\n"
            f"**Topic ID:** `{message.message_thread_id}`\n"
            f"**Chat ID:** `{message.chat.id}`"
        )
    else:
        await message.reply_text(
            "**ℹ️ This message is not inside a topic.**\n\n"
            "Send `/topicid` from inside a forum topic to get its ID."
        )


async def parse_topics_command(client: Client, message: Message):
    """Command: /parsetopics — send a txt file to preview topics found in it.
    Shows topic names and any [id] prefixes already set.
    """
    prompt = await message.reply_text(
        "<b>📂 Send your .txt file now.</b>\n\n"
        "<i>I will show all topic headings found and whether they have IDs set.</i>\n\n"
        "<i>Waiting 60 seconds...</i>",
        parse_mode=enums.ParseMode.HTML
    )

    try:
        file_msg = await client.listen(message.chat.id, timeout=60)
    except Exception:
        await prompt.edit("**❌ Timed out. Please run `/parsetopics` again.**")
        return

    if not file_msg or not file_msg.document:
        await prompt.edit("**❌ No file received. Please run `/parsetopics` again.**")
        return

    if not file_msg.document.file_name.endswith('.txt'):
        await prompt.edit("**❌ That is not a `.txt` file. Please run `/parsetopics` again.**")
        return

    await prompt.edit("**🔍 Parsing topics from file...**")
    txt_path = await file_msg.download()

    try:
        import re as _re
        topics_found = []
        with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '://' in line:
                    continue
                tid_match = _re.match(r'^\[(\d+)\]\s*(.*)', line)
                if tid_match:
                    topics_found.append((tid_match.group(2).strip(), int(tid_match.group(1))))
                else:
                    topics_found.append((line, None))
    except Exception as e:
        await prompt.edit(f"**❌ Failed to read file:** `{e}`")
        return
    finally:
        try:
            os.remove(txt_path)
        except Exception:
            pass

    if not topics_found:
        await prompt.edit(
            "<b>❌ No topic headings found.</b>\n\n"
            "Lines without <code>://</code> (and not starting with <code>#</code>) are treated as topic names.\n\n"
            "<b>Example format:</b>\n"
            "<code>[12345] Batch Demo Videos videos</code>\n"
            "<code>Content Name://url...</code>",
            parse_mode=enums.ParseMode.HTML
        )
        return

    def esc(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    no_id = sum(1 for _, t in topics_found if t is None)

    topic_lines = []
    for idx, (name, tid) in enumerate(topics_found, 1):
        if tid:
            topic_lines.append(f"<b>{idx}.</b> {esc(name)}\n    ↳ Topic ID: <code>{tid}</code> ✅")
        else:
            topic_lines.append(f"<b>{idx}.</b> {esc(name)}\n    ↳ No ID set ⚠️")

    if no_id:
        footer = (
            f"\n<b>⚠️ {no_id} topic(s) have no ID yet.</b>\n"
            "Go into each topic in your group → send <code>/topicid</code> → copy the ID.\n"
            "Then edit your txt file:\n"
            "<code>[12345] Topic Name</code>"
        )
    else:
        footer = "\n<b>✅ All topics have IDs — ready to upload!</b>"

    # Split into chunks of max 4000 chars to avoid MESSAGE_TOO_LONG
    MAX_LEN = 4000
    chunks = []
    current = f"<b>📋 Topics found ({len(topics_found)}):</b>\n\n"
    for line in topic_lines:
        entry = line + "\n\n"
        if len(current) + len(entry) > MAX_LEN:
            chunks.append(current.rstrip())
            current = entry
        else:
            current += entry
    current += footer
    chunks.append(current.rstrip())

    await prompt.edit(chunks[0], parse_mode=enums.ParseMode.HTML)
    for chunk in chunks[1:]:
        await message.reply_text(chunk, parse_mode=enums.ParseMode.HTML)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register_topic_handlers(bot: Client):
    bot.on_message(filters.command("createtopic"))(create_topic_command)
    bot.on_message(filters.command("topics"))(list_topics_command)
    bot.on_message(filters.command("settopic"))(set_topic_command)
    bot.on_message(filters.command("setuptopics"))(setup_topics_command)
    bot.on_message(filters.command("parsetxt"))(parse_txt_command)
    bot.on_message(filters.command("defaulttopic"))(set_default_topic_command)
    bot.on_message(filters.command("topicid"))(get_topic_id_command)
    bot.on_message(filters.command("parsetopics"))(parse_topics_command)

    @bot.on_message(filters.group & filters.service)
    async def _on_group_join(client, message: Message):
        if not message.new_chat_members:
            return
        me = await client.get_me()
        for member in message.new_chat_members:
            if member.id == me.id:
                try:
                    await setup_default_topics(client, message.chat.id)
                    await message.reply_text(
                        "**✅ Bot Added!**\n\n"
                        "Default topics created:\n"
                        "• 📢 Notices\n• 📤 Uploads\n• 🎥 Videos\n• 📄 PDFs\n• 💬 General\n\n"
                        "Use `/topics` to see IDs.\n"
                        "Reply to a txt file with `/parsetxt <channel_id>` to create topics from file."
                    )
                except Exception as e:
                    print(f"[TopicHandler] Auto-setup failed: {e}")
                break

    print("[TopicHandler] Handlers registered: /createtopic /topics /settopic /setuptopics /parsetxt /defaulttopic /topicid /parsetopics")
