# SoundTouch Sleep Timer Checklist

This is an independent, component-based breakdown of the steps required to build the SoundTouch sleep timer app. Each module can be built and tested individually.

- [X] **Phase 1: Project Setup & Research**
  - [X] Cloned existing repo to `soundtouch-service` as the working directory.
  - [X] Set up a virtual environment and generate `requirements.txt`.
  - [X] Review Bose SoundTouch Web API documentation for device discovery, state retrieval, and control commands.

- [X] **Phase 2: API Verification Test (`test_api.py`)**
  - [X] Create `test_api.py` to ensure commands to the speaker work effectively based on the referenced SoundTouch documentation.
  - [X] Program it to discover the "Living Room" speaker, set volume to 20%, run Preset 1, wait 20 seconds, and turn it off.

- [X] **Phase 3: Network Discovery Module (`discovery.py`)**
  - [X] Implement local network discovery (likely using `zeroconf` for mDNS Bonjour broadcasting).
  - [X] Create a function that returns a list of discovered SoundTouch device IP addresses and names.
  - [X] Test the script locally to confirm it successfully registers the speakers on the network.

- [X] **Phase 4: Status Query Module (`status.py`)**
  - [X] Implement a function to query a specific speaker's current power/playback state via `GET /now_playing`.
  - [X] Parse the XML response to definitively conclude if the speaker is "OFF" or currently playing media.

- [X] **Phase 5: Power Control Module (`control.py`)**
  - [X] Implement a function to send a `STOP` key press to ensure music stops.
  - [X] Implement a function to send a `POWER` key press sequentially afterwards to turn the speaker off.
  - [X] Verify both functions correctly construct necessary POST requests (`POST /key`).

- [X] **Phase 6: Main Orchestration, Scheduling, and API (`main.py`)**
  - [X] Implement the overarching orchestrator: Fetch IPs -> Check Status -> Halt/Power Off if active.
  - [X] Integrate a scheduler (e.g. `schedule` library) to run in a background thread for predefined operations.
  - [X] Expose a lightweight API (using a framework like Flask or FastAPI) with endpoints to manually power off or play a preset.
  - [X] Add basic logging (to stdout) to ensure activities are observable in Docker logs.

- [X] **Phase 7: Containerization for Synology**
  - [X] Write a minimal `Dockerfile` based on `python:3-alpine` to keep the footprint as small as possible.
  - [X] Test building the Docker image and confirm the image size is suitably small.
  - [X] Document instructions on how and where to inject environment variables (like the scheduled time) so it can be deployed on a Synology NAS.

