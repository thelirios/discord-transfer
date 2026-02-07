import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any

import orjson
import aiohttp
import discord
from discord import Intents
from discord.errors import Forbidden, NotFound


def _json_dumps(obj: Any) -> bytes:
    try:
        return orjson.dumps(obj)
    except Exception:
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")


async def _export_channel(client: discord.Client, channel_id: int, out_dir: Path):
    try:
        channel = await client.fetch_channel(channel_id)
    except Forbidden:
        raise RuntimeError(
            "Bot lacks access to source channel. Verify it's in the guild and has 'View Channel' + 'Read Message History' permissions, and that channel overrides allow the bot."
        )
    except NotFound:
        raise RuntimeError("Source channel not found. Check SOURCE_CHANNEL_ID and bot guild membership.")

    if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
        raise RuntimeError("Only TextChannel/ForumChannel are supported for now.")

    out_dir.mkdir(parents=True, exist_ok=True)
    attach_dir = out_dir / "attachments"
    attach_dir.mkdir(parents=True, exist_ok=True)
    messages_path = out_dir / "messages.jsonl"

    session: aiohttp.ClientSession = client.http._HTTPClient__session  # type: ignore

    async with aiohttp.ClientSession() as download_session:
        with messages_path.open("wb") as f:
            # ForumChannels do not have top-level message history; skip to threads.
            if isinstance(channel, discord.TextChannel):
                async for msg in channel.history(limit=None, oldest_first=True):
                    record: Dict[str, Any] = {
                        "id": msg.id,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat(),
                        "author": {
                            "id": msg.author.id,
                            "name": getattr(msg.author, "display_name", msg.author.name),
                            "avatar": getattr(msg.author.display_avatar, "url", None),
                        },
                        "mentions": [m.id for m in msg.mentions],
                        "role_mentions": [r.id for r in getattr(msg, "role_mentions", [])],
                        "attachments": [],
                        "embeds": [e.to_dict() for e in msg.embeds],
                        "reference": (msg.reference.message_id if msg.reference else None),
                        "is_reply": msg.reference is not None,
                    }

                    # Download attachments
                    for idx, att in enumerate(msg.attachments):
                        safe_name = f"{msg.id}_{idx}_{att.filename}"
                        dest = attach_dir / safe_name
                        try:
                            data = await att.read()
                            dest.write_bytes(data)
                            record["attachments"].append({
                                "filename": att.filename,
                                "saved_as": safe_name,
                                "content_type": att.content_type,
                                "size": att.size,
                            })
                        except Exception as e:
                            record["attachments"].append({
                                "filename": att.filename,
                                "error": str(e),
                            })

                    f.write(_json_dumps(record) + b"\n")
                record: Dict[str, Any] = {
                    "id": msg.id,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                    "author": {
                        "id": msg.author.id,
                        "name": getattr(msg.author, "display_name", msg.author.name),
                        "avatar": getattr(msg.author.display_avatar, "url", None),
                    },
                    "mentions": [m.id for m in msg.mentions],
                    "role_mentions": [r.id for r in getattr(msg, "role_mentions", [])],
                    "attachments": [],
                    "embeds": [e.to_dict() for e in msg.embeds],
                    "reference": (msg.reference.message_id if msg.reference else None),
                    "is_reply": msg.reference is not None,
                }

                # Download attachments
                for idx, att in enumerate(msg.attachments):
                    # Name pattern: messageId_attachIndex_original
                    safe_name = f"{msg.id}_{idx}_{att.filename}"
                    dest = attach_dir / safe_name
                    try:
                        data = await att.read()
                        dest.write_bytes(data)
                        record["attachments"].append({
                            "filename": att.filename,
                            "saved_as": safe_name,
                            "content_type": att.content_type,
                            "size": att.size,
                        })
                    except Exception as e:
                        record["attachments"].append({
                            "filename": att.filename,
                            "error": str(e),
                        })

                f.write(_json_dumps(record) + b"\n")

        # Export threads (active + archived)
        threads_dir = out_dir / "threads"
        threads_dir.mkdir(exist_ok=True)

        # Active threads
        for thread in getattr(channel, "threads", []):
            await _export_thread(thread, threads_dir)

        # Archived threads
        try:
            async for thread in channel.archived_threads(limit=None):
                await _export_thread(thread, threads_dir)
        except Forbidden:
            # Missing access to archived threads
            print("Warning: cannot access archived threads. Grant 'Read Message History' on channel.")
        except Exception:
            # Some channels may not support archived_threads iterator
            pass


async def _export_thread(thread: discord.Thread, threads_dir: Path):
    tdir = threads_dir / str(thread.id)
    tdir.mkdir(parents=True, exist_ok=True)
    meta_path = tdir / "meta.json"
    msgs_path = tdir / "messages.jsonl"
    attach_dir = tdir / "attachments"
    attach_dir.mkdir(exist_ok=True)

    meta = {
        "id": thread.id,
        "name": thread.name,
        "created_at": getattr(thread, "created_at", None).isoformat() if getattr(thread, "created_at", None) else None,
        "archived": thread.archived,
        "locked": thread.locked,
        "owner_id": getattr(thread, "owner_id", None),
    }
    meta_path.write_bytes(_json_dumps(meta))

    async for msg in thread.history(limit=None, oldest_first=True):
        record = {
            "id": msg.id,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "author": {
                "id": msg.author.id,
                "name": getattr(msg.author, "display_name", msg.author.name),
                "avatar": getattr(msg.author.display_avatar, "url", None),
            },
            "attachments": [],
            "embeds": [e.to_dict() for e in msg.embeds],
            "reference": (msg.reference.message_id if msg.reference else None),
            "is_reply": msg.reference is not None,
        }

        for idx, att in enumerate(msg.attachments):
            safe_name = f"{msg.id}_{idx}_{att.filename}"
            dest = attach_dir / safe_name
            try:
                data = await att.read()
                dest.write_bytes(data)
                record["attachments"].append({
                    "filename": att.filename,
                    "saved_as": safe_name,
                    "content_type": att.content_type,
                    "size": att.size,
                })
            except Exception as e:
                record["attachments"].append({
                    "filename": att.filename,
                    "error": str(e),
                })

        with msgs_path.open("ab") as f:
            f.write(_json_dumps(record) + b"\n")


async def run_archive(token: str, source_channel_id: int, out_dir: str):
    intents = Intents.none()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True  # requiere activarlo en el portal del bot
    client = discord.Client(intents=intents)

    out = Path(out_dir)

    ready = asyncio.Event()

    @client.event
    async def on_ready():
        ready.set()

    async def runner():
        await ready.wait()
        try:
            await _export_channel(client, source_channel_id, out)
        finally:
            await client.close()

    await asyncio.gather(client.start(token), runner())