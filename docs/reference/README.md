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
