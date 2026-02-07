# discord-transfer

Python tool to archive and restore Discord channel messages (including threads and attachments) from one server to another, aiming for a 1:1 copy in order.

Important notes:

- You cannot move original messages or preserve original authors/timestamps. Messages are re-posted (ideally via webhooks) with the author's name and avatar, but they are new messages.
- Message replies (references) cannot be recreated exactly via webhooks; this tool emulates them with textual prefixes.
- Respect Discord TOS and privacy: you need permission, and the bot must have the proper roles/permissions (Read Message History, Manage Webhooks, Attach Files, Manage Threads, etc.). Enable your bot's "Message Content Intent".

## Requirements

- Python 3.10+
- Discord bot token
- Permissions on both servers

## Quick start

1. Create and configure a bot in the Developer Portal and enable "Message Content Intent".
2. Invite the bot to both servers with sufficient permissions.
3. Copy `.env.example` to `.env` and fill in the variables.
4. Install dependencies and the package (editable) and run the commands.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# install package with src/ layout
pip install -e .

python -m discord_transfer.cli --help
python -m discord_transfer.cli archive --source-channel 1234567890 --out-dir data/source
python -m discord_transfer.cli restore --dest-channel 0987654321 --in-dir data/source
```

### Dry-run (no posting)

To preview what would be posted without sending anything:

```bash
python -m discord_transfer.cli restore --in-dir data/source --dry-run
```

Alternatively, use the console script:

```bash
discord-transfer --help
discord-transfer archive --source-channel 1234567890 --out-dir data/source
discord-transfer restore --dest-channel 0987654321 --in-dir data/source
```

## Technical limitations

- Timestamps cannot be backdated; order is preserved when re-posting.
- Original authors cannot be impersonated; webhooks approximate appearance with name and avatar.
- Complex third-party embeds may not be faithfully recreated.
- Ephemeral messages or deleted content cannot be recovered.

## Structure

- `src/discord_transfer/archive.py`: Exports messages/attachments/threads to JSONL + files.
- `src/discord_transfer/importer.py`: Re-posts to destination channel using webhooks.
- `src/discord_transfer/cli.py`: CLI with `archive` and `restore` commands.
- `requirements.txt`, `.env.example`, `README.md`.

## Safety and compliance

- Obtain permissions and notify members if transferring personal content.
- Comply with Discord TOS and server policies.

## Using your user account (self-bot)

Automating actions with your personal user account (using your personal token for scripts) is prohibited by Discord's TOS. This is known as a “self-bot” and may result in account suspension. discord.py does not support user accounts. Use a bot + webhooks with proper permissions for safe and compliant transfers.

