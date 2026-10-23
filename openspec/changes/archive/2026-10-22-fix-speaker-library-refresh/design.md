## Context
The favorites overview already reads native presets but the UI only displays Wisp favorites. Source parsing previously retained only NAS and local radio. Hub Refresh used cached discovery, leaving blank hardware identities unresolved.

## Decisions
Keep native slots, Wisp favorites, and informational service availability separate. Group service types using fixed public names; never return account identifiers or account display names. Preserve the existing NAS source collection and browsing checks. Explicit hub and panel Refresh request rediscovery rather than adding repeated implicit retries for offline devices. Use a 20-second hub deadline and a 45-second panel read deadline spanning rediscovery and sequential reads. Reject expired requests and responses from previous views or speakers. Report discovery failures as 503.

## Verification
Run isolated Python/Node regressions with network disabled. No playback or speaker mutation is needed. Backend changes require a normal restart when the owner chooses to activate them; this task does not restart the app.
