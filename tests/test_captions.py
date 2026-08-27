"""Dependency-free tests for the pure logic (captions + duration math + metadata).

Run directly (no pytest needed):   python tests/test_captions.py
Or with pytest:                     pytest tests/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import captions, metadata
from src.assemble import compute_beat_durations
from src.fallback_scripts import pick

CFG = {
    "video": {"width": 1080, "height": 1920, "fps": 30, "min_seconds": 30, "max_seconds": 60, "tail_seconds": 1.2},
    "captions": {
        "font_name": "Arial", "bold": True, "fontsize": 92,
        "primary_color": "#FFFFFF", "highlight_color": "#FFD400", "outline_color": "#000000",
        "outline": 6, "shadow": 2, "max_words": 3, "position": 0.72,
    },
}

WORDS = [
    {"text": "Stop", "start": 0.0, "end": 0.4},
    {"text": "waiting", "start": 0.4, "end": 0.9},
    {"text": "to", "start": 0.9, "end": 1.0},
    {"text": "feel", "start": 1.0, "end": 1.4},
    {"text": "motivated", "start": 1.4, "end": 2.1},
]


def test_hex_to_ass():
    assert captions._hex_to_ass("#FFFFFF") == "&H00FFFFFF"
    assert captions._hex_to_ass("#FFD400") == "&H0000D4FF"  # BGR order
    assert captions._hex_to_ass("bad") == "&H00FFFFFF"


def test_time_format():
    assert captions._t(0) == "0:00:00.00"
    assert captions._t(1.4) == "0:00:01.40"
    assert captions._t(65.999).startswith("0:01:06")  # rounding guard, no cs>=100


def test_build_groups():
    groups = captions.build_groups(WORDS, 3)
    assert [len(g) for g in groups] == [3, 2]


def test_to_ass_structure():
    ass = captions.to_ass(WORDS, CFG)
    assert "[Script Info]" in ass and "PlayResX: 1080" in ass
    assert ass.count("Dialogue:") == len(WORDS)      # one event per word (rolling highlight)
    assert "\\pos(540," in ass                        # centered horizontally
    assert "&H0000D4FF" in ass                        # highlight color present
    # every dialogue line is well-formed
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            assert line.count(",") >= 9


def test_beat_durations_sum_to_target():
    beats = [{"text": w["text"]} for w in WORDS]
    durs, target = compute_beat_durations(beats, narration_dur=12.0, cfg=CFG)
    assert len(durs) == len(beats)
    assert abs(sum(durs) - target) < 1e-6
    assert target >= CFG["video"]["min_seconds"]     # never below the 30s floor


def test_beat_durations_respect_min_floor():
    beats = [{"text": "a"}, {"text": "b"}]
    durs, target = compute_beat_durations(beats, narration_dur=2.0, cfg=CFG)
    assert target == 30                                # short voice -> padded to min
    assert all(d > 0 for d in durs)


def test_metadata_shape():
    scr = pick("discipline")
    meta = metadata.build_metadata(scr)
    assert set(meta) >= {"youtube", "tiktok", "facebook", "instagram"}
    assert meta["youtube"]["title"]
    assert any(t.lower() == "shorts" for t in meta["youtube"]["tags"])
    assert len(meta["tiktok"]["caption"]) <= 150


def _run():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")


if __name__ == "__main__":
    _run()
