"""YouTube OAuth sign-in + resumable upload + statistics (free, no card).

Design notes:
- Desktop OAuth via InstalledAppFlow.run_local_server; credentials persist to
  token.json in the OUT-OF-ONEDRIVE secrets dir (see settings.load_config).
- Uploads default to Private. When a publishAt time is given the video MUST be
  private at upload; YouTube flips it public automatically at that time.
- Statistics use the OAuth service (not the API key) so private/scheduled videos
  the channel owns are visible.

Quota: videos.insert = 1600 units, videos.list = 1 unit; 10,000/day default.
"""
from __future__ import annotations

import logging
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

LOG = logging.getLogger("youtube")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# name (as emitted by metadata.py) -> numeric categoryId required by the API
_CATEGORY = {
    "People & Blogs": "22", "Education": "27", "Entertainment": "24",
    "Howto & Style": "26", "Comedy": "23", "Film & Animation": "1",
}
_RETRIABLE = {500, 502, 503, 504, 429}


# ---- paths / readiness ------------------------------------------------------
def client_secret_path(cfg: dict) -> Path:
    return Path(cfg["paths"]["secrets"]) / "client_secret.json"


def token_path(cfg: dict) -> Path:
    return Path(cfg["paths"]["secrets"]) / "token.json"


def is_configured(cfg: dict) -> bool:
    return client_secret_path(cfg).exists()


def has_token(cfg: dict) -> bool:
    return token_path(cfg).exists()


# ---- credentials ------------------------------------------------------------
def _save_token(tp: Path, creds: Credentials) -> None:
    tp.parent.mkdir(parents=True, exist_ok=True)
    tp.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(tp, 0o600)  # best-effort on Windows
    except OSError:
        pass


def get_credentials(cfg: dict) -> Credentials:
    """Load token.json; refresh if stale; else run the desktop browser flow."""
    tp = token_path(cfg)
    creds = None
    if tp.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(tp), SCOPES)
        except Exception as e:
            LOG.warning("token.json unreadable (%s); re-authorizing", e)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(tp, creds)
            return creds
        except Exception as e:
            LOG.warning("token refresh failed (%s); re-authorizing", e)

    cs = client_secret_path(cfg)
    if not cs.exists():
        raise RuntimeError(
            f"client_secret.json not found at {cs}. Create a Desktop OAuth client in the "
            f"Google Cloud Console and save it there (see the setup steps)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(cs), SCOPES)
    creds = flow.run_local_server(port=0)  # opens the browser, waits for consent
    _save_token(tp, creds)
    return creds


def build_service(cfg: dict):
    return build("youtube", "v3", credentials=get_credentials(cfg), cache_discovery=False)


def channel_title(cfg: dict) -> str | None:
    resp = build_service(cfg).channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    return items[0]["snippet"]["title"] if items else None


# ---- helpers ----------------------------------------------------------------
def _category_id(cfg: dict, meta: dict) -> str:
    name = (meta.get("youtube", {}) or {}).get("category")
    return _CATEGORY.get(name) or str(cfg.get("youtube", {}).get("category_id", 22))


def to_rfc3339_utc(value) -> str:
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    elif isinstance(value, datetime):
        dt = value
    else:
        raise ValueError("publish_at must be a datetime or ISO string")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- upload -----------------------------------------------------------------
def upload_video(cfg: dict, mp4_path: str, meta: dict, privacy: str = "private",
                 publish_at=None, on_progress=None) -> dict:
    svc = build_service(cfg)
    yt = meta.get("youtube", {}) or {}
    status = {
        "privacyStatus": "private" if publish_at else privacy,  # publishAt requires private
        "selfDeclaredMadeForKids": bool(yt.get("made_for_kids", False)),
    }
    if publish_at:
        status["publishAt"] = to_rfc3339_utc(publish_at)
    body = {
        "snippet": {
            "title": (yt.get("title") or Path(mp4_path).stem)[:100],
            "description": yt.get("description", ""),
            "tags": yt.get("tags", []),
            "categoryId": _category_id(cfg, meta),
        },
        "status": status,
    }

    media = MediaFileUpload(mp4_path, chunksize=4 * 1024 * 1024, resumable=True)
    request = svc.videos().insert(part="snippet,status", body=body, media_body=media)

    response, attempt = None, 0
    while response is None:
        try:
            chunk_status, response = request.next_chunk()
            if chunk_status and on_progress:
                on_progress(int(chunk_status.progress() * 100))
        except HttpError as e:
            if getattr(e, "resp", None) and e.resp.status in _RETRIABLE and attempt < 5:
                attempt += 1
                LOG.warning("retriable HTTP %s on upload; retry %d", e.resp.status, attempt)
                time.sleep(min(2 ** attempt, 30))
                continue
            raise
        except (socket.timeout, ConnectionError, OSError) as e:
            if attempt < 5:
                attempt += 1
                LOG.warning("transient upload error (%s); retry %d", e, attempt)
                time.sleep(min(2 ** attempt, 30))
                continue
            raise

    vid = response["id"]
    if on_progress:
        on_progress(100)
    LOG.info("uploaded video %s (privacy=%s publishAt=%s)", vid, status["privacyStatus"], status.get("publishAt"))
    return {"video_id": vid, "url": f"https://youtu.be/{vid}",
            "privacy": status["privacyStatus"], "publish_at": status.get("publishAt")}


# ---- statistics (OAuth so private/scheduled own videos are visible) ---------
def fetch_statistics(cfg: dict, video_ids: list[str]) -> list[dict]:
    svc = build_service(cfg)
    ids = [v for v in video_ids if v]
    out: list[dict] = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        resp = svc.videos().list(part="statistics,snippet", id=",".join(chunk)).execute()
        for it in resp.get("items", []):
            st = it.get("statistics", {})
            out.append({
                "id": it["id"],
                "views": int(st.get("viewCount", 0) or 0),
                "likes": int(st.get("likeCount", 0) or 0),
                "comments": int(st.get("commentCount", 0) or 0),
            })
    return out
