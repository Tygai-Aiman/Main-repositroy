"""Find the best moments in a stream.

Signals (combined):
  1. YouTube "Most replayed" heatmap - what viewers rewatched.
  2. Audio excitement - loud spikes vs the streamer's normal volume
     (screaming, explosions, crashes, gunfights).
"""
import os
import subprocess

import numpy as np
import yt_dlp


def ydl_opts(extra=None):
    o = {"quiet": True, "no_warnings": True, "noprogress": True}
    if os.environ.get("YT_COOKIES_FILE") and os.path.exists(os.environ["YT_COOKIES_FILE"]):
        o["cookiefile"] = os.environ["YT_COOKIES_FILE"]
    o.update(extra or {})
    return o


def video_info(video_id):
    with yt_dlp.YoutubeDL(ydl_opts({"skip_download": True})) as y:
        return y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)


def heatmap_curve(info, duration):
    curve = np.zeros(int(duration) + 1)
    for h in info.get("heatmap") or []:
        a, b = int(h["start_time"]), min(int(h["end_time"]), int(duration))
        curve[a:b + 1] = np.maximum(curve[a:b + 1], h["value"])
    return curve


def audio_curve(video_id, workdir, duration):
    """Per-second loudness z-score from a low-bitrate audio download."""
    out = os.path.join(workdir, f"{video_id}_audio.%(ext)s")
    with yt_dlp.YoutubeDL(ydl_opts({"format": "worstaudio/bestaudio", "outtmpl": out})) as y:
        y.download([f"https://www.youtube.com/watch?v={video_id}"])
    path = next(os.path.join(workdir, f) for f in os.listdir(workdir) if f.startswith(f"{video_id}_audio"))
    sr = 8000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    os.remove(path)
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    n = len(pcm) // sr
    rms = np.sqrt((pcm[:n * sr].reshape(n, sr) ** 2).mean(axis=1) + 1e-6)
    db = 20 * np.log10(rms)
    # Compare to a rolling ~2 min baseline so quiet & loud streamers both work.
    k = 121
    base = np.convolve(db, np.ones(k) / k, mode="same")
    z = (db - base) / (db.std() + 1e-6)
    # Smooth over ~5s so a single bang doesn't beat a sustained hype moment.
    z = np.convolve(z, np.ones(5) / 5, mode="same")
    curve = np.zeros(int(duration) + 1)
    curve[:min(len(z), len(curve))] = z[:len(curve)]
    return curve


def pick_moments(video_id, workdir, cfg, count):
    c = cfg["clips"]
    info = video_info(video_id)
    duration = int(info.get("duration") or 0)
    if duration < 600:
        return info, []
    heat = heatmap_curve(info, duration)
    try:
        aud = audio_curve(video_id, workdir, duration)
    except Exception as e:  # audio is a bonus signal
        print("  audio analysis failed:", e)
        aud = np.zeros(duration + 1)
    norm = lambda a: (a - a.min()) / (a.max() - a.min() + 1e-9)
    score = (0.6 * norm(heat) + 0.4 * norm(aud)) if heat.any() else norm(aud)

    L = c["length_seconds"]
    lo, hi = c["skip_first_minutes"] * 60, duration - L - 30
    score[:lo] = -1
    score[hi:] = -1
    picks = []
    # Pick extra candidates; some get dropped later by the content filter.
    order = np.argsort(score)[::-1]
    for t in order:
        if score[t] <= 0 or len(picks) >= count * 2:
            break
        if all(abs(int(t) - p) >= c["min_gap_seconds"] for p in picks):
            picks.append(int(t))
    # Peak lands ~60% into the clip: build-up, then the payoff.
    starts = [max(0, p - int(L * 0.6)) for p in picks]
    return info, starts
