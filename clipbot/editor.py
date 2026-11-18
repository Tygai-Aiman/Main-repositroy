"""Download a moment, caption it, clean it, and render a vertical 1080x1920 Short."""
import os
import re
import subprocess

import yt_dlp
from PIL import Image, ImageDraw, ImageFont

from clipbot.moments import ydl_opts

# ---------- download ----------------------------------------------------------

def download_clip(video_id, start, length, out_path):
    opts = ydl_opts({
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": out_path,
        "download_ranges": yt_dlp.utils.download_range_func(None, [(start, start + length)]),
        "force_keyframes_at_cuts": True,
    })
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([f"https://www.youtube.com/watch?v={video_id}"])
    return out_path


# ---------- transcription ------------------------------------------------------

_whisper = None


def transcribe(path, model_name):
    global _whisper
    from faster_whisper import WhisperModel
    if _whisper is None:
        _whisper = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, _ = _whisper.transcribe(path, word_timestamps=True, vad_filter=True)
    words = []
    for s in segs:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append({"text": t, "start": w.start, "end": w.end})
    return words


# ---------- keep it YouTube-appropriate --------------------------------------

SLURS = re.compile(r"^(nigg|fag|retard|tranny|chink|spic|kike)", re.I)
SWEARS = re.compile(r"^(fuck|motherf|shit|bitch|cunt|dick|pussy|asshole|bastard|whore|slut|cock|damn|goddamn)", re.I)


def clean_words(words, max_swears):
    """Mask swears in captions, return intervals to mute. None = skip clip."""
    mutes, n = [], 0
    for w in words:
        core = re.sub(r"[^a-zA-Z]", "", w["text"])
        if SLURS.match(core):
            return None, None
        if SWEARS.match(core):
            n += 1
            w["text"] = core[0] + "*" * (len(core) - 1)
            mutes.append((max(0, w["start"] - 0.05), w["end"] + 0.05))
    if n > max_swears:
        return None, None
    return words, mutes


# ---------- captions (ASS) -----------------------------------------------------

def _ts(t):
    h, r = divmod(max(t, 0), 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(words, credit, length, path, W, H):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,84,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,8,60,60,1390,1
Style: Credit,DejaVu Sans,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,8,60,60,1560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    # 3-word chunks, current word highlighted yellow (TikTok/Shorts style).
    for i in range(0, len(words), 3):
        chunk = words[i:i + 3]
        end_chunk = words[i + 3]["start"] if i + 3 < len(words) else chunk[-1]["end"] + 0.4
        for j, w in enumerate(chunk):
            a = w["start"]
            b = chunk[j + 1]["start"] if j + 1 < len(chunk) else end_chunk
            txt = " ".join(
                ("{\\c&H00FFFF&}" + x["text"].upper() + "{\\c&HFFFFFF&}") if k == j else x["text"].upper()
                for k, x in enumerate(chunk))
            lines.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{txt}")
    # Streamer credit, always visible, under the captions.
    lines.append(f"Dialogue: 0,{_ts(0)},{_ts(length + 1)},Credit,,0,0,0,,{credit}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")


# ---------- hook text image (supports emoji) --------------------------------

def _is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0x2190 <= o <= 0x21FF or o in (0x200D, 0xFE0F)


def _runs(text):
    runs, cur, cur_e = [], "", None
    for ch in text:
        e = _is_emoji(ch)
        if cur and e != cur_e:
            runs.append((cur, cur_e))
            cur = ""
        cur, cur_e = cur + ch, e
    if cur:
        runs.append((cur, cur_e))
    return runs


def render_hook(text, out_png, W, H, font_path, emoji_path, size=96):
    font = ImageFont.truetype(font_path, size)
    efont = ImageFont.truetype(emoji_path, 109)  # Noto Color Emoji only renders at 109
    stroke = 8

    def measure(t):
        w = 0
        for r, e in _runs(t):
            if e:
                w += int(size * 1.15) * len([c for c in r if ord(c) not in (0x200D, 0xFE0F)])
            else:
                w += int(font.getlength(r))
        return w

    # word-wrap to 940px
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if measure(trial) > 940 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 190
    for line in lines:
        x = (W - measure(line)) // 2
        for r, e in _runs(line):
            if e:
                for c in r:
                    if ord(c) in (0x200D, 0xFE0F):
                        continue
                    g = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
                    ImageDraw.Draw(g).text((0, 0), c + "️", font=efont, embedded_color=True)
                    bbox = g.getbbox()
                    if bbox:
                        g = g.crop(bbox)
                    es = int(size * 1.05)
                    g = g.resize((es, es), Image.LANCZOS)
                    img.alpha_composite(g, (x, y + int(size * 0.05)))
                    x += int(size * 1.15)
            else:
                d.text((x, y), r, font=font, fill="white", stroke_width=stroke, stroke_fill="black")
                x += int(font.getlength(r))
        y += int(size * 1.25)
    img.save(out_png)


# ---------- final render ------------------------------------------------------

def render_short(src, hook_png, ass_path, mutes, out, W, H):
    fg_h = 960
    vf = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"boxblur=25:5,eq=brightness=-0.18[bg];"
        f"[0:v]crop='min(iw,ih*{W}/{fg_h})':ih,scale={W}:{fg_h}[fg];"
        f"[bg][fg]overlay=0:{(H - fg_h) // 2 - 120}[v1];"
        f"[v1][1:v]overlay=0:0[v2];"
        f"[v2]ass={ass_path},format=yuv420p[v]"
    )
    af = "".join(f"volume=enable='between(t,{a:.2f},{b:.2f})':volume=0," for a, b in mutes)
    af += "loudnorm=I=-14:TP=-1.5:LRA=11"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", src, "-i", hook_png,
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a?", "-af", af,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out,
    ], check=True)
    return out
