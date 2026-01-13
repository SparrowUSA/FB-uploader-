import os
import requests
from typing import List

from telethon import TelegramClient


async def download_videos(client: TelegramClient, entity: str, limit: int) -> List[str]:
    """Download video files from channel (oldest → newest)"""
    paths = []

    async for msg in client.iter_messages(entity, limit=limit, reverse=True):
        if msg.video:
            # returns local path or None
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


def upload_to_facebook(filepath: str, page_id: str, access_token: str) -> bool:
    """Upload single video to Facebook Page using Graph API"""
    url = f"https://graph-video.facebook.com/v20.0/{page_id}/videos"

    with open(filepath, "rb") as f:
        files = {"file": f}
        data = {
            "access_token": access_token,
            "title": os.path.basename(filepath).rsplit(".", 1)[0],
            "description": "Uploaded from Telegram channel",
        }

        try:
            r = requests.post(url, data=data, files=files, timeout=1800)
            if r.status_code in (200, 202):
                print(f"OK  {os.path.basename(filepath)} → {r.json().get('id','–')}")
                return True
            else:
                print(f"FAIL {os.path.basename(filepath)} → {r.status_code} {r.text[:200]}")
                return False
        except Exception as e:
            print(f"Exception during upload: {e}")
            return False
