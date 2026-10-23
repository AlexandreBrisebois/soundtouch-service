## Implementation and verification
- [x] Display native slots separately and add sanitized informational service summaries; preserve NAS browsing.
- [x] Make explicit Refresh rediscover with bounded deadlines and visible failures; reject stale responses.
- [x] Run isolated regression tests and record evidence, including unchanged identity and ambiguity contracts.

Evidence: 220 tests passed across test_library, test_favorites, test_presets_ui, test_playback_ui, test_routes_validation, test_discovery_identity, and test_stations_ui in the installed wisp-chom-tests:d8a4baf-4602fa2b image with --network none and a read-only checkout. Strict noninteractive OpenSpec validation and git diff --check passed. No device controls or app restart performed; activation and real-speaker qualification remain with the owner.
