import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import aiohttp
import discord
from discord import Intents


async def _ensure_webhook(channel: discord.TextChannel) -> discord.Webhook:
    hooks = await channel.webhooks()
    for h in hooks:
        if h.token:
            return h
    # Webhook names cannot contain the word "discord"
    return await channel.create_webhook(name="channel-transfer")


async def _send_via_webhook(
    webhook: discord.Webhook,
    content: str,
    username: str | None,
    avatar_url: str | None,
    files: List[discord.File] | None,
    thread_id: int | None = None,
):
    try:
        thread_obj = None
        if thread_id and hasattr(webhook.channel, "get_thread"):
            thread_obj = webhook.channel.get_thread(thread_id)  # type: ignore

        if thread_obj is not None:
            await webhook.send(
                content=content,
                username=username or webhook.name,
                avatar_url=avatar_url,
                files=files or [],
                wait=True,
                thread=thread_obj,
            )
        else:
            await webhook.send(
                content=content,
                username=username or webhook.name,
                avatar_url=avatar_url,
                files=files or [],
                wait=True,
            )
    except Exception:
        # Fallback: send as bot
        if thread_id:
            thread = webhook.channel.get_thread(thread_id) if hasattr(webhook.channel, "get_thread") else None  # type: ignore
            if thread:
                await thread.send(content=content, files=files or [])
                return
        await webhook.channel.send(content=content, files=files or [])  # type: ignore


async def _restore_messages(channel: discord.TextChannel | discord.ForumChannel, in_dir: Path, webhook: discord.Webhook | None, dry_run: bool, counters: Dict[str, int], target_thread_id: int | None = None):
    messages_path = in_dir / "messages.jsonl"
    if not messages_path.exists():
        return
    async with aiohttp.ClientSession() as session:
        with messages_path.open("rb") as f:
            for raw in f:
                rec: Dict[str, Any] = json.loads(raw)
                files: List[discord.File] = []
                for att in rec.get("attachments", []):
                    saved = att.get("saved_as")
                    if saved:
                        p = in_dir / "attachments" / saved
                        if p.exists():
                            files.append(discord.File(fp=str(p), filename=att.get("filename") or saved))
                            counters["attachments"] = counters.get("attachments", 0) + 1

                # Emulate replies with a textual prefix when applicable
                prefix = ""
                if rec.get("is_reply") and rec.get("reference"):
                    prefix = f"(Reply to message {rec['reference']})\n"
                if dry_run:
                    counters["messages"] = counters.get("messages", 0) + 1
                    continue
                content = prefix + (rec.get("content") or "")
                if not content and not files:
                    # Skip empty messages without attachments to avoid API errors
                    continue
                if webhook is None:
                    webhook = await _ensure_webhook(channel)
                await _send_via_webhook(
                    webhook,
                    content=content,
                    username=(rec.get("author") or {}).get("name"),
                    avatar_url=(rec.get("author") or {}).get("avatar"),
                    files=files,
                    thread_id=target_thread_id,
                )
                counters["messages"] = counters.get("messages", 0) + 1


async def _restore_threads(channel: discord.TextChannel | discord.ForumChannel, in_dir: Path, webhook: discord.Webhook | None, dry_run: bool, counters: Dict[str, int]):
    threads_dir = in_dir / "threads"
    if not threads_dir.exists():
        return
    for tdir in threads_dir.iterdir():
        if not tdir.is_dir():
            continue
        meta_path = tdir / "meta.json"
        msgs_path = tdir / "messages.jsonl"
        if not msgs_path.exists():
            continue
        name = str(tdir.name)
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(meta, dict) and meta.get("name"):
                    name = str(meta["name"])[:100]
            except Exception:
                pass
        if dry_run:
            counters["threads"] = counters.get("threads", 0) + 1
            with msgs_path.open("rb") as f:
                for raw in f:
                    rec: Dict[str, Any] = json.loads(raw)
                    counters["thread_messages"] = counters.get("thread_messages", 0) + 1
                    for att in rec.get("attachments", []):
                        if att.get("saved_as"):
                            counters["attachments"] = counters.get("attachments", 0) + 1
            continue

        # Forum channels require a starter message when creating a post
        created = await channel.create_thread(name=name, content="Thread import start") if isinstance(channel, discord.ForumChannel) else await channel.create_thread(name=name)
        thread = created.thread if hasattr(created, "thread") else created
        with msgs_path.open("rb") as f:
            for raw in f:
                rec: Dict[str, Any] = json.loads(raw)
                files: List[discord.File] = []
                for att in rec.get("attachments", []):
                    saved = att.get("saved_as")
                    if saved:
                        p = tdir / "attachments" / saved
                        if p.exists():
                            files.append(discord.File(fp=str(p), filename=att.get("filename") or saved))
                            counters["attachments"] = counters.get("attachments", 0) + 1

                # Emulate replies with a textual prefix when applicable
                prefix = ""
                if rec.get("is_reply") and rec.get("reference"):
                    prefix = f"(Reply to message {rec['reference']})\n"
                content = prefix + (rec.get("content") or "")
                if not content and not files:
                    # Skip empty messages without attachments to avoid API errors
                    continue

                await _send_via_webhook(
                    webhook,
                    content=content,
                    username=(rec.get("author") or {}).get("name"),
                    avatar_url=(rec.get("author") or {}).get("avatar"),
                    files=files,
                    thread_id=thread.id,
                )
                counters["thread_messages"] = counters.get("thread_messages", 0) + 1


async def run_restore(token: str, dest_channel_id: int, in_dir: str, dry_run: bool = False):
    intents = Intents.none()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    ready = asyncio.Event()

    @client.event
    async def on_ready():
        ready.set()

    async def runner():
        await ready.wait()
        try:
            channel = await client.fetch_channel(dest_channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                raise RuntimeError("Destination channel must be a TextChannel or ForumChannel.")
            in_path = Path(in_dir)
            counters: Dict[str, int] = {}
            webhook = None
            if not dry_run:
                webhook = await _ensure_webhook(channel)
                try:
                    print(f"Using webhook: id={webhook.id} name={webhook.name}")
                except Exception:
                    pass
            target_thread_id = None
            # For forum channels, post main messages inside a dedicated thread
            if isinstance(channel, discord.ForumChannel):
                if dry_run:
                    counters["threads"] = counters.get("threads", 0) + 1
                else:
                    created = await channel.create_thread(name="channel-messages", content="Starting import")
                    thread_obj = created.thread if hasattr(created, "thread") else created
                    target_thread_id = thread_obj.id
            await _restore_messages(channel, in_path, webhook, dry_run, counters, target_thread_id)
            await _restore_threads(channel, in_path, webhook, dry_run, counters)
            print(
                "Restore summary:",
                f"messages={counters.get('messages', 0)}",
                f"thread_messages={counters.get('thread_messages', 0)}",
                f"threads={counters.get('threads', 0)}",
                f"attachments={counters.get('attachments', 0)}",
                f"dry_run={dry_run}",
            )
        finally:
            await client.close()
    await asyncio.gather(client.start(token), runner())