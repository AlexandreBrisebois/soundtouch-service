# Test the Linux container locally

The container builds this checkout, including FFmpeg for ICI Première. It does not
pull a published Wisp release or require an ICI activation flag.

1. Start Docker Desktop (or a local Docker Engine on Linux).
2. Stop native Wisp with `task down` so port 9001 is free.
3. Use your computer's current LAN address, not localhost or a Docker VM address:

   ```sh
   export WISP_BASE_URL=http://YOUR_COMPUTER_LAN_IP:9001
   task container:up SPEAKER_IPS=YOUR_SPEAKER_LAN_IP
   ```

For several speakers, separate their IPs with commas (at most eight). If the base
URL is already set in your Taskfile's `env:` section, you do not need to export it
again. `SPEAKER_IPS` can alternatively be set as the `WISP_SPEAKER_IPS` environment
variable. A native Python `.venv` is required for the small task runner, as with
`task up`; the application itself runs in the Linux container.

Open http://localhost:9001, confirm the expected device appears, then test one
station under supervision. The task publishes port 9001 for LAN access; it does
not modify your firewall, Docker Desktop settings, or speaker configuration.

```sh
task container:logs
task container:down
```

`container:down` stops and removes only this checkout's labeled test container.
It leaves the local image and all test data in place. Stop the container before
using native `task up` again. Re-run `container:up` after pulling changes to rebuild
from the current checkout.

## Separate test data

On first startup, `.wisp-container/config.json` is copied from the native
`CONFIG_FILE` (normally `.wisp-dev.json`) with **all schedules paused**. If no source
exists, it starts with no schedules. Favorites are copied once from `FAVORITES_FILE`
or the favorites file next to that configuration; otherwise normal station seeding
applies. Original files are never modified.

Subsequent starts retain the container's edited config and library, including any
schedules you explicitly enabled during testing. The directory is gitignored and
is mounted as a directory so atomic favorites writes work. Time zone defaults to
`America/Toronto`; set `TZ` before startup for another time zone.

## Docker Desktop networking

These tasks use published ports, not Desktop's optional host-networking mode.
Wisp normally uses mDNS discovery, which is not reliably available across Desktop's
VM boundary. Explicit `WISP_SPEAKER_IPS` selects a read-only `/info` lookup instead:
only RFC1918 private IPv4 addresses are accepted, identity/name are refreshed on
normal discovery cycles, and the existing ambiguity/identity safeguards still apply.
List every speaker you want in this test; unset the variable to use normal mDNS.

Speaker-to-container radio delivery is still a hardware acceptance check. Wisp's
relay intentionally requires the incoming connection to have the speaker's source
IP. If your Docker Desktop networking rewrites that address, the relay will refuse
it rather than weaken that guard. Do not use a reverse proxy or forwarded-header
workaround. Report the failed station test; successful UI access alone does not
prove the speaker can fetch audio. Linux host-network deployment remains unchanged.

Docker references: [Desktop networking](https://docs.docker.com/desktop/features/networking/)
and [host-network limitations](https://docs.docker.com/engine/network/drivers/host/).

HLS radio is enabled by the Linux image by default. An explicitly exported
`WISP_ENABLE_HLS_RADIO=0` is respected by `container:up`.
