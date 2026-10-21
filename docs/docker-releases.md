# Docker release channels

The tag-triggered publish workflow supports an explicit opt-in beta channel so a
feature branch can be evaluated without merging unfinished work into `main` or
replacing the stable `latest` image. This is publishing support, not hardware
qualification or deployment automation.

| Git tag | Allowed commit | Docker Hub tags |
| --- | --- | --- |
| `v1.2.3` | Tag commit must be an ancestor of `origin/main` | `v1.2.3`, `latest` |
| `v1.2.3-beta.1` | May be off main | **Only** `v1.2.3-beta.1` |

Use exactly `vMAJOR.MINOR.PATCH` or `vMAJOR.MINOR.PATCH-beta.N`. Version components
are nonnegative integers without leading zeroes; N starts at 1 without leading
zeroes. Other prereleases, build metadata, incomplete versions and tags longer
than Docker's 128-character limit fail before Docker login/build/push. Both
annotated and lightweight tags work. The checkout must match the tag commit.
The workflow still triggers only on `v*` tag pushes, not ordinary branch pushes.

## Future beta publication (separate authorization required)

1. Review the exact feature commit, isolated test results, CI and outstanding
   hardware limitations. Ensure that commit contains the updated workflow and
   `.github/scripts/docker_release.py`; older commits retain their old workflow.
2. Choose an unused version such as `v1.2.3-beta.1` and create/push that Git tag
   on the reviewed commit. **Pushing the tag publishes an image** using the
   existing `docker-hub` environment and Docker Hub credentials. Environment
   protection rules may require approval or restrict which refs can publish;
   this change does not alter them, permissions or credentials.
3. Verify the workflow succeeded and inspect its exact image tags and digest.
   There is no rolling `beta` alias and beta never publishes `latest`. Treat
   each beta version as immutable: never move/reuse its Git or Docker tag;
   increment N for another build. Docker tags are not inherently immutable:
   this workflow does not configure registry immutability or prevent reruns
   overwriting the same version. Record/pin the resulting digest for exact bytes.
4. Installation is a separate, explicitly approved operation. Select the full
   beta tag (prefer its digest), retain the previous known-good image/digest and
   back up configuration/favorites first. Existing `latest` installations do not
   opt in to beta. No automatic rollout or rollback is added here.

The beta exemption is narrow: a stable version off main still fails. Stable
publication preserves the existing version + `latest` behavior and main-ancestry
check. Publishing beta is not evidence of successful playback or NAS/radio
compatibility. Do not use a release tag merely to test this policy.

## Offline checks

Run `pytest -q tests/test_docker_release.py` or the normal `pytest -q` suite.
Tests create disposable local Git repositories only: stable/beta on/off main,
annotated/lightweight tags, ancestor commits, missing main, mismatched checkout,
malformed tags, exact outputs, fail-closed CLI writes and workflow wiring.
They never create remote tags, log in to a registry, build/push images, deploy,
or contact speakers. Real tag-triggered publication remains untested until a
separately approved release; absence of GitHub CI is not a passing CI result.
