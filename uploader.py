import os
import json
from typing import List, Optional

from telethon import TelegramClient

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/drive']


def get_drive_service():
    """Create authenticated Google Drive v3 service using service account JSON"""
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_str:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")

    credentials_info = json.loads(json_str)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=SCOPES
    )

    return build('drive', 'v3', credentials=credentials)


async def download_videos(client: TelegramClient, entity: str, limit: int) -> List[str]:
    """Download video files from channel (oldest first)"""
    paths = []

    async for msg in client.iter_messages(entity, limit=limit, reverse=True):
        if msg.video:
            path = await msg.download_media(file="downloads/")
            if path:
                paths.append(path)

    return paths


def rename_videos(paths: List[str], base_name: str) -> List[str]:
    """Rename files sequentially: base_name 1.mp4, base_name 2.mp4, …"""
    renamed = []

    for i, old_path in enumerate(paths, 1):
        _, ext = os.path.splitext(old_path)
        if not ext:
            ext = ".mp4"

        new_name = f"{base_name} {i}{ext}"
        new_path = os.path.join("downloads", new_name)

        os.rename(old_path, new_path)
        renamed.append(new_path)

    return renamed


def upload_to_google_drive(
    filepath: str,
    folder_id: Optional[str] = None,
    drive_service=None
) -> bool:
    """Upload video file to Google Drive — resumable for large files"""
    if not drive_service:
        drive_service = get_drive_service()

    filename = os.path.basename(filepath)

    file_metadata = {
        'name': filename,
        'mimeType': 'video/mp4'   # change if you have other formats
    }

    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(
        filepath,
        mimetype='video/mp4',
        resumable=True,
        chunksize=50 * 1024 * 1024   # 50 MB chunks — good balance
    )

    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()

        print(f"Uploaded: {filename} → ID: {file.get('id')} | Link: {file.get('webViewLink')}")
        return True

    except HttpError as error:
        print(f"Google Drive error: {error}")
        if 'insufficientPermissions' in str(error).lower():
            print("→ Service account probably doesn't have write access to the folder!")
        return False
    except Exception as e:
        print(f"Upload failed: {e}")
        return False
