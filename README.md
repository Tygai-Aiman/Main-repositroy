# Megapithucs GTA 6 Shorts bot

Every day this bot:

1. Finds a GTA 6 livestream on YouTube from a **different streamer** than recent days.
2. Picks the **5 best moments**, using YouTube's "Most replayed" graph plus loud audio spikes (screams, explosions, chases).
3. Edits each one into a **vertical 1080x1920 Short** with:
   - big hook text at the top, like **"GTA 6 airport 🤯"**, chosen from what's said in the clip
   - word-by-word captions
   - **"Streamer: @name"** under the captions
   - swears bleeped (muted) and starred out in captions; clips with slurs or heavy swearing are skipped
4. Uploads all 5 to **megapithucs** and schedules them for **9am, 12pm, 3pm, 6pm and 9pm** (New York time), with a title, tags, hashtags and a description that credits and links the streamer.

The settings are in `clipbot/config.yaml`: posting times, time zone, tags, clip length and streamer cooldown.

## One-time setup (about 20 min)

### 1. Google Cloud: allow uploads to your channel
1. Go to https://console.cloud.google.com, then create a project (e.g. "megapithucs-bot").
2. **APIs & Services → Library**: enable **YouTube Data API v3**.
3. **OAuth consent screen**: set it to External, add your Gmail as a test user, then **Publish app** ("In production"). If you skip this, the login expires every 7 days.
4. **Credentials → Create credentials → OAuth client ID → Desktop app**, then download the JSON file.

### 2. Connect the megapithucs channel (on your computer)
```
pip install google-auth-oauthlib google-api-python-client
python -m clipbot.auth_setup path/to/client_secret.json
```
Sign in and **pick the megapithucs channel (red gorilla)**. It prints 3 values.

### 3. Add GitHub secrets
In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**:
- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`
- `YT_COOKIES` *(strongly recommended)*: your YouTube cookies in Netscape format, from a "Get cookies.txt" browser extension while logged in to a spare Google account. Without them, YouTube often blocks downloads from GitHub's servers.

### 4. Turn it on
The workflow has to be on the repo's **default branch** to run on a schedule. Then go to **Actions → Daily GTA 6 Shorts → Run workflow** and tick "dry run" to test it. The videos show up as a downloadable artifact on the run page.

## Important YouTube rules
- **Uploads from a new API project are stuck on *private*** until Google approves an API audit. Submit the free form at https://support.google.com/youtube/contact/yt_api_form ("audit and quota extension"). Until it's approved, videos upload but you must set each one to public yourself in YouTube Studio.
- The free quota (10,000 units a day) covers about 5 uploads a day, which is exactly what this bot does. Don't run it twice in one day.

## Test locally
```
python -m clipbot.run --dry-run --video-id <youtube_video_id> --streamer "@name"
```
