# OtakuAura Render Deployment Runbook

This runbook is for the person deploying the bot. Do not paste secrets into chat, source files, screenshots, or Git commits.

## 1. Before deployment

- Create the Telegram bot and keep its token private.
- Create an eligible Google AI API project and keep the API key private. Review current model availability, pricing, quotas, and data-handling terms in the provider console before enabling real users.
- Decide who will administer the bot and obtain that person's numeric Telegram user ID through a trusted method.
- Create a private Git repository and upload the contents of this ZIP (not the ZIP itself).

## 2. Render service

Create a **Web Service** from the repository. The included `render.yaml` supplies the Python runtime, build command, and start command. Confirm the current Render dashboard's plan and service settings before creating resources.

- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Render sets `RENDER_EXTERNAL_URL` and `PORT` for a web service. The app uses Telegram webhook mode when `RENDER_EXTERNAL_URL` is present; local runs use long polling.

Set these environment variables in Render's Environment page:

| Variable | Required | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Secret; never commit it |
| `GEMINI_API_KEY` | Yes for the current single-key setup | Secret; never commit it. Used as the first key. |
| `GEMINI_API_KEYS` | Optional | Future key pool: comma-separated Gemini API keys. Leave blank for now; when more keys are approved/configured, add them here in Render. Keys are tried in order and quota/rate-limit errors trigger fallback. Never commit keys. |
| `WEBHOOK_SECRET` | Yes on Render | Use a long, random secret token accepted by Telegram |
| `GEMINI_MODEL` | Recommended | Verify the exact model ID is currently available to this API key |
| `ADMIN_USER_IDS` | Optional | Comma-separated numeric Telegram user IDs |
| `DATABASE_PATH` | Recommended | SQLite operational data (preferences/history/usage); for a mounted disk use `/var/data/otakuaura.sqlite3` |
| `MONGO_URI` | Optional | MongoDB connection string. When set, MongoDB stores the bot user directory used by `/user` and `/broadcast`; invalid connection prevents startup rather than silently falling back. |
| `MONGO_DB_NAME` | Optional | MongoDB database name; default `otakuaura`. |
| `USER_DAILY_LIMIT` | Optional | Default 20 operations per user per UTC day |
| `GLOBAL_DAILY_LIMIT` | Optional | Default 500 operations per UTC day; `0` disables this app-level cap |
| `REQUEST_COOLDOWN_SECONDS` | Optional | Default 3 seconds between new image uploads |
| `AI_MAX_RETRIES` | Optional | Default 1 retry after the initial attempt; increase only if transient provider errors justify the added wait |
| `AI_CONCURRENCY` | Optional | Default 3 concurrent AI operations per process |

Never send API keys or bot tokens to the developer in a chat. The deploying adult/account owner should enter them directly in Render.

## 3. Persistent database storage

SQLite operational data (preferences, opt-in prompt history, and usage limits) is stored at `DATABASE_PATH`. When `MONGO_URI` is configured, the bot user directory used for `/user` and `/broadcast` is stored in MongoDB. A normal ephemeral filesystem can lose SQLite data on restart, redeploy, or instance replacement. If preferences and opted-in prompt history must persist, attach a Render persistent disk using a mount path such as `/var/data`, then set:

`DATABASE_PATH=/var/data/otakuaura.sqlite3`

Check current Render plan eligibility, disk pricing, and backup options in the Render dashboard. Do not assume a free instance includes a persistent disk. If no persistent disk is attached, treat local SQLite data as temporary and tell users settings/history may reset.

The `/user` admin report shows total registered users, broadcast audience, and rolling 30-day active users. The 30-day figure is an application estimate based on last activity recorded when a user starts the bot or uploads an image; it is not Telegram’s official profile statistic. The bot does not save uploaded images in the database. The most recent image is held in active process memory only for Regenerate and is lost on restart.

## 4. Preflight and smoke test

Before starting the service locally, run:

```bash
python -m pip install -r requirements.txt
python scripts/preflight.py
python -m compileall -q .
pytest -q
```

After deploying, verify in Telegram using a test account:

