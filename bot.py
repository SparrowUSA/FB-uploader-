import os
import asyncio
import queue
import time
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from telethon import TelegramClient

# ──── Helper functions ─────────────────────────────────────────────────────
from uploader import (
    download_videos,
    rename_videos,
    upload_to_google_drive,
    get_drive_service
)

# ──── Configuration (all from Railway environment variables) ───────────────
TELEGRAM_API_ID       = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH     = os.getenv("TELEGRAM_API_HASH")
TELETHON_BOT_TOKEN    = os.getenv("TELETHON_BOT_TOKEN")      # Bot token for Telethon
COMMAND_BOT_TOKEN     = os.getenv("BOT_TOKEN")               # Bot token for commands

ALLOWED_USER_ID       = int(os.getenv("ALLOWED_USER_ID"))    # Your Telegram numeric ID

DOWNLOAD_FOLDER       = "downloads"
VIDEO_BASE_NAME       = "My vlog"
DELAY_BETWEEN_UPLOAD  = 60                                   # seconds — adjust if needed

# ────────────────────────────────────────────────────────────────────────────

async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("🚫 Not authorized.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "Usage:\n"
            "/upload @channelname 50\n"
            "/upload -1001234567890 30"
        )
        return

    channel_input = args[0]
    try:
        video_count = int(args[1])
        if video_count < 1 or video_count > 300:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Second argument must be a number between 1–300.")
        return

    status = await update.message.reply_text(
        f"⏳ Starting • {video_count} videos from {channel_input} …"
    )

    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    # Telethon client — bot mode (no session file, no phone login)
    client = TelegramClient(
        None,  # no session file
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH
    )

    try:
        await client.start(bot_token=TELETHON_BOT_TOKEN)

        await status.edit_text("📥 Downloading videos (oldest → newest) …")

        paths = await download_videos(client, channel_input, video_count)

        if not paths:
            await status.edit_text("No videos found in recent channel messages.")
            return

        count_downloaded = len(paths)
        await status.edit_text(f"Downloaded {count_downloaded} videos. Renaming …")

        renamed_paths = rename_videos(paths, VIDEO_BASE_NAME)

        await status.edit_text(f"Starting upload to Google Drive ({count_downloaded} videos) …")

        drive_service = get_drive_service()

        q = queue.Queue()
        for p in renamed_paths:
            q.put(p)

        uploaded_ok = 0
        failed = []

        while not q.empty():
            path = q.get()
            filename = os.path.basename(path)

            await status.edit_text(
                f"Uploading {filename}  ({uploaded_ok + 1}/{count_downloaded})"
            )

            success = upload_to_google_drive(
                path,
                folder_id=os.getenv("DRIVE_FOLDER_ID"),
                drive_service=drive_service
            )

            if success:
                uploaded_ok += 1
                try:
                    os.remove(path)
                except:
                    pass
            else:
                failed.append(filename)

            await asyncio.sleep(DELAY_BETWEEN_UPLOAD)

        summary = f"✅ Finished\nUploaded: {uploaded_ok}/{count_downloaded}"
        if failed:
            summary += "\nFailed:\n" + "\n".join(f"• {f}" for f in failed)

        await status.edit_text(summary)

    except Exception as e:
        await status.edit_text(f"Error: {type(e).__name__}\n{str(e)[:500]}")
    finally:
        await client.disconnect()


def main():
    app = ApplicationBuilder() \
        .token(COMMAND_BOT_TOKEN) \
        .read_timeout(30) \
        .write_timeout(60) \
        .get_updates_read_timeout(30) \
        .build()

    app.add_handler(CommandHandler("upload", cmd_upload))

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot started (Google Drive mode)")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
