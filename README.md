# SoundTouch Routine Manager

Automate your Bose SoundTouch speakers. This app finds your speakers on the local network. It manages a simple schedule to control power, volume, and audio sources.

## Features

* **Phone-Friendly UI:** Manage your speakers from any phone or tablet in the house. No app to install, just a fast PWA.
* **Pause / Resume:** Temporarily pause any schedule (sick day, ped day, vacation) without losing it. Resume when ready.
* **Smart Time:** Plays music in the morning and stops it at night automatically.
* **Polite System:** It checks if music is already playing first. It will never interrupt your own songs.
* **NAS Ready:** Runs perfectly in a Docker container on port **9001**.
* **Zero Config Discovery:** Automatically finds SoundTouch speakers on your local network.

## The Web UI

Access the manager at `http://<your-ip>:9001` from your browser. 

* **Hub:** See all speakers at a glance with live status and current volume % indicators.
* **Detail:** Manage schedules, toggle power, and view active routines.
* **PWA:** Select "Add to Home Screen" on iOS or Android to use it like a native app. The icon and theme color are already configured.

## The Schedule

The app reads it and does the work. You can select which days a routine should run. 

### Fade Transitions
To ensure a gentle experience, the app supports volume fading:
* **Fade-In (Wake Up):** Gradually steps up volume from 0 to your target. Default is **300 seconds** (5 minutes).
* **Fade-Out (Sleep):** Gradually steps down volume to 0 before power off. Default is **60 seconds** (1 minute).

> [!IMPORTANT]
> All duration values (e.g., `fade_in_duration`) must be specified in **seconds**, not minutes.

```json
{
  "Living Room": [
    {
      "name": "Morning Routine",
      "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
      "on_time": "06:15",
      "off_time": "07:30",
      "preset": 1,
      "volume": 10,
      "fade_in_duration": 300,
      "fade_out_duration": 60,
      "paused": false
    }
  ]
}
```

## The API

You do not have to edit the file by hand. The app provides a fast REST API. You can add, update, and delete schedules over your network. Data saves safely through a background queue. Your files will not corrupt.

Open your browser to `http://<your-ip>:9001/apidocs` to see the live API manual. You can test commands directly from this page.

### Pause & Resume

Pause a schedule for a sick day, ped day, or vacation without losing the routine:

```
PATCH /api/<speaker_name>/schedules/<schedule_name>/pause
PATCH /api/<speaker_name>/schedules/<schedule_name>/resume
```

Both return `202 Accepted`. The `paused` flag is saved to disk. The schedule remains in the config and resumes on the next matching day once you resume it.

## Deployment

The app runs perfectly in a Synology NAS Docker environment. 

1. **Host Network:** Run the Docker container in "Host" network mode. This is required for mDNS discovery.
2. **Mount Config:** Map `deployment/config.json` to `/workspace/config.json`. The app writes schedule changes here.
3. **Port:** The manager serves the Web UI and API on port **9001** by default.

## Documentation

This tool uses the official Bose SoundTouch Web API.
