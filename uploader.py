import os
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

def get_drive_service():
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_str:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials_info = json.loads(json_str)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=credentials)

def upload_to_google_drive(filepath: str, folder_id=None, drive_service=None) -> bool:
    if not drive_service:
        drive_service = get_drive_service()

    filename = os.path.basename(filepath)

    file_metadata = {'name': filename, 'mimeType': 'video/mp4'}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(
        filepath,
        mimetype='video/mp4',
        resumable=True,
        chunksize=50 * 1024 * 1024
    )

    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        print(f"Uploaded: {filename} → ID: {file.get('id')} | Link: {file.get('webViewLink')}")
        return True
    except HttpError as e:
        print(f"Drive error: {e}")
        return False
    except Exception as e:
        print(f"Upload failed: {e}")
        return False
