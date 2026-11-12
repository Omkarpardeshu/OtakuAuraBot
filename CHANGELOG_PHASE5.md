# Phase 5 — Bot responsiveness and interaction reliability

- Enabled bounded concurrent Telegram update processing (12 updates) with a matching HTTP connection pool. Long Gemini image analysis no longer queues `/start`, `/help`, and other commands behind the active image handler.
- Moved synchronous SQLite and MongoDB work used by Telegram handlers into worker threads so database waits do not block the async event loop.
- Kept the local SQLite user registration immediate and moved optional MongoDB directory synchronization to a background worker.
- Cached Telegram's returned welcome-photo `file_id` for the lifetime of the process. Repeated `/start` requests reuse Telegram's cached media instead of uploading the 338 KB asset every time.
- Added an immediate image-received acknowledgement; image validation and resizing now run in worker threads. Logs distinguish Telegram download, image preparation, Gemini processing, and `/start` response times.
- Preserved the welcome message design and the existing Sleep/Wake commands.
- Preserved the safe copy behavior: native Telegram Copy Text is used only within Telegram's 256-character limit; longer prompts are delivered as a `.txt` attachment rather than being posted as a duplicate chat message. Telegram bots cannot use the native one-tap copy button for arbitrary-length text.

## Notes

This phase improves queueing, event-loop responsiveness, and repeat `/start` latency. It cannot remove Gemini model latency, Botkeep network latency, or Telegram API delays. The first `/start` after a process restart still uploads the welcome image once to obtain a new process-local cached `file_id`.