1. `/start`, `/help`, `/about`, `/settings`, and `/privacy` respond.
2. Upload a permitted JPG, PNG, and WebP image; confirm each returns an image-grounded prompt.
3. Test Natural, Tags, and Enhanced modes; all four detail levels; English, Hindi, and Hinglish.
4. Test Translate and Regenerate.
5. Test `/history_on`, `/history`, `/clear_history`, and `/history_off`; confirm history is opt-in and images are never stored.
6. Confirm an ordinary user cannot run `/admin_stats`; confirm a configured admin can.
7. Test invalid/oversized images, quota limits, cooldowns, and provider failure messaging.
8. Restart/redeploy and confirm preferences/history persist only when the persistent disk is attached and correctly mounted.
9. Check Render logs for startup errors. Logs should not contain API keys, image bytes, or prompt content.

## 5. Cost and operational controls

The app's daily request quotas and concurrency setting reduce accidental usage but are not a guaranteed monetary spend cap. Configure any available provider-side quotas/budget alerts separately and monitor actual usage. Provider pricing, model availability, and free-tier terms can change.

## 6. Rollback

Keep the last known-good Git commit. If a deployment fails, redeploy that commit from Render. Before schema-changing updates in future releases, take a database backup and test restoring it to a separate path. Do not overwrite the only production database during testing.

## 7. Go-live checklist

- [ ] Required secrets configured only in Render
- [ ] `WEBHOOK_SECRET` set and webhook startup passes preflight
- [ ] Exact Gemini model ID verified in provider console
- [ ] Persistent disk attached if durable preferences/history are required
- [ ] Admin IDs verified
- [ ] App quotas reviewed and provider billing controls checked
- [ ] Telegram smoke tests passed
- [ ] Privacy/history deletion behavior confirmed
- [ ] Rollback commit identified
- [ ] Bot's public `/about` and privacy wording reviewed

A green local test suite is not proof of live Telegram or Gemini connectivity. Mark production launch complete only after the live smoke test passes.


## Gemini API key management (admin commands)

Set `ADMIN_USER_IDS` to comma-separated numeric Telegram user IDs. Admins can manage extra Gemini keys in a private chat with the bot:

- `/addkey YOUR_GEMINI_API_KEY` — add and activate a key. The bot attempts to delete the command message; still use a private chat and delete it manually if it remains visible.
- `/listkeys` — show counts and numbered admin-added keys; actual secrets are never displayed.
- `/removekey 1` — remove the numbered admin-added key. Keys supplied through Render environment variables cannot be removed here.
- `/key_status` — show active key count.

The default key file is `data/gemini_keys.json`. For Render, set `GEMINI_KEYS_FILE` to a path on a persistent disk (for example `/var/data/gemini_keys.json`) or keys added in Telegram may be lost on redeploy/restart. Keep the file private; it contains API credentials. Existing environment keys (`GEMINI_API_KEY` and `GEMINI_API_KEYS`) continue to work. Key fallback only responds to quota/rate-limit errors and does not increase the quota granted by Google or bypass provider restrictions.

## OtakuAura branding and Telegram start screen

The bot sends `app/assets/welcome.jpg` with the personalized welcome caption whenever a user sends `/start`.

Telegram's pre-Start profile/intro screen is controlled by Telegram/BotFather, not by a normal bot message. To apply the supplied branding after deployment:

1. Open **@BotFather** and select this bot.
2. Use `/setuserpic` and upload `app/assets/start_screen_profile.jpg` (the supplied Ryuuzi Senpai HQ artwork).
3. Use `/setdescription` and set:

   `Part of:- @RyuziseHqB`

   Telegram displays its own **What can this bot do?** heading above the description.

4. Use `/setabouttext` and set:

   `Bot Developer:- TIWARI`

Telegram controls the exact placement and styling of these profile fields; the bot cannot force the developer credit into a particular bottom corner. The developer credit is kept separate from the main description by using the BotFather About text.

The `/start` welcome card uses `app/assets/welcome.jpg` and the personalized welcome text in `app/bot.py`.

## Response speed and copy action

