# Design

## Context

See [proposal.md](proposal.md) for motivation. The speaker overview currently derives a sanitized `services` list from the speaker's source observations in `app/core/favorites.py`, returns it beside `favorites`, `presets`, and supported NAS `sources`, and renders every entry uniformly in the Settings preset panel. The same raw source observations are still required to identify registered NAS libraries and whether the speaker reports Spotify, so source retrieval itself must remain.

The service summaries are informational only: no Wisp route browses, authenticates, or controls Alexa, Amazon Music, Spotify, TuneIn, QPlay, or generic UPnP services through this list. Bose's [SoundTouch end-of-life notice](https://www.bose.com/soundtouch-end-of-life) confirms that cloud support ended on May 6, 2026, music-service browsing and initiation from SoundTouch no longer function, and Alexa voice commands no longer work. It separately preserves Spotify Connect as a Spotify-app feature external to Wisp. The notice does not say that direct internet-radio streams are unavailable; Wisp radio fetches configured streams and relays them locally under its own ownership and safety contracts.

## Goals / Non-Goals

**Goals:**

- Replace the undifferentiated service signal with an allowlisted external-playback contract for Spotify Connect.
- Preserve native speaker-button assignments, Wisp favorites, and supported NAS library browsing.
- Preserve the station library, all three radio intents, scheduled radio, relay ownership, and stalled-relay recovery without changing their contracts.
- Preserve existing discovery freshness, identity validation, privacy filtering, and stale-view protection.

**Non-Goals:**

- Implementing the full SoundTouch API or adding control for third-party connected services.
- Initiating, authenticating, or controlling Spotify Connect from Wisp.
- Reassessing Wisp's existing local physical-preset workflow against Bose's separate end-of-life warning that presets are unsupported or not guaranteed.
- Changing speaker discovery, source retrieval, internet-radio streaming, playback ownership, volume safety, preset programming, or scheduling.
- Requiring live-speaker or audible-playback qualification for a presentation-only removal.

## Decisions

### Replace generic services with allowlisted external playback

The overview response will no longer include generic `services`. It will instead expose `external_playback`, initially containing only a speaker-reported `SPOTIFY` source mapped to `Spotify Connect`, its reported readiness, and guidance to start playback in the Spotify app. Alexa, Amazon Music, TuneIn, QPlay, and unknown source types will not be projected into this field.

Alternative considered: keep the generic field and relabel individual entries. Rejected because an open-ended list would continue presenting source observations as Wisp capabilities. Removing Spotify entirely was also rejected because Bose explicitly preserves Spotify Connect.

### Keep source observation and NAS filtering intact

The overview will continue reading the speaker's sources because the supported NAS-library list and Spotify Connect observation are derived from them. The generic summary helper will be replaced with a narrowly typed external-playback projection.

Alternative considered: stop reading all speaker sources. Rejected because that would remove the supported “Music connected to this speaker” workflow.

### Present Spotify Connect as external and non-actionable

The Connected services heading and generic renderer will be replaced with an External playback section. A reported Spotify source renders as “Spotify Connect” with guidance to use the Spotify app; it provides no Wisp playback button. The existing request gate continues to protect external playback, native presets, favorites, and NAS sources from obsolete speaker responses.

Alternative considered: retain Alexa and Amazon Music with “unsupported” labels. Rejected because non-actionable retired integrations add noise and still suggest that they belong to Wisp.

### Keep Wisp internet radio outside this change

The station library and radio playback paths do not consume the connected-service summary. Their templates, routes, station persistence, playback intents, relay ownership, volume gating, Stop behavior, scheduling, and recovery logic will not be edited. Focused regression checks will prove the Radio library entry point and radio tests remain intact.

Alternative considered: infer that Bose cloud retirement also retires Wisp radio. Rejected because the notice does not make that claim and the Wisp path uses independently configured stream URLs and local relay behavior already covered by separate specifications and evidence.

## Risks / Trade-offs

- [Existing API consumer expects `services`] → Treat this as an intentional response replacement, cover `services` absence and `external_playback` shape in the API contract test, and deploy API and UI together.
- [Speaker reports Spotify ready but external playback still fails] → Label readiness as speaker-reported, provide no Wisp action, and avoid claiming audible or authenticated playback.
- [Removing service rendering weakens stale-response coverage] → Keep the stale speaker-switch test focused on native presets, which remain observable and exercise the same request gate.
- [NAS libraries disappear accidentally with the service projection] → Add focused coverage proving supported NAS sources remain in the API response and Settings workflow.
- [Bose cloud retirement is applied to Wisp radio] → Add contract and regression assertions that the Radio library and existing radio workflows remain unchanged.

## Migration Plan

Deploy the API and static UI assets together. No persisted data migration, speaker command, restart-specific device action, or user configuration change is required. Rollback is the inverse code change and does not require restoring data.
