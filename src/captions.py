"""Build TikTok-style burned-in captions as an ASS subtitle file from word timings.

Pure string generation (no rendering libs) — ffmpeg's `ass` filter burns it in.
The active word is highlighted; a small rolling window of words is shown.
"""
from __future__ import annotations


def _hex_to_ass(color: str) -> str:
    """#RRGGBB -> &H00BBGGRR (ASS is BGR with an alpha byte; 00 = opaque)."""
    c = color.lstrip("#")
    if len(c) != 6:
        c = "FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H00{b}{g}{r}".upper()


def _t(seconds: float) -> str:
    seconds = max(seconds, 0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:  # rounding guard
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_groups(words: list[dict], max_words: int) -> list[list[dict]]:
    """Chunk consecutive words into caption groups of up to max_words.

    If words carry a 'sent' (sentence index), a new group starts at each sentence
    boundary so a caption line never spans two sentences.
    """
    max_words = max(max_words, 1)
    groups: list[list[dict]] = []
    current: list[dict] = []
    cur_sent = None
    for w in words:
        sent = w.get("sent")
        if current and (len(current) >= max_words or (sent is not None and sent != cur_sent)):
            groups.append(current)
            current = []
        current.append(w)
        cur_sent = sent
    if current:
        groups.append(current)
    return groups


def to_ass(words: list[dict], cfg: dict) -> str:
    cap = cfg["captions"]
    vid = cfg["video"]
    w, h = vid["width"], vid["height"]
    cx = w // 2
    cy = int(h * cap["position"])

    primary = _hex_to_ass(cap["primary_color"])
    highlight = _hex_to_ass(cap["highlight_color"])
    outline = _hex_to_ass(cap["outline_color"])
    bold = -1 if cap.get("bold", True) else 0

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{cap['font_name']},{cap['fontsize']},{primary},{primary},{outline},&H00000000,"
        f"{bold},0,0,0,100,100,0,0,1,{cap['outline']},{cap['shadow']},5,60,60,60,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: list[str] = []
    groups = build_groups(words, cap["max_words"])
    for group in groups:
        group_end = group[-1]["end"]
        for i, word in enumerate(group):
            start = word["start"]
            end = group[i + 1]["start"] if i + 1 < len(group) else group_end
            if end <= start:
                end = start + 0.12
            # render the whole group, highlighting the active word
            parts = []
            for j, gw in enumerate(group):
                token = gw["text"]
                if j == i:
                    parts.append(f"{{\\c{highlight}}}{token}{{\\c{primary}}}")
                else:
                    parts.append(token)
            text = f"{{\\an5\\pos({cx},{cy})}}" + " ".join(parts)
            events.append(f"Dialogue: 0,{_t(start)},{_t(end)},Default,,0,0,0,,{text}")

    return "\n".join(header + events) + "\n"
