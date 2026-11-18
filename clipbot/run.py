"""Daily job: find a GTA 6 streamer, cut 5 best moments, schedule 5 Shorts.

    python -m clipbot.run                 # full run (needs YT_* secrets)
    python -m clipbot.run --dry-run       # make the videos, don't upload
    python -m clipbot.run --dry-run --video-id XXXX --streamer "Name"   # test on one stream
"""
import argparse
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from clipbot import editor, hooks, moments

ROOT = Path(__file__).parent
STATE = ROOT / "state" / "history.json"
OUT = Path(os.environ.get("CLIPBOT_OUT", ROOT.parent / "output"))


def load(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def schedule_times(cfg, n):
    tz = ZoneInfo(cfg["posting"]["timezone"])
    now = datetime.now(tz)
    times = []
    day = now.date()
    while len(times) < n:
        for hm in cfg["posting"]["times"]:
            h, m = map(int, hm.split(":"))
            t = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
            if t > now + timedelta(minutes=20) and len(times) < n:
                times.append(t)
        day += timedelta(days=1)
    return [t.astimezone(timezone.utc) for t in times]


def make_clips(stream, cfg, workdir, need, used_hooks):
    st, cl = cfg["style"], cfg["clips"]
    W, H = st["width"], st["height"]
    print(f"Analysing: {stream['title']}  ({stream['channel_title']})")
    info, starts = moments.pick_moments(stream["video_id"], workdir, cfg, need)
    credit = stream.get("handle") or stream["channel_title"]
    made = []
    for i, start in enumerate(starts):
        if len(made) >= need:
            break
        tag = f"{stream['video_id']}_{start}"
        raw = os.path.join(workdir, f"{tag}_raw.mp4")
        try:
            editor.download_clip(stream["video_id"], start, cl["length_seconds"], raw)
            words = editor.transcribe(raw, st["whisper_model"])
            words, mutes = editor.clean_words(words, cl["max_swears_per_clip"])
            if words is None:
                print(f"  skip {start}s: not YouTube-appropriate")
                continue
            text = " ".join(w["text"] for w in words)
            hook = hooks.pick_hook(text, stream["title"], used_hooks)
            used_hooks.add(hook)
            png = os.path.join(workdir, f"{tag}_hook.png")
            ass = os.path.join(workdir, f"{tag}.ass")
            editor.render_hook(hook, png, W, H, st["font"], st["emoji_font"])
            editor.write_ass(words, f"Streamer: {credit}", cl["length_seconds"], ass, W, H)
            final = str(OUT / f"{tag}.mp4")
            editor.render_short(raw, png, ass, mutes, final, W, H)
            made.append({"path": final, "hook": hook, "start": start, "stream": stream, "credit": credit})
            print(f"  ✓ clip at {start}s -> {hook}")
        except Exception as e:
            print(f"  clip at {start}s failed: {e}")
    return made


def describe(c, cfg):
    s = c["stream"]
    tags = " ".join(cfg["posting"]["hashtags"])
    title = f"{c['hook']} {cfg['posting']['hashtags'][0]} #shorts"
    desc = (f"{c['hook']}\n\n"
            f"🎮 Streamer: {s['channel_title']} {s.get('handle') or ''}\n"
            f"📺 Full stream: https://www.youtube.com/watch?v={s['video_id']}&t={c['start']}s\n"
            f"Go show {s['channel_title']} some love and subscribe!\n\n"
            f"Clipped with permission.\n\n{tags}")
    return title, desc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--video-id")
    ap.add_argument("--streamer", default="Streamer")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    hist = load(STATE, {"used_channels": [], "used_videos": [], "runs": []})
    OUT.mkdir(parents=True, exist_ok=True)
    workdir = str(OUT / "_work")
    os.makedirs(workdir, exist_ok=True)
    need = cfg["clips"]["per_day"]

    yt = None
    if args.video_id:
        candidates = [{"video_id": args.video_id, "title": "GTA 6 stream", "channel_id": "manual",
                       "channel_title": args.streamer, "views": 0}]
    else:
        from clipbot import youtube_api
        yt = youtube_api.client()
        me = youtube_api.my_channel(yt)
        print("Posting to channel:", me["snippet"]["title"] if me else "?")
        cutoff = datetime.now(timezone.utc) - timedelta(days=cfg["search"]["streamer_cooldown_days"])
        recent = {u["channel_id"] for u in hist["used_channels"]
                  if datetime.fromisoformat(u["date"]) > cutoff}
        skip = recent | set(cfg["search"]["blocklist_channels"]) | ({me["id"]} if me else set())
        candidates = [c for c in youtube_api.find_gta6_streams(yt, cfg)
                      if c["channel_id"] not in skip and c["video_id"] not in hist["used_videos"]]
        for c in candidates[:5]:
            c["handle"] = youtube_api.channel_handle(yt, c["channel_id"])
        print(f"{len(candidates)} new GTA 6 streams found")

    clips, used_hooks = [], set()
    # Today's streamer first; only fall back to the next streamer if we're short.
    for stream in candidates[:4]:
        clips += make_clips(stream, cfg, workdir, need - len(clips), used_hooks)
        if len(clips) >= need:
            break
    shutil.rmtree(workdir, ignore_errors=True)
    if not clips:
        raise SystemExit("No clips made today.")

    times = schedule_times(cfg, len(clips))
    report = []
    for c, t in zip(clips, times):
        title, desc = describe(c, cfg)
        entry = {"file": c["path"], "title": title, "publish_at": t.isoformat(),
                 "streamer": c["stream"]["channel_title"]}
        if not args.dry_run:
            from clipbot import youtube_api
            vid = youtube_api.upload_short(yt, c["path"], title, desc, cfg["posting"]["tags"],
                                           cfg["posting"]["category_id"], t)
            entry["youtube_id"] = vid
            print(f"Scheduled {title!r} for {t.isoformat()} -> https://youtube.com/shorts/{vid}")
        else:
            print(f"[dry run] {title!r} would post at {t.isoformat()}")
        report.append(entry)

    if not args.dry_run:
        now = datetime.now(timezone.utc).isoformat()
        for s in {c["stream"]["channel_id"]: c["stream"] for c in clips}.values():
            hist["used_channels"].append({"channel_id": s["channel_id"], "name": s["channel_title"], "date": now})
            hist["used_videos"].append(s["video_id"])
        hist["runs"].append({"date": now, "clips": report})
        hist["runs"] = hist["runs"][-60:]
        hist["used_videos"] = hist["used_videos"][-500:]
        STATE.write_text(json.dumps(hist, indent=2))
    (OUT / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
