import os
import asyncio
import queue
import time
from datetime import datetime

from telethon import TelegramClient, events

# ──── Helper functions ─────────────────────────────────────────────────────
from uploader import (
    rename_videos,           # we'll modify slightly
    upload_to_google_drive,
    get_drive_service
)

# ──── Configuration (Railway env vars) ─────────────────────────────────────
TELEGRAM_API_ID       = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH     = os.getenv("TELEGRAM_API_HASH")
TELETHON_BOT_TOKEN    = os.getenv("TELETHON_BOT_TOKEN")      # Bot token for Telethon

DOWNLOAD_FOLDER       = "downloads"
VIDEO_BASE_NAME       = "My vlog"
DELAY_BETWEEN_UPLOAD  = 60                                   # seconds

# Global counter for sequential naming (resets on restart)
video_counter = 0
upload_queue = queue.Queue()

# Optional: target channel username or ID (set via env or hardcode for simplicity)
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@yourchannelusername")  # or -1001234567890

# ────────────────────────────────────────────────────────────────────────────

def get_drive_service():
    # same as before - load from GOOGLE_SERVICE_ACCOUNT_JSON
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_str:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials_info = json.loads(json_str)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=credentials)

async def process_queue():
    """Background task to upload queued videos one by one"""
    drive_service = get_drive_service()
    while True:
        if not upload_queue.empty():
            path = upload_queue.get()
            filename = os.path.basename(path)
            print(f"Uploading {filename} to Drive...")
            success = upload_to_google_drive(
                path,
                folder_id=os.getenv("DRIVE_FOLDER_ID"),
                drive_service=drive_service
            )
            if success:
                try:
                    os.remove(path)
                except:
                    pass
            else:
                print(f"Failed: {filename}")
            await asyncio.sleep(DELAY_BETWEEN_UPLOAD)
        else:
            await asyncio.sleep(5)  # idle check

@client.on(events.NewMessage(chats=TARGET_CHANNEL))
async def video_handler(event):
    global video_counter
    if event.video:
        print(f"New video detected in {TARGET_CHANNEL}")
        path = await event.download_media(file=DOWNLOAD_FOLDER)
        if path:
            video_counter += 1
            ext = os.path.splitext(path)[1] or ".mp4"
            new_path = os.path.join(DOWNLOAD_FOLDER, f"{VIDEO_BASE_NAME} {video_counter}{ext}")
            os.rename(path, new_path)
            upload_queue.put(new_path)
            print(f"Queued: {os.path.basename(new_path)} (#{video_counter})")

async def main():
    global client
    client = TelegramClient(None, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot starting in event mode...")

    await client.start(bot_token=TELETHON_BOT_TOKEN)
    print("Bot authorized successfully (bot mode)")

    # Start background upload worker
    asyncio.create_task(process_queue())

    # Keep running forever
    print(f"Listening for new videos in: {TARGET_CHANNEL}")
    await client.run_until_disconnected()

if __name__ == "__main__":
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
    asyncio.run(main())
