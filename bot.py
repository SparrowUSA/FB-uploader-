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

# ──── your helper functions ────────────────────────────────────────────────
from uploader import (
    download_videos,
    rename_videos,
    upload_to_facebook
)

# ──── Configuration from env vars (Railway) ────────────────────────────────
TELEGRAM_API_ID       = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH     = os.getenv("TELEGRAM_API_HASH")
TELETHON_BOT_TOKEN    = os.getenv("TELETHON_BOT_TOKEN")      # Bot token for Telethon downloads
COMMAND_BOT_TOKEN     = os.getenv("BOT_TOKEN")               # Bot token for python-telegram-bot commands
FB_PAGE_ID            = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN       = os.getenv("FB_ACCESS_TOKEN")
ALLOWED_USER_ID       = int(os.getenv("ALLOWED_USER_ID"))    # Your numeric Telegram ID

SESSION_NAME          = None                                 # No session file needed in bot mode
DOWNLOAD_FOLDER       = "downloads"
VIDEO_BASE_NAME       = "My vlog"
DELAY_BETWEEN_UPLOAD  = 65                                   # seconds – safe for FB

# ────────────────────────────────────────────────────────────────────────────

async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("🚫 Not authorized.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "Usage examples:\n"
            "/upload @mychannel 50\n"
            "/upload -1001234567890 30"
        )
        return

    channel_input = args[0]
    try:
        video_count = int(args[1])
        if video_count < 1 or video_count > 300:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Second argument must be a number (1–300).")
        return

    status = await update.message.reply_text(
        f"⏳ Starting • Fetching {video_count} videos from {channel_input} …"
    )

    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    # Telethon client in BOT mode – no phone, no session file
    client = TelegramClient(
        SESSION_NAME,
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH
    )

    try:
        await client.start(bot_token=TELETHON_BOT_TOKEN)

        await status.edit_text("📥 Downloading videos (oldest first) …")

        paths = await download_videos(client, channel_input, video_count)

        if not paths:
            await status.edit_text("No videos found in the recent messages of the channel.")
            return

        count_downloaded = len(paths)
        await status.edit_text(f"Downloaded {count_downloaded} videos. Renaming sequentially …")

        renamed_paths = rename_videos(paths, VIDEO_BASE_NAME)

        await status.edit_text(f"Queuing uploads ({count_downloaded} videos) …")

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

            success = upload_to_facebook(path, FB_PAGE_ID, FB_ACCESS_TOKEN)

            if success:
                uploaded_ok += 1
                try:
                    os.remove(path)
                except:
                    pass
            else:
                failed.append(filename)

            await asyncio.sleep(DELAY_BETWEEN_UPLOAD)

        summary = f"✅ Done\nUploaded {uploaded_ok}/{count_downloaded}"
        if failed:
            summary += "\nFailed:\n" + "\n".join(f"• {f}" for f in failed)

        await status.edit_text(summary)

    except Exception as e:
        await status.edit_text(f"Error: {type(e).__name__}\n{str(e)[:400]}")
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

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot started (bot mode)")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
