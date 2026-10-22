# Tasks

## 1. Exact CHOM relay compatibility

- [x] 1.1 Add literal legacy-AAC and stable-MP3 CHOM constants at the relay URL-selection boundary, map only the exact legacy URL, and verify focused relay tests cover the legacy alias, direct saved MP3 pass-through, edited/query/case variant preservation, and unchanged volume/ownership preparation behavior.
- [x] 1.2 Keep `radio_stream.CANDIDATES` unchanged and add focused coverage proving neither CHOM HTTPS form is advertised by direct speaker diagnostics; verify existing Star, Buzz, and CBC candidates remain unchanged.

## 2. New-install station seed

- [x] 2.1 Replace only the CHOM starter URL with the stable HTTPS MP3 dispatcher while retaining seed version 1, and verify seed tests assert the exact CHOM value plus unchanged Star, Buzz, CBC Montréal, Énergie, and ICI names and URLs.
- [x] 2.2 Extend persistence coverage for populated, renamed, favorited, scheduled, archived, and deleted station records, and verify seeding never rewrites IDs, saved URLs, links, or user choices.

## 3. Validation and review artifact

- [x] 3.1 Run focused radio-relay, direct-radio, radio-stream, and favorites tests in an isolated environment with no speaker access, then run the full test suite and record exact pass/fail evidence.
- [x] 3.2 Run strict OpenSpec validation, inspect the final diff for unrelated baseline/runtime files, and produce an immutable patch containing only this change's OpenSpec artifacts, implementation, seed, and tests for independent review.

## Workflow follow-up

- Archive the change only after independent review and approval.
- Perform separate supervised real-speaker qualification before claiming audible CHOM playback.
