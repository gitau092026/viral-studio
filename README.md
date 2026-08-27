# Viral Content Agent 🎬

An AI co-pilot that (1) **researches what's going viral** on YouTube in the motivation /
self-improvement niche and (2) **auto-produces faceless vertical Shorts** — neural voiceover +
cinematic b-roll + TikTok-style word-synced captions — ready for **YouTube Shorts, TikTok, and
Facebook/Reels**. Every tool in the stack is **free** (no credit card).

> **Format:** 1080×1920 vertical, 30–60s, burned-in captions. One render works on all three platforms.

---

## ⚠️ Read this first — how to actually get monetized

**YouTube monetization requires** 1,000 subscribers **plus** *either* 4,000 public watch-hours in 12
months *or* **10,000,000 Shorts views in 90 days**. The Shorts path is the realistic one for short
content. Hitting that in ~60 days from zero is aggressive — this tool maximizes your odds, it does
not guarantee them.

**The critical rule (July-2025 policy):** YouTube demonetizes *"mass-produced"* and *"repetitious"*
content, and explicitly names **faceless text-to-speech over stock footage** as a risk. **AI is
allowed** — but each video must carry an **original angle and real variation**.

👉 **That's why this is a co-pilot, not a robot.** It drafts a complete video; **you review, tweak one
line, and approve** before publishing. That human touch is the difference between getting monetized
and getting rejected. Don't skip the review step.

---

## The free stack

| Job | Tool | Key needed? |
|-----|------|-------------|
| Viral research | YouTube Data API v3 (10k units/day free) | Free key |
| Ideas + scripts | Google Gemini free tier | Free key *(optional — falls back to built-in scripts)* |
| Voiceover | `edge-tts` (Microsoft neural voices) | **No key** |
| B-roll | Pexels API | Free key *(optional — falls back to color backgrounds)* |
| Captions | derived from voice timings | — |
| Assembly | `ffmpeg` | — (binary install) |

---

## Setup (one time)

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Install ffmpeg (required for video assembly)
```bash
winget install --id=Gyan.FFmpeg -e
```
Then **close and reopen your terminal** so `ffmpeg` is on your PATH. Verify:
```bash
ffmpeg -version
```
(macOS: `brew install ffmpeg` · Linux: `sudo apt install ffmpeg`)

### 3. Add your free API keys
```bash
copy .env.example .env      # Windows  (macOS/Linux: cp .env.example .env)
```
Open `.env` and paste in the keys. Every one is free and needs **no credit card** — the file has
click-by-click instructions. Minimum to start:
- **`YOUTUBE_API_KEY`** — for `research` ([console.cloud.google.com](https://console.cloud.google.com))
- **`PEXELS_API_KEY`** — for real b-roll ([pexels.com/api](https://www.pexels.com/api/))
- **`GEMINI_API_KEY`** — optional, better scripts ([aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey))

### 4. Check everything
```bash
python run.py check
```

---

## Quick start

```bash
python run.py make --topic "discipline beats motivation"
```
This runs the whole pipeline and drops a finished video + metadata in `output/`. It works **even with
zero API keys** (built-in script + color background), so you can see it end-to-end immediately, then
add keys for real b-roll and trend-driven scripts.

---

## The daily workflow (aim for 1–3 videos/day)

```bash
# 1. See what's going viral right now (writes data/trend_report.md)
python run.py research

# 2. Turn those trends into original concepts (writes data/ideas.json)
python run.py ideas

# 3. Make a video from the top idea
python run.py make --from-ideas 1
#    ...or make a few at once
python run.py batch --count 3

# 4. REVIEW in output/  — watch it, edit the .script.txt line if needed, make sure it's YOURS

# 5. Get platform-ready captions + upload guidance
python run.py publish --file output/your-video.mp4
```

Each `make` produces, in `output/`:
- `<slug>.mp4` — the finished vertical video
- `<slug>.thumbnail.jpg` — a frame you can use as a cover
- `<slug>.metadata.json` — tailored title/description/hashtags for YT, TikTok, FB, IG
- `<slug>.script.txt` — the script (edit this to add your personal touch)

---

## Publishing

**YouTube / TikTok / Facebook / Instagram:** upload `output/<slug>.mp4` and paste the copy from
`python run.py publish`. Manual upload works today and avoids API-approval delays — it's the fastest
path to shipping. (Automated YouTube upload via OAuth is **Phase 2** — ask when you want it.)

**Cross-post the same file to all three** to multiply your reach. YouTube Shorts is your monetization
engine; TikTok and Reels are free extra distribution.

---

## Your 60-day playbook

1. **Pick a tight lane** and stay in it (e.g. *discipline & stoicism*). Consistency trains the algorithm.
2. **Post 1–3 Shorts/day.** Volume × quality. Batch on weekends.
3. **Hook in the first 1 second** — the script's first line is everything. Weak hook = dead video.
4. **Ride trends fast.** Run `research` often; when a topic spikes, make your original take *that day*.
5. **Edit every script** so it sounds like you, not a template. This keeps you monetizable.
6. **Study your analytics.** Double down on hooks/topics that keep viewers watching.
7. **Cross-post** every video to TikTok + Reels for compounding reach.

---

## Configuration

Everything is in [`config.yaml`](config.yaml) — niche keywords, voice, video length, caption style,
music. Sensible defaults are built in, so a missing value never breaks the pipeline. Popular tweaks:
- **Voice:** `voice.name` (try `en-US-GuyNeural`, `en-US-BrianNeural`, `en-US-EricNeural`)
- **Caption punch:** `captions.font_name: "Impact"`, bump `captions.fontsize`
- **Music:** drop a royalty-free track in `assets/music/`, set `music.enabled: true` and `music.path`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ffmpeg not found` | Install it (step 2) and **reopen your terminal** |
| edge-tts "no audio" | Transient network blip — rerun; or change `voice.name` in config |
| `research` fails | Set `YOUTUBE_API_KEY`; if quota exceeded, wait a day (resets) or use fewer keywords |
| Video has plain color backgrounds | Set `PEXELS_API_KEY` for real b-roll |
| Scripts feel generic | Set `GEMINI_API_KEY`, and always edit the script before posting |

---

## How it works (pipeline)

```
research ─► ideas ─► script ─► voice (edge-tts) ─► b-roll (Pexels) ─► captions ─► assemble (ffmpeg)
   │                                                                                     │
YouTube Data API                                                          output/<slug>.mp4 + metadata
```

Run tests (no keys/ffmpeg needed): `python tests/test_captions.py`

## Roadmap
- **Phase 2:** automated YouTube upload (OAuth), scheduling, content calendar
- **Phase 3:** TikTok/Meta posting APIs (after app approval), analytics feedback loop

---

*Use responsibly. Only use royalty-free music and respect each platform's terms. Always add your own
creative input — that's what makes content perform **and** keeps it monetizable.*
