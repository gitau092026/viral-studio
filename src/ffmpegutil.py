"""Thin, robust wrapper around ffmpeg / ffprobe (called as subprocesses)."""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

_WIN_GLOBS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\BtbN.FFmpeg*\**\bin"),
    os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin"),
    r"C:\ffmpeg\bin",
]


def ensure_on_path() -> bool:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True
    for pattern in _WIN_GLOBS:
        for hit in glob.glob(pattern, recursive=True):
            if Path(hit, "ffmpeg.exe").exists():
                os.environ["PATH"] = hit + os.pathsep + os.environ.get("PATH", "")
                return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    return False


def has_ffmpeg() -> bool:
    return ensure_on_path()


def _require():
    if not has_ffmpeg():
        raise RuntimeError(
            "ffmpeg/ffprobe not found on PATH.\n"
            "  Windows:  winget install --id=Gyan.FFmpeg -e   (then reopen your terminal)\n"
            "  macOS:    brew install ffmpeg\n"
            "  Linux:    sudo apt install ffmpeg"
        )


def ff(args: list[str], cwd: str | None = None) -> None:
    _require()
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-12:]
        raise RuntimeError("ffmpeg failed:\n" + "\n".join(tail) + "\n\ncmd: ffmpeg " + " ".join(args))


def probe_duration(path: str) -> float:
    _require()
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return 0.0
    try:
        return float(json.loads(proc.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def make_color_clip(out_path: str, seconds: float, size: str = "1080x1920", color: str = "0x0B1220") -> str:
    ff([
        "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={max(seconds, 1):.2f}:r=30",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out_path),
    ])
    return str(out_path)


def extract_thumbnail(video_path: str, out_path: str, at_seconds: float = 1.0) -> str:
    ff(["-ss", f"{at_seconds:.2f}", "-i", str(video_path), "-frames:v", "1", "-q:v", "3", str(out_path)])
    return str(out_path)


def ensure_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path