- [X] **Phase 8: Documentation**
  - [X] Create a minimal `README.md` containing setup, deployment instructions, and referencing the official [Bose SoundTouch Web API documentation](https://assets.bosecreative.com/m/496577402d128874/original/SoundTouch-Web-API.pdf).

- [X] **Phase 9: Flexible Scheduling Feature**
  - [X] Implement new config schema that supports multiple named schedules per speaker.
  - [X] Support `on_time` with specified preset and volume, and `off_time`.
  - [X] Update background scheduler to parse and handle schedules, avoiding toggling OFF if already ON during `on_time`.
  - [X] Implement a `queue.Queue` background thread in `app/scheduler/jobs.py` to handle thread-safe configuration file writes.
  - [X] Update `config.json` and `deployment/config.json` templates to match the new syntax.
  - [X] Implement tests/validation for the new logic to ensure existing behavior is uninterrupted.

- [X] **Phase 10: API & Documentation Enhancements**
  - [X] Add `flasgger` to `requirements.txt` and initialize it in `app/main.py`.
  - [X] Create API routes in `app/api/routes.py` to GET, POST (add/update), and DELETE schedules.
  - [X] Integrate the new API routes with the configuration IO Queue to prevent deadlocks.
  - [X] Add Flasgger docstrings to all API endpoints for OpenAPI discoverability.
  - [X] Update `tests/test.http` with the new schedule CRUD endpoints.
  - [X] Update `tests/test_api.py` with cases targeting the new endpoints.

- [X] **Phase 11: CI/CD Pipeline**
  - [X] Design a GitHub Actions workflow YAML file for building and pushing the Docker image.
  - [X] Configure action securely mapping Docker Hub credentials (`DOCKER_USERNAME`, `DOCKER_PASSWORD`) using GitHub Secrets.
  - [X] Configure trigger natively for Semantic Versioning tags (e.g. `v1.0.0`).
  - [X] Extract Git tag dynamically and apply it as the Docker image tag (and `latest`) during the push phase.

- [X] **Phase 12: Weekend Scheduling**
  - [X] Update `config.json` default properties to include `"days"` with default `"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"`.
  - [X] Implement robust day-of-week parsing in `app/scheduler/jobs.py` during `run_scheduler_loop()`.
  - [X] Update Swagger UI definitions in `app/api/routes.py` to allow the new `"days"` query parameter as an explicit string array.
  - [X] Update Automated tests (`tests/test_api.py`) where applicable to ensure we don't regress.

- [X] **Phase 13: CI/CD Pipeline Refactor**
  - [X] Redesign `docker-publish.yml` to trigger on main branch pushes or tags.
  - [X] Replaced `metadata-action` plugin with robust POSIX shell tag verification and extraction.
  - [X] Hardcoded explicit `:latest` and `:<tag>` references into the Docker push step.

- [X] **Phase 14: AUX Audio Source Support**
  - [X] Update `deployment/config.json` default properties to include `"source": "AUX"` example.
  - [X] Update Swagger UI definitions in `app/api/routes.py` to allow the new `"source"` property.
  - [X] Implement robust `source` parsing in `app/scheduler/jobs.py` during `run_scheduler_loop()`.
  - [X] Update `app/core/control.py` to support `AUX_INPUT` action.
  - [X] Update `README.md` to explain the new property.

- [x] **Phase 15: Fade-In and Fade-Out Support**
  - [x] Investigate feasibility of fading volume for Bose SoundTouch speakers and threading behavior.
  - [x] Implement `get_volume` in `app/core/status.py`.
  - [x] Update `app/scheduler/jobs.py` configuration schema (`fade_in_duration`, `fade_out_duration`).
  - [x] Implement looping logic with `time.sleep` in `auto_on_job` (starting from 0).
  - [x] Implement looping logic with `time.sleep` in `auto_off_job` (stepping down to 0).
  - [x] Ensure manual interventions smoothly abort background fade threads.

- [x] **Phase 16: Schedule Pause / Resume**
  - [x] Add `"paused": false` field to the default config in `app/scheduler/jobs.py` (`get_default_config()`).
  - [x] Add a skip guard in `run_scheduler_loop()` to silently skip any schedule where `"paused": true`.
  - [x] Add `PATCH /api/<speaker_name>/schedules/<schedule_name>/pause` endpoint to `app/api/routes.py`.
  - [x] Add `PATCH /api/<speaker_name>/schedules/<schedule_name>/resume` endpoint to `app/api/routes.py`.
  - [x] Update `config.json` and `deployment/config.json` templates with the new `"paused"` field.
  - [x] Update `tests/test_api.py` with pause → verify → resume → verify integration test calls.
  - [x] Update `README.md` with Pause / Resume feature bullet, updated JSON example, and new API subsection.

- [x] **Phase 17: Phone-Friendly Web UI** *(branch: `feature/web-ui`)*
  - [x] Create feature branch `feature/web-ui` from `main`.
  - [x] Add `GET /` route in Flask serving the single-page HTML app from `app/templates/index.html`.
  - [x] Update `app/main.py` to set `template_folder` and `static_folder`.
  - [x] Update `Dockerfile` to `COPY app/templates/ ./app/templates/` and `COPY app/static/ ./app/static/`.
  - [x] **App icon** — copy generated icon to `app/static/icon.png`, served at `/static/icon.png`.
  - [x] **PWA manifest** — create `app/static/manifest.json` for Android "Add to Home Screen" support.
  - [x] **Cross-platform `<head>` tags** — `apple-touch-icon` (iOS), `manifest` (Android), `theme-color`, `viewport-fit=cover`.
  - [x] **Responsive layout** — max-width 540 px (tablet), 640 px (iPad landscape); single column on phones.
  - [x] **Hub screen** — discover speakers, show live status dots, one-tap to detail, "Turn Off All" in thumb zone.
  - [x] **Speaker Detail screen** — schedule list with pause (primary) / delete (secondary via `···`), power toggle, Add Schedule button.
  - [x] **Add/Edit Schedule form** — smart defaults, auto-name from on-time, day chips, volume slider, preset pills, ± fade stepper.
  - [x] **Pause/Resume flow** — toggle on card calls `PATCH /api/<speaker>/schedules/<name>/pause|resume`.
  - [x] **Delete flow** — `···` menu → confirmation sheet → `DELETE /api/<speaker>/schedules/<name>`.
  - [x] **Turn Off All flow** — confirmation sheet → power toggle all active speakers.
  - [x] Verify all flows on phone (375 px) and tablet (768 px) viewports.
  - [x] Run `pytest tests/test_api.py -v` to confirm no regressions.
  - [x] **AUX Support** — Add AUX pill to the schedule form and update payload logic.
  - [x] **Rich Status Info** — Show source (Spotify, AUX, etc.) and track metadata in the UI.
  - [x] **PWA Installability** — Added Service Worker (`sw.js`) to enable standalone mode on Android/Edge.


