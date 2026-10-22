# Spec Delta

## MODIFIED Requirements

### Requirement: Preview physical-button changes before writing
Wisp SHALL create a short-lived physical-button plan only from playable, preset-capable `STORED_MUSIC` content reported by the selected speaker. The plan SHALL identify the exact speaker, target slot, proposed content, and current six-slot map. It SHALL require separate explicit confirmation and SHALL expire on restart, identity change, timeout, or a competing preset-map change.

#### Scenario: User cancels a preview
- **WHEN** the confirmation is not sent
- **THEN** no preset command is issued and all six physical buttons remain untouched by Wisp

#### Scenario: Current map changed after preview
- **WHEN** any preset differs from the previewed map at confirmation time
- **THEN** Wisp rejects the write rather than overwriting concurrent changes

#### Scenario: Radio content is submitted for a preset plan
- **WHEN** a client submits a station identifier, radio URL, or non-`STORED_MUSIC` item as new physical-preset content
- **THEN** Wisp rejects the request before persisting an intent or sending a speaker command

#### Scenario: Existing speaker presets are inspected
- **WHEN** Wisp opens the native-preset workflow after this change
- **THEN** it reads the current six-slot map without clearing, rewriting, or migrating any existing assignment

