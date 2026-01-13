import os
import asyncio
import queue
import json
import time
from datetime import datetime

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ────────────────────────────────────────────────────────────────────────────
# Configuration – all from environment variables
# ────────────────────────────────────────────────────────────────────────────

API_ID          = int(os.getenv("TELEGRAM_API_ID"))
API_HASH        = os.getenv("TELEGRAM_API_HASH")
STRING_SESSION  = os.getenv("STRING_SESSION")               # the long session string

TARGET_CHANNEL  = os.getenv("TARGET_CHANNEL")               # @username or -100xxxxxxxxxx

DOWNLOAD_DIR    = "downloads"
BASE_NAME       = "My vlog"
DELAY_SECONDS   = 60

# ────────────────────────────────────────────────────────────────────────────

SCOPES = ['https://www.googleapis.com/auth/drive']

upload_queue = queue.Queue()
video_counter = 0

def get_drive_service():
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_str:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_JSON env var")
    
    credentials_info = json.loads(json_str)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=credentials)

def upload_to_drive(filepath: str, folder_id=None, service=None):
    global video_counter
    
    if not service:
        service = get_drive_service()

    filename = os.path.basename(filepath)

    file_metadata = {
        'name': filename,
        'mimeType': 'video/mp4'
    }
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(
        filepath,
        mimetype='video/mp4',
        resumable=True,
        chunksize=50 * 1024 * 1024
    )

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

async def upload_worker():
    service = get_drive_service()
    while True:
        if not upload_queue.empty():
            path = upload_queue.get()
            success = upload_to_drive(
                path,
                folder_id=os.getenv("DRIVE_FOLDER_ID"),
                service=service
            )
            if success:
                try:
                    os.remove(path)
                except:
                    pass
            await asyncio.sleep(DELAY_SECONDS)
        else:
            await asyncio.sleep(3)

@client.on(events.NewMessage(chats=TARGET_CHANNEL))
async def new_video_handler(event):
    global video_counter

    if not event.video:
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] New video detected")

    path = await event.download_media(file=DOWNLOAD_DIR)
    if not path:
        print("Download failed")
        return

    video_counter += 1
    ext = os.path.splitext(path)[1] or ".mp4"
    new_filename = f"{BASE_NAME} {video_counter}{ext}"
    new_path = os.path.join(DOWNLOAD_DIR, new_filename)

    os.rename(path, new_path)
    print(f"Renamed → {new_filename}")

    upload_queue.put(new_path)
    print(f"Queued for upload → {new_filename}  (#{video_counter})")

async def main():
    global client

    if not STRING_SESSION:
        print("STRING_SESSION environment variable is missing!")
        return

    client = TelegramClient(
        StringSession(STRING_SESSION),
        API_ID,
        API_HASH
    )

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting bot (user mode) ...")

    await client.start()
    print("Session authorized successfully")

    if not TARGET_CHANNEL:
        print("Warning: TARGET_CHANNEL not set → listening to ALL chats!")
    else:
        print(f"Listening for new videos in: {TARGET_CHANNEL}")

    # Start background upload task
    asyncio.create_task(upload_worker())

    # Keep the bot running
    await client.run_until_disconnected()

if __name__ == "__main__":
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    asyncio.run(main())
