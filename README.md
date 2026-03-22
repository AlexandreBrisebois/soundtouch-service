# SoundTouch Sleep Service

A containerized Python application that discovers Bose SoundTouch speakers on your local network using mDNS (Bonjour), exposes a lightweight REST API for remote control, and dynamically reads a JSON config file to act as an automated sleep timer for multiple speakers simultaneously.

Built to be minimal and runs perfectly in a **Synology NAS** Docker environment.

## Dynamic Configuration (`config.json`)

Instead of standard, rigid environment variables, the service dynamically watches a `config.json` file. You can adjust your speaker sleep schedules on the fly as a JSON object `{"Speaker Name": "HH:MM"}` without restarting the container!

Example `config.json`:
```json
{
  "Target Speaker 1": "22:30",
  "Target Speaker 2": "20:00",
  "Target Speaker 3": "23:00"
}
```

## Synology NAS Deployment

1. **Host Networking is Required**: Make sure you select the **"Host"** network mode when configuring your Docker container. This is strictly required because UDP mDNS packets (`_soundtouch._tcp.local.`) cannot broadcast to the rest of your network without it.
2. **Mount the Config File**: Mount a local file on your NAS (e.g., `/volume1/docker/soundtouch/config.json`) to `/app/config.json` in the container. Whenever you edit the file via **File Station**, the container will instantly obey the new schedules!
3. **Configure the Port**: Ensure the Flask server's port does not conflict with any other services on your NAS. By default, it runs on `5000`, but you can easily change this by setting the `PORT` environment variable in your Docker container settings (e.g. `PORT=8091`).

## REST API Features

A lightweight Flask web server runs simultaneously on the configured `PORT` to let you perform remote control operations via web calls (great for Apple Shortcuts or Home Assistant):

- **GET `/api/discover`** - Returns a JSON list of all discovered Bose SoundTouch systems.
- **GET `/api/<speaker_name>/status`** - Retrieves the current state (e.g. `STANDBY`, `PLAY_STATE`).
- **POST `/api/<speaker_name>/power`** - Toggles the power state of the speaker.
- **POST `/api/<speaker_name>/volume`** - Sets the speaker volume. Pass JSON like: `{ "volume": 20 }`.
- **POST `/api/<speaker_name>/preset/<num>`** - Triggers a specific preset (`1` through `6`).

## Documentation

This implementation was designed directly aligning with the official [Bose SoundTouch Web API documentation](https://assets.bosecreative.com/m/496577402d128874/original/SoundTouch-Web-API.pdf).
