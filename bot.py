import os
import asyncio
import queue
import json
from datetime import datetime

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ────────────────────────────────────────────────────────────────────────────
# Configuration – all from environment variables
# ────────────────────────────────────────────────────────────────────────────

API_ID          = int(os.getenv("TELEGRAM_API_ID"))
API_HASH        = os.getenv("TELEGRAM_API_HASH")
STRING_SESSION  = os.getenv("STRING_SESSION")

TARGET_CHANNEL  = os.getenv("TARGET_CHANNEL")               # required: @username or -100xxxxxxxxxx

DOWNLOAD_DIR    = "downloads"
BASE_NAME       = "My vlog"
DELAY_SECONDS   = 60

# ────────────────────────────────────────────────────────────────────────────

SCOPES = ['https://www.googleapis.com/auth/drive']

upload_queue = queue.Queue()
video_counter = 0

# Create client globally (required for decorator)
client = TelegramClient(
    StringSession(STRING_SESSION),
    API_ID,
    API_HASH
)

# ──── Google Drive helpers ──────────────────────────────────────────────────

def get_drive_service():
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_str:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials_info = json.loads(json_str)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=credentials)

def upload_to_drive(filepath: str):
    global video_counter
    service = get_drive_service()
    filename = os.path.basename(filepath)

    file_metadata = {'name': filename, 'mimeType': 'video/mp4'}
    if os.getenv("DRIVE_FOLDER_ID"):
        file_metadata['parents'] = [os.getenv("DRIVE_FOLDER_ID")]

    media = MediaFileUpload(filepath, mimetype='video/mp4', resumable=True)

    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Uploaded → {filename}")
        print(f"Drive link: {file.get('webViewLink')}")
        return True
    except Exception as e:
        print(f"Upload failed: {filename} → {e}")
        return False

# ──── Background upload worker ──────────────────────────────────────────────

async def upload_worker():
    while True:
        if not upload_queue.empty():
            path = upload_queue.get()
            if upload_to_drive(path):
                try:
                    os.remove(path)
                except:
                    pass
            await asyncio.sleep(DELAY_SECONDS)
        else:
            await asyncio.sleep(3)

# ──── Keep-alive task (forces Telegram to send channel updates) ─────────────

async def channel_keep_alive():
    while True:
        try:
            # Fetch last message → triggers update flow for the channel
            await client.get_messages(TARGET_CHANNEL, limit=1)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Keep-alive: touched {TARGET_CHANNEL}")
        except Exception as e:
            print(f"Keep-alive failed: {e}")
        await asyncio.sleep(300)  # 5 minutes

# ──── Event handler ─────────────────────────────────────────────────────────

@client.on(events.NewMessage(chats=TARGET_CHANNEL))
async def new_video_handler(event):
    global video_counter

    if not event.video:
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] New video detected in {TARGET_CHANNEL}")

    path = await event.download_media(file=DOWNLOAD_DIR)
    if not path:
        print("Download failed")
        return

    video_counter += 1
    ext = os.path.splitext(path)[1] or ".mp4"
    new_filename = f"{BASE_NAME} {video_counter}{ext}"
    new_path = os.path.join(DOWNLOAD_DIR, new_filename)

    os.rename(path, new_path)
    print(f"Renamed to → {new_filename}")

    upload_queue.put(new_path)
    print(f"Queued → {new_filename}  (#{video_counter})")

# ──── Main startup ──────────────────────────────────────────────────────────

async def main():
    if not STRING_SESSION:
        print("ERROR: STRING_SESSION is missing in environment variables!")
        return

    if not TARGET_CHANNEL:
        print("WARNING: TARGET_CHANNEL not set → will listen to ALL incoming messages!")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting user-mode listener...")

    await client.start()
    print("Connected and authorized successfully")

    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # Start background tasks
    asyncio.create_task(upload_worker())
    asyncio.create_task(channel_keep_alive())

    print(f"Listening for new videos in: {TARGET_CHANNEL or 'all chats'}")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
