"""YouTube Data API helpers: auth, search for GTA 6 streams, upload Shorts."""
import os
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def my_channel(yt):
    items = yt.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    return items[0] if items else None


def _iso_minutes(d):
    # PT1H23M45S -> minutes
    import re
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 1440 + h * 60 + mi + s / 60


def find_gta6_streams(yt, cfg):
    """Return candidate finished GTA 6 livestreams, best (most viewed) first."""
    s = cfg["search"]
    after = (datetime.now(timezone.utc) - timedelta(hours=s["max_age_hours"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = []
    for q in s["queries"]:
        res = yt.search().list(part="id", q=q, type="video", eventType="completed",
                               order="viewCount", publishedAfter=after, maxResults=25,
                               relevanceLanguage="en", safeSearch="moderate").execute()
        ids += [i["id"]["videoId"] for i in res.get("items", [])]
    ids = list(dict.fromkeys(ids))
    out = []
    for i in range(0, len(ids), 50):
        res = yt.videos().list(part="snippet,contentDetails,statistics,status",
                               id=",".join(ids[i:i + 50])).execute()
        for v in res.get("items", []):
            title = v["snippet"]["title"].lower()
            if not any(k in title for k in s["title_must_contain"]):
                continue
            if v["snippet"].get("liveBroadcastContent") != "none":
                continue  # still live / upcoming
            if v["status"].get("madeForKids"):
                continue
            if _iso_minutes(v["contentDetails"].get("duration")) < s["min_duration_minutes"]:
                continue
            out.append({
                "video_id": v["id"],
                "title": v["snippet"]["title"],
                "channel_id": v["snippet"]["channelId"],
                "channel_title": v["snippet"]["channelTitle"],
                "views": int(v["statistics"].get("viewCount", 0)),
            })
    out.sort(key=lambda x: x["views"], reverse=True)
    return out


def channel_handle(yt, channel_id):
    res = yt.channels().list(part="snippet", id=channel_id).execute().get("items", [])
    if not res:
        return None
    return res[0]["snippet"].get("customUrl")  # e.g. "@somestreamer"


def upload_short(yt, path, title, description, tags, category_id, publish_at_utc):
    body = {
        "snippet": {"title": title[:100], "description": description[:4900],
                    "tags": tags, "categoryId": category_id},
        "status": {"privacyStatus": "private",           # required for scheduled publish
                   "publishAt": publish_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": False},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]