The default per-user image-request cooldown is reduced from 20 seconds to 3 seconds (daily usage limits remain active). The image pipeline continues to use the configured Gemini Flash model and asynchronous worker-thread execution so a synchronous SDK call does not block Telegram's event loop. Actual completion time depends on Telegram download, image size, Gemini service latency, quota, and network conditions; a 2–3 second response cannot be guaranteed. The generated prompt is shown with the requested `✨NEW IMAGE PROCESSING✨` heading. Short prompts (up to Telegram's 256-character Copy Text limit) use a native one-tap copy button. Longer prompts use a `.txt` attachment so the full prompt is available without posting a duplicate copy into the chat; open the file and use Select all → Copy. Telegram bots cannot place arbitrary-length text directly on a user's clipboard with a single native button.


## Anime-tag output and copy behaviour

New users default to the anime-oriented **Tags** output mode. Existing users whose stored mode was `natural` are migrated to `tags`; users can still choose Natural or Enhanced in `/settings`. Tag generation uses a fixed subject-to-background ordering, low randomness for repeatability, deduplication, and image-grounded instructions. Danbooru-style tags remain in standard English even if a user selects Hindi/Hinglish for prose modes. The tag output ceiling is 520 tokens. These changes improve consistency but cannot guarantee that every visual detail is identified correctly.

For copy actions, Telegram's native `CopyTextButton` supports a maximum payload of 256 characters. Short prompts use that button. Longer prompts are delivered as a text-file attachment by the **Get Full Prompt** button. This avoids the previous behaviour of re-posting the same prompt as a second chat message.

## Admin Sleep/Wake controls (Phase 5)
- Set `ADMIN_USER_IDS` in Render to a comma-separated list of numeric Telegram user IDs.
- Authorized admins can use `/sleep`, `/wake`, and `/status` in the bot chat.
- `/sleep` is an application-level Sleep Mode, not a process shutdown. The Telegram process stays alive so an admin can send `/wake`.
- While sleeping, non-admin messages and button callbacks are blocked. Admins can still issue admin commands.
- Sleep state is saved in `DATABASE_PATH` (SQLite). It survives process restarts only while that database file is retained. For durability across redeploys/instance replacement, configure persistent storage for the database or extend persistence to a durable database.
- Render Free services may spin down when idle. No Telegram command can wake a service that is completely stopped. Choose a paid always-on Render instance for continuous availability. Platform restarts/outages can still occur.

## Updating from GitHub
1. Extract the delivered ZIP.
2. Open `OtakuAura_Final_Complete_Deployment_Bundle/OtakuAura/` and upload/commit the **contents of this `OtakuAura` folder** to the connected GitHub repository (including `main.py`, `app/`, `scripts/`, `tests/`, `requirements.txt`, `render.yaml`, and docs). Do not upload only the ZIP file.
3. If Render is connected to that GitHub repository, push/commit triggers a deploy (or use Manual Deploy → Deploy latest commit).
4. Keep existing Render environment variables, especially `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `ADMIN_USER_IDS`, `MONGO_URI` if used, and `WEBHOOK_SECRET`. Do not put secrets in GitHub.
5. Ensure `ADMIN_USER_IDS` contains the admin's numeric Telegram ID. After deployment, test `/status`, `/sleep`, then `/wake`.

## Responsiveness / concurrent updates (Phase 5)

The Telegram application processes up to 12 updates concurrently and uses a 16-connection HTTP pool. This prevents a long-running Gemini image request from holding up `/start`, `/help`, and unrelated commands. Synchronous SQLite/MongoDB work and image validation/resizing are moved to worker threads. Repeated `/start` calls reuse Telegram's cached welcome-photo `file_id` during the running process.

The bot acknowledges an image before downloading it. Logs include `/start response elapsed_seconds`, `telegram_download_seconds`, `image_prepare_seconds`, and `ai_seconds`; use these to identify whether delay is in Telegram, image preparation, or Gemini.

Copy behavior remains constrained by Telegram: native Copy Text supports up to 256 characters. Longer prompts are sent as a text-file attachment so the bot does not post the prompt as a duplicate chat message.
