# Known Limitations Before Public Launch

- No live Telegram or Gemini API request can be verified by the offline automated test suite.
- Confirm that the configured Gemini model identifier is available for the deployment's API key; the model name is configurable via `GEMINI_MODEL`.
- The app-level request quotas count operations, not currency. Provider-side billing controls are still needed.
- SQLite persistence requires a durable mounted disk on the chosen host. Ephemeral storage can reset.
- Latest-image memory for Regenerate is per active bot process and disappears on restart; it is not a permanent image archive.
- A single process's semaphore does not coordinate concurrency across multiple service instances. Keep one instance unless shared coordination is added.
- Render free-instance sleep/availability behavior and persistent-disk eligibility can change; verify current plan limits before choosing production settings.
- Human review of sample outputs is needed to assess image-grounding and hallucinations before public launch.

- Telegram's native one-tap Copy Text button accepts at most 256 characters. OtakuAura uses it for short prompts; longer prompts are delivered as a UTF-8 `.txt` attachment to avoid reposting the entire prompt as a duplicate chat message.
- Anime tag output is the default mode. Users can still change output mode in `/settings`; existing stored Natural preferences are migrated to Tags once on startup as part of this product update.
- Image preprocessing only downsizes images whose longest side exceeds 2560 pixels; original bytes are retained for smaller images.
- Retry handling is limited to transient service, rate-limit, timeout, and network errors. Invalid keys, unsupported models, and malformed requests are surfaced without wasteful retries.
