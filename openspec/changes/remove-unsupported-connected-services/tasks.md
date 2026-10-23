# Tasks

## 1. Speaker overview API contract

- [x] 1.1 Add a focused overview regression test asserting that generic `services`, Alexa, and Amazon Music are absent; speaker-reported Spotify becomes external `Spotify Connect` with Spotify-app guidance; and native presets, registered NAS sources, and radio capability data remain; verify the new assertions fail against the current response with `.venv/bin/pytest -q tests/test_favorites.py`.
- [x] 1.2 Replace the generic service-summary projection with the allowlisted external-playback projection for `SPOTIFY`; verify `.venv/bin/pytest -q tests/test_favorites.py tests/test_library.py` passes without changing source discovery, internet radio, ownership, volume, presets, or schedules.
- [x] 1.3 Add the Bose end-of-life notice to `docs/reference/README.md`, recording that Spotify Connect remains externally initiated and that the notice does not retire Wisp's independent internet-radio relay; verified the four-page local snapshot visually against the official page and recorded its source, retrieval date, and SHA-256 checksum.

## 2. Settings presentation

- [x] 2.1 Update focused browser-contract coverage to assert that Settings replaces Connected services with external Spotify Connect guidance, omits Alexa and Amazon Music, retains the Radio library control plus native buttons and NAS libraries, and still rejects an obsolete speaker response; verify the assertions fail against the current UI with `.venv/bin/pytest -q tests/test_presets_ui.py`.
- [x] 2.2 Replace the generic service markup and rendering path with non-actionable External playback rendering; verify `.venv/bin/pytest -q tests/test_presets_ui.py tests/test_stations_ui.py` passes and `node --check app/static/presets.js` succeeds.

## 3. Radio preservation and offline integration evidence

- [x] 3.1 Run `.venv/bin/pytest -q tests/test_stations_ui.py tests/test_playback_ui.py tests/test_playback_operations.py tests/test_radio_listening.py tests/test_radio_recovery.py tests/test_radio_relay.py tests/test_radio_stream.py`; verify the station library, Play/Test intents, scheduling-facing playback, relay ownership, and recovery contracts remain green without changing radio implementation.
- [x] 3.2 Run `.venv/bin/pytest -q tests/test_favorites.py tests/test_library.py tests/test_presets_ui.py`, `.venv/bin/ruff check app tests`, `.venv/bin/mypy`, and `task spec:check`; record passed, failed, and not-run evidence, with real-speaker and audibility qualification marked not applicable because the change sends no device command.

## Workflow follow-up

- Sync the delta into the main `web-interface-and-api` spec and archive the change only after implementation and review evidence are complete.
