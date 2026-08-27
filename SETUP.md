# YouTube auto-upload — one-time setup (free, no credit card)

The dashboard can upload straight to YouTube (Private, Public, or **scheduled** —
uploads Private now and auto-flips Public at a time you pick, so it works with
your PC off). This needs a one-time Google OAuth sign-in. ~10 minutes, $0.

Everything else in the app works **without** this — you can always copy the
captions and upload by hand.

---

## 1. Enable the API (reuse your existing project)

1. Go to <https://console.cloud.google.com/> and select the **same project** that
   holds your `YOUTUBE_API_KEY`.
2. **APIs & Services → Library →** search **"YouTube Data API v3" → Enable**
   (if it isn't already).

## 2. Configure the OAuth consent screen

1. **APIs & Services → OAuth consent screen.**
2. User type **External → Create**.
3. Fill the required fields (app name, your email). You can leave optional fields blank.
4. **Add your own Google account as a Test user.**
5. **IMPORTANT — Publish the app to Production.** On the consent-screen page click
   **PUBLISH APP** and confirm. If you leave it in *Testing*, Google **expires your
   refresh token after 7 days** and you'd have to reconnect weekly. Publishing to
   Production keeps you signed in. (Personal use needs **no** Google verification —
   the `youtube.upload` scope is "sensitive" but not "restricted".)

## 3. Create a Desktop OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID.**
2. Application type: **Desktop app** → **Create**.
3. Click **Download JSON**.

## 4. Save the client secret OUTSIDE OneDrive

Save the downloaded file as **`client_secret.json`** in your state folder:

```
%LOCALAPPDATA%\ViralContent\secrets\client_secret.json
```

(That's `C:\Users\<you>\AppData\Local\ViralContent\secrets\`. Run
`python run.py check` to see the exact path.)

> ⚠️ Do **not** put it in the project folder — this project lives in OneDrive,
> which syncs to the cloud. Secrets and your login token must never sync. The app
> deliberately keeps the DB, logs, and secrets in `%LOCALAPPDATA%` for this reason.

## 5. Connect

Either:

```bash
python run.py connect-youtube
```

or open the dashboard (`python run.py web`), go to **Publish**, and click
**Connect YouTube**.

Your browser opens Google's consent screen. The first time, you'll see an
**"unverified app"** warning — click **Advanced → Go to \<app name\> (unsafe)**.
This is expected and safe for your own personal app. Grant access.

A `token.json` is written next to `client_secret.json`. You're connected — the
app refreshes the token automatically from now on.

---

## Using it

- **Dashboard:** render → **Review** (clear all 5 checks → Approve) → **Publish**
  → choose Schedule / Private now / Public now → upload. Uploads are **gated**:
  the server refuses anything that hasn't passed the review checklist.
- **CLI:**
  ```bash
  python run.py upload   --file myvideo.mp4 --approve --mode schedule --publish-at 2026-08-28T18:30
  python run.py schedule --file myvideo.mp4 --at 2026-08-28T18:30 --approve
  python run.py analytics --refresh
  ```

## Quota (for reference)

Default free quota is **10,000 units/day**. An upload costs **1,600 units**
(~6 uploads/day); a stats refresh costs **1 unit** per video. Plenty for a
one-person channel.
