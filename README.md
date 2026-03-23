# SoundTouch Routine Manager

Automate your Bose SoundTouch speakers. This app finds your speakers on the local network. It manages a simple schedule to control power, volume, and audio sources.

## Features

* **Fast Setup:** Finds speakers on your network fast.
* **Smart Time:** Plays music in the morning and stops it at night.
* **Weekends:** Make one routine for weekdays and one for weekends.
* **Polite System:** It checks if music is already playing. It will never interrupt your songs.
* **Live API:** Add schedules from your browser using the built-in REST API.
* **NAS Ready:** Runs great as a simple Docker image using Host networking.

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
      "fade_out_duration": 60
    }
  ]
}
```

## The API

You do not have to edit the file by hand. The app provides a fast REST API. You can add, update, and delete schedules over your network. Data saves safely through a background queue. Your files will not corrupt.

Open your browser to `http://<your-ip>:5000/apidocs` to see the live API manual. You can test commands directly from this page.

## Deployment

The app runs perfectly in a Synology NAS Docker environment. GitHub Actions automatically builds and publishes the newest container image to Docker Hub whenever a release tag is pushed. You do not need to build it yourself!

1. **Host Network:** Run the Docker container in "Host" network mode. This is required to find speakers.
2. **Mount Config:** Map `deployment/config.json` to `/workspace/config.json`. The app writes schedule changes here. It will not break your file link.

## Documentation

This tool uses the official Bose SoundTouch Web API.
