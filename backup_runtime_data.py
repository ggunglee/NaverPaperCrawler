import argparse
import json
import mimetypes
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from config import SAFE_DIR, ensure_app_dirs


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
BACKUP_PREFIX = "naver-runtime-backup"


def parse_args():
    parser = argparse.ArgumentParser(description="Back up runtime data to Google Drive.")
    parser.add_argument("--runtime-dir", type=Path, default=SAFE_DIR)
    parser.add_argument("--keep", type=int, default=14, help="Number of Drive backups to keep.")
    parser.add_argument("--skip-if-unconfigured", action="store_true")
    return parser.parse_args()


def drive_configured():
    return bool(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") and os.environ.get("GOOGLE_DRIVE_FOLDER_ID"))


def credentials():
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=[DRIVE_SCOPE])
    creds.refresh(Request())
    return creds


def create_backup_zip(runtime_dir):
    runtime_dir = runtime_dir.expanduser()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(tempfile.gettempdir()) / f"{BACKUP_PREFIX}-{timestamp}.zip"
    roots = [
        runtime_dir / "data",
        runtime_dir / "reports",
        runtime_dir / "feedback",
        runtime_dir / "logs",
    ]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(runtime_dir))
    return output


def drive_headers(creds):
    return {"Authorization": f"Bearer {creds.token}"}


def upload_file(creds, folder_id, path):
    metadata = {"name": path.name, "parents": [folder_id]}
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    boundary = "naverpaperboundary"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
            json.dumps(metadata).encode("utf-8"),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    headers = drive_headers(creds)
    headers["Content-Type"] = f"multipart/related; boundary={boundary}"
    response = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,size",
        headers=headers,
        data=body,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def list_backups(creds, folder_id):
    query = (
        f"'{folder_id}' in parents and "
        f"name contains '{BACKUP_PREFIX}-' and "
        "trashed = false"
    )
    response = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers=drive_headers(creds),
        params={
            "q": query,
            "fields": "files(id,name,createdTime)",
            "orderBy": "createdTime desc",
            "pageSize": 100,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("files", [])


def prune_backups(creds, folder_id, keep):
    backups = list_backups(creds, folder_id)
    deleted = 0
    for item in backups[max(keep, 0) :]:
        response = requests.delete(
            f"https://www.googleapis.com/drive/v3/files/{item['id']}",
            headers=drive_headers(creds),
            timeout=60,
        )
        if response.status_code not in {200, 204}:
            response.raise_for_status()
        deleted += 1
    return len(backups), deleted


def main():
    ensure_app_dirs()
    args = parse_args()
    if not drive_configured():
        message = "google_drive_backup_skipped=unconfigured"
        if args.skip_if_unconfigured:
            print(message)
            return 0
        raise SystemExit(message)
    creds = credentials()
    folder_id = os.environ["GOOGLE_DRIVE_FOLDER_ID"]
    backup = create_backup_zip(args.runtime_dir)
    uploaded = upload_file(creds, folder_id, backup)
    seen, deleted = prune_backups(creds, folder_id, args.keep)
    print(
        f"google_drive_backup_uploaded id={uploaded.get('id')} "
        f"name={uploaded.get('name')} size={uploaded.get('size')} "
        f"backups_seen={seen} backups_deleted={deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
