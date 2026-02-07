import asyncio
import os
from typing import Optional
from pathlib import Path

import typer
from dotenv import load_dotenv, find_dotenv, dotenv_values

from .archive import run_archive
from .importer import run_restore

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _load_env():
    """Load .env from current directory and project root.

    Supports running commands from workspace root or subfolders (e.g., src).
    """
    # 1) Find .env in CWD or parent chain
    attempted_paths = []
    try:
        found = find_dotenv(usecwd=True)
        if found:
            attempted_paths.append(found)
            load_dotenv(dotenv_path=found, override=True)
    except Exception:
        pass

    # 2) Also try project root based on this file location
    try:
        root = Path(__file__).resolve().parents[2]  # .../src/discord_transfer/ -> repo root
        root_env = root / ".env"
        if root_env.exists():
            attempted_paths.append(str(root_env))
            load_dotenv(dotenv_path=str(root_env), override=True)
    except Exception:
        pass

    # 3) Fallback: if still missing, set envs manually from detected files
    if not os.getenv("DISCORD_BOT_TOKEN"):
        try:
            values = {}
            if 'found' in locals() and found:
                values.update(dotenv_values(found) or {})
            if 'root_env' in locals() and root_env.exists():
                values.update(dotenv_values(str(root_env)) or {})
            for k, v in values.items():
                if k and v and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass

    # Debug: if still missing, echo attempted paths to help diagnose
    if not os.getenv("DISCORD_BOT_TOKEN"):
        try:
            if attempted_paths:
                typer.echo(f".env not loaded; attempted: {attempted_paths}")
            else:
                typer.echo(".env not found in CWD or project root.")
        except Exception:
            pass


@app.command()
def archive(
    source_channel: Optional[int] = typer.Option(None, help="Source channel ID"),
    out_dir: str = typer.Option("data/source", help="Output directory"),
    token: Optional[str] = typer.Option(None, help="Bot token (or use .env)"),
):
    """Export messages, attachments, and threads from the source channel to disk."""
    _load_env()
    token = token or os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise typer.Exit("Missing DISCORD_BOT_TOKEN. Set .env or pass --token.")
    if source_channel is None:
        env_id = os.getenv("SOURCE_CHANNEL_ID")
        if not env_id:
            raise typer.Exit("Missing SOURCE_CHANNEL_ID. Pass via CLI or .env.")
        source_channel = int(env_id)

    asyncio.run(run_archive(token=token, source_channel_id=source_channel, out_dir=out_dir))


@app.command()
def restore(
    dest_channel: Optional[int] = typer.Option(None, help="Destination channel ID"),
    in_dir: str = typer.Option("data/source", help="Directory with exported content"),
    token: Optional[str] = typer.Option(None, help="Bot token (or use .env)"),
    dry_run: bool = typer.Option(False, help="Do not post; print a summary of actions"),
):
    """Re-post messages/attachments/threads into the destination channel using webhooks."""
    _load_env()
    token = token or os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise typer.Exit("Missing DISCORD_BOT_TOKEN. Set .env or pass --token.")
    if dest_channel is None:
        env_id = os.getenv("DEST_CHANNEL_ID")
        if not env_id:
            raise typer.Exit("Missing DEST_CHANNEL_ID. Pass via CLI or .env.")
        dest_channel = int(env_id)

    asyncio.run(run_restore(token=token, dest_channel_id=dest_channel, in_dir=in_dir, dry_run=dry_run))


def main():
    app()


if __name__ == "__main__":
    main()