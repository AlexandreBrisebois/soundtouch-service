# Reference documents

## Bose SoundTouch Web API

- Local copy: [SoundTouch-Web-API.pdf](SoundTouch-Web-API.pdf)
- Official source: <https://assets.bosecreative.com/m/496577402d128874/original/SoundTouch-Web-API.pdf>
- Retrieved: 2026-10-22
- SHA-256: `294ddee5471bc74b8f692cfd36ecab8e2bbc8757408a50c2f25361af6f099d29`

The PDF is retained unchanged as the authority for the HTTP Web API shapes it
actually documents: source and now-playing observation, play-status values,
actual/target volume, distinct STOP and POWER commands, and change
notifications. It does **not** document AVTransport `SetAVTransportURI`, relay
lease ownership, UPNP/`INVALID_SOURCE` transitions, reconnecting a lost proxy
stream, or audible liveness. Wisp treats those as guarded implementation and
supervised-hardware evidence, never as promises from the PDF.

Wisp intentionally does not implement or expose the complete Bose API as a raw
proxy. Product capabilities add only the typed reads and commands needed for
their ownership and volume-safety contracts. A generic proxy would bypass those
contracts and is outside the service's scope.

## Bose SoundTouch end-of-life notice

- Local snapshot: [SoundTouch-End-of-Life.pdf](SoundTouch-End-of-Life.pdf)
- Official source: <https://www.bose.com/soundtouch-end-of-life>
- Bose update date: 2026-05-06
- Retrieved: 2026-10-22
- SHA-256: `e6b232b3a8c954ef7589fe5d6c6de12320bb4d76c30f445072261abd671e874c`

The notice is the authority for Bose's post-cloud product support statements.
It says local setup, remote controls, grouping, Bluetooth, AirPlay, AUX, and
Spotify Connect continue, while SoundTouch-app music-service browsing, Alexa
voice commands, and guaranteed preset access do not. Spotify Connect remains an
external workflow initiated from the Spotify app; a speaker-reported Spotify
source is not a Wisp-controlled music-service integration.

The notice does not state that independently supplied internet-radio streams
are unavailable. It must not be used to remove or weaken Wisp's station library,
radio Play/Test/diagnostic intents, scheduled radio, relay ownership, Stop, or
bounded relay-recovery behavior. Those capabilities depend on Wisp's own stream
and supervised-speaker evidence rather than Bose's retired cloud service.

## Community implementations

When a SoundTouch behavior or integration is unclear, consult the
[bosefirmware repositories](https://github.com/bosefirmware?tab=repositories)
for prior art and implementation ideas. The collection includes examples in
Python, Rust, JavaScript/TypeScript, command-line tools, Home Assistant,
multi-room control, proxies, replacement servers, and embedded remotes.

Use these projects as inspiration and corroborating evidence, not as protocol
authority. Validate behavior against the official API document and supervised
speaker observations, and check the individual repository's license before
reusing code.
