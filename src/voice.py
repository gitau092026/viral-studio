"""Free neural voiceover via edge-tts, with per-word timings for caption sync.

edge-tts emits either WordBoundary or (for some voices/versions) SentenceBoundary
events. We normalize both into a per-word timing list so captions always sync:
 - WordBoundary present -> use directly.
 - Only SentenceBoundary -> distribute words across each sentence's time window,
   weighted by word length. Approximate but reads perfectly for short-form captions.
"""
from __future__ import annotations

import asyncio

import edge_tts

_TICKS = 1e7  # edge-tts offsets/durations are in 100-nanosecond ticks


async def _stream(text: str, out_mp3: str, voice: str, rate: str, pitch: str, volume: str):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    word_events: list[dict] = []
    sentence_events: list[dict] = []
    audio_bytes = 0
    with open(out_mp3, "wb") as f:
        async for chunk in communicate.stream():
            t = chunk["type"]
            if t == "audio":
                f.write(chunk["data"])
                audio_bytes += len(chunk["data"])
            elif t == "WordBoundary":
                word_events.append({"text": chunk["text"],
                                    "start": chunk["offset"] / _TICKS,
                                    "end": (chunk["offset"] + chunk["duration"]) / _TICKS})
            elif t == "SentenceBoundary":
                sentence_events.append({"text": chunk["text"],
                                        "start": chunk["offset"] / _TICKS,
                                        "end": (chunk["offset"] + chunk["duration"]) / _TICKS})
    return word_events, sentence_events, audio_bytes


def _distribute_sentences(sentences: list[dict]) -> list[dict]:
    words: list[dict] = []
    for si, s in enumerate(sentences):
        tokens = s["text"].split()
        if not tokens:
            continue
        total = sum(len(tok) for tok in tokens) or 1
        span = max(s["end"] - s["start"], 0.2)
        t = s["start"]
        for tok in tokens:
            w = span * (len(tok) / total)
            words.append({"text": tok, "start": round(t, 3), "end": round(t + w, 3), "sent": si})
            t += w
    return words


def narrate(cfg: dict, text: str, out_mp3: str) -> list[dict]:
    """Write narration to out_mp3 and return [{text,start,end[,sent]}, ...] word timings."""
    v = cfg["voice"]
    args = (text, out_mp3, v["name"], v.get("rate", "+0%"), v.get("pitch", "+0Hz"), v.get("volume", "+0%"))

    words: list[dict] = []
    last_err = None
    for attempt in range(2):  # one retry — the endpoint occasionally returns an empty first stream
        try:
            word_events, sentence_events, audio_bytes = asyncio.run(_stream(*args))
        except Exception as e:  # network / service error
            last_err = e
            continue
        if audio_bytes > 0:
            words = word_events if word_events else _distribute_sentences(sentence_events)
            if words:
                return words
        last_err = RuntimeError("no audio/timing returned")

    raise RuntimeError(
        f"edge-tts failed after retries ({last_err}). Check your internet connection, or try a "
        f"different voice name in config.yaml (e.g. en-US-GuyNeural)."
    )
