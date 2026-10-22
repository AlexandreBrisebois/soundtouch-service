# ICI Première: opt-in container relay

This adapter supports only the existing Montréal ICI Première seed URL:
`https://rcavliveaudio.akamaized.net/hls/live/2006635/P-2QMTL0_MTL/master.m3u8`.
It is disabled unless `WISP_ENABLE_HLS_RADIO=1`; it also requires Linux and FFmpeg.
The scheduler's speaker-reachable HTTP `WISP_BASE_URL` and volume/ownership gate
remain required. It does not register Bose sources or write physical presets.

The fixed 128 kbps rendition currently uses unencrypted packed AAC segments.
Wisp fetches those over verified, public-IP-pinned HTTPS and converts bytes through
an FFmpeg stdin pipe to MP3. FFmpeg never receives a URL or playlist. Unexpected
playlist structures, encryption, initialization maps, sequence rollback, changed
segment identities, discontinuities, gaps, stale playlists, and fetch errors fail
closed. No automatic reconnect or process restart occurs. Starting near the last
three segments avoids replaying the provider's approximately one-hour window;
expect roughly 18 seconds of live-edge latency plus codec/speaker buffering.

Each speaker gets a separate session and converter. A maximum of two converters
can run concurrently; other MP3 stations do not require a converter. Closing a
session interrupts fetching and sends TERM, then KILL if necessary, to its process
group. Pipes and bounded segment buffers do not record radio to disk. Child stderr
is discarded rather than accumulated or exposed with provider details. The child
has a 512 MiB address-space limit, 32-descriptor limit, no core dumps, a 16 MiB
FFmpeg per-allocation cap, and single codec threads. These are not a container-wide
CPU/RAM limit: set suitable Docker memory/CPU limits for the actual deployment and
measure simultaneous playback there before relying on schedules.

The Dockerfile pins Alpine 3.24's `ffmpeg=8.1.2-r0`; package updates require a
reviewed pin change. Alpine package metadata lists GPL-2.0-or-later AND
LGPL-2.1-or-later. FFmpeg is a separate executable, not code linked into Wisp.
Redistributors must preserve package notices and satisfy applicable corresponding
source/license obligations; see the official package and FFmpeg legal resources:
- https://pkgs.alpinelinux.org/package/v3.24/community/x86_64/ffmpeg
- https://ffmpeg.org/legal.html
- https://ffmpeg.org/ffmpeg-protocols.html

Verification: bounded live playlist/single-segment inspection and local AAC-to-MP3
conversion succeeded. Automated tests use synthetic audio only, including concurrent
isolated sessions and cancellation. This is not a claim of sustained playback,
Docker image build, target-container performance, or physical-speaker acceptance.
Keep opt-in disabled until the built image and a brief supervised speaker test pass.
CHOM and Énergie provider access failures are not resolved by this adapter.
