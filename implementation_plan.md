# SoundTouch Sleeper App Implementation Plan

This app will automatically discover Bose SoundTouch speakers on your local network and safely turn them off at a designated time if they are actively playing. It is designed to run continuously inside a highly minimal Docker container, making it ideal for a Synology NAS device.

## User Review Required

- **Scheduling Preference:** How should we configure the pre-defined target time? For a Synology NAS, the easiest approach is via environment variables (e.g., passing `SLEEP_TIME=\"22:30\"` when creating the container) and having the internal python script wait for that time daily. Does this design work for you?
- **Target Filtering:** Should this sleep restriction apply indiscriminately to *every* SoundTouch speaker found on the network, or will you need a way to whitelist/blacklist specific rooms (e.g. only target the \"Kids Bedroom\" speaker)?

## Proposed Changes

The project will encompass the following files to ensure separation of concerns:

### Python Application Core
We will leverage Python with an orchestration utilizing lightweight dependencies like `requests` and `zeroconf`.
#### [NEW] [discovery.py](./discovery.py)
Independent script implementing mDNS (Bonjour) capabilities for device discovery, retrieving available SoundTouch IPs on the sub-net.
#### [NEW] [control.py](./control.py)
Script interfacing directly with the SoundTouch RESTful API. Handles:
- Requesting `/now_playing` status to check if a system is off, suspended, or playing.
- Transmitting `<key state=\"press\" sender=\"Gabbo\">STOP</key>` and `POWER` requests.
#### [NEW] [main.py](./main.py)
Entrypoint orchestrator mapping the discovery of speakers to the status check and command transmission logic. Runs a lightweight API (e.g., via Flask) for remote control operations (preset/power) on the main thread, while a background thread loops safely executing automated actions periodically using a standard scheduler.
#### [NEW] [requirements.txt](./requirements.txt)
Minimal package requirement manifest.

### System Containerization
#### [NEW] [Dockerfile](./Dockerfile)
Builds directly from `python:3-alpine` (historically under ~50MB image size). Copies app logic, installs bare-minimum dependencies, and designates the python app as its `ENTRYPOINT`.

### Documentation
#### [NEW] [README.md](./README.md)
Minimal documentation covering setup, environment variables, Synology installation instructions, and pointing to the official [SoundTouch Web API documentation](https://assets.bosecreative.com/m/496577402d128874/original/SoundTouch-Web-API.pdf).

## Verification Plan
### Automated Verification
- Sanity-check the container layer size to ensure image minimality.
- Verify core script structure handles errors correctly, meaning that unreceived network data won't crash the orchestrator.
- **[NEW] API Verification Script**: Create a test script (`test_api.py`) to verify API commands directly against the "Living Room" speaker. This script will:
  1. Set volume to 20%
  2. Trigger PRESET_1
  3. Wait 20 seconds
  4. Send the POWER off command
### Manual Verification
- We can execute the module live out-of-container on your network to verify speaker discovery works properly.
- Run a sleep scenario right away to confirm that the app correctly checks status and executes the stop/off flow exclusively on speakers currently playing.
