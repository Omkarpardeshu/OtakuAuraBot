# Phase 4 changelog

- Added startup/deployment preflight checks for required secrets, Render webhook secret, database-directory writability, and Telegram-safe prompt length.
- Moved Render webhook-secret validation into preflight so configuration errors are caught before the bot application starts.
- Added automated tests for deployment preflight and configuration validation.
- Added a complete Render deployment runbook, smoke-test checklist, persistence guidance, cost-control notes, rollback notes, and known-limitations document.
- Consolidated Phase 1–3 functionality into the final handoff ZIP.

## Requested OtakuAura branding and UX updates

- Added the supplied welcome artwork and personalized `/start` caption.
- Added BotFather setup instructions and the separate developer About text.
- Standardized generated, regenerated, and translated prompt responses with the requested heading.
- Added a Copy Prompt action that sends the complete prompt as plain text.
- Reduced the default per-user image cooldown from 20 seconds to 3 seconds.
- Tightened image-grounded prompt instructions and added Telegram UTF-16 message-length safety.
- Added the supplied profile/start-screen artwork for manual BotFather setup.

## Anime-tag, speed, and copy-action refinement

- Tightened the default anime tag instructions: fixed tag ordering, specific tag vocabulary, image-grounded details only, and no prose/filler/unsupported quality tags.
- Lowered Gemini generation randomness for more consistent visual tags and reduced the tag-mode output-token ceiling to limit unnecessary generation.
- Reduced default transient retry count to one and shortened retry backoff to improve recovery responsiveness. Retry settings remain configurable.
- Kept image preprocessing conservative: only oversized images are downscaled, preserving aspect ratio and fine detail.
- Corrected the copy UX: short prompts use Telegram's native Copy Text button; long prompts are provided as a `.txt` attachment. The bot no longer re-sends the prompt as a duplicate chat message.
- BotFather profile and `/start` welcome settings are intentionally unchanged per owner instruction.

## Phase 5 — Admin Sleep/Wake Controls
- Added admin-only `/sleep`, `/wake`, and `/status` commands.
- `/sleep` enables a persisted application Sleep Mode; the process and Telegram webhook/polling remain running so `/wake` can be received.
- Non-admin messages and callback actions are blocked while Sleep Mode is active. Admin updates remain available.
- Sleep Mode is stored in the configured SQLite database and survives application process restarts when that database file is retained.
- Important hosting limitation: Render Free web services can spin down and do not provide guaranteed always-on execution. A bot command cannot wake a fully stopped Render service. Use a paid always-on Render instance for continuous operation; use persistent storage or a configured persistent database if sleep-state persistence across redeploys is required.
