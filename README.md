# SoundTouch Routine Manager

Automate your Bose SoundTouch speakers without effort.

## What It Is
This service finds Bose speakers on your local network. It turns them on when you wake up and turns them off when you sleep. You control the schedule, the volume, and the preset audio station. 

If a speaker is already playing music during a scheduled start time, the service will not interrupt it.

## The Schedule
You provide a simple JSON schedule. The app reads it and does the work. You can optionally specify which days a routine should run (if omitted, it runs every day).

```json
{
  "Living Room": [
    {
      "name": "Morning Routine",
      "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
      "on_time": "06:15",
      "off_time": "07:30",
      "preset": 1,
      "volume": 10
    },
    {
      "name": "Weekend Sleep In",
      "days": ["saturday", "sunday"],
      "on_time": "09:00",
      "off_time": "10:30",
      "preset": 2,
      "volume": 20
    }
  ]
}
```

## The API
You do not have to edit the file by hand. The app provides a fast REST API. You can add, update, and delete schedules over your network. Data saves safely through a background queue. Your files will not corrupt.

Open your browser to `http://<your-ip>:5000/apidocs` to see the live API manual. You can test commands directly from this page.

## Deployment
It runs perfectly in a Synology NAS Docker environment.

1. **Host Network:** Run the Docker container in "Host" network mode. This is required to find speakers.
2. **Mount Config:** Map `./config.json` to `/app/config.json`. The app writes schedule changes here. It will not break your file link.

## Documentation
This tool uses the official Bose SoundTouch Web API.
