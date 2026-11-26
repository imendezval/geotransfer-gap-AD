# German Random100 and Interactive100 source-only queues v1

## Frozen artifacts and scope

The deterministic source-only selector is
`src/geotransfer_gap/corpus/freeze_random_interactive_v1.py`. Its identity,
movement and independence helpers are in
`src/geotransfer_gap/corpus/source_only_protocol.py`; focused selector tests are
in `tests/test_source_only_protocol.py`.

The generated, ignored artifacts are under `artifacts/german_200_v1/`:

- `queues.json` contains the two 100-row primary queues, source population
  ledger, ordered source-phase alternates, frozen 16-scene identity rows and
  selection rejections.
- `first_batch.json` contains the immutable first 24 primary rows for the
  separate bounded conversion and admission workstream.
- `provenance.json` binds the generator, helper, converter, all source
  catalogs/selectors/preflights and source file hashes to the queue and first
  batch bytes. `summary.json` records concise queue counts and artifact hashes.

Reproduce the selection in a separate directory and compare the frozen bytes.
The provenance sidecar was recorded alongside the original freeze.

```bash
selection_check=$(mktemp -d /tmp/geotransfer-german200-selection.XXXXXX)
.venv/bin/python -m geotransfer_gap.corpus.freeze_random_interactive_v1 \
  --output-dir "$selection_check"
cmp artifacts/german_200_v1/queues.json "$selection_check/queues.json"
cmp artifacts/german_200_v1/first_batch.json "$selection_check/first_batch.json"
```

Frozen byte identities are `queues.json` SHA-256
`33069002fe04000c0b6e35213f90a219554a1accba6c9bce8230bb990d779cba`,
`first_batch.json` SHA-256
`5af1c9ef57cb57adffbbf54a59cf74ab5181b2347c68ca4282121b9ed5a2c6a0`, and
`provenance.json` SHA-256
`496922f50e6aa36f3d37342a7092a60c8b872a4d016d6588cb0cd5e5ea5f558c`.

These queues define source candidates for later admission gates. Selection
reads no planner result, grants no research admission and infers no interaction
outcome. Every row retains `rule_applicability: pending_source_review`; the
location-2 rows remain annotated candidates while their applicable semantics
await source review.

## Source populations and randomization

The random arm uses the intersection of the existing stride-50 source catalogs
and matching oriented map-preflight rows. A window must have passed the source
motion, goal-timing and source-completeness screens, all sampled ego centers
inside the road/bus-lane map and a directed start-to-goal route. The complete
inclusive source interval is `first_frame` through `first_frame + 225`, with
91 evaluator samples spaced 2.5 source frames apart.

`Random100` samples equal-weight `(recording, ego_track_id)` units from a
sorted canonical population, then orders that unit's eligible source phases
using the fixed SHA-256 seed rank. This avoids giving an ego more raw draw
weight just because it has more eligible stride phases. The current population
has 2,966 recording/ego units and 5,934 eligible source windows.

`Interactive100` samples distinct `(recording, ego_track_id, actor_track_id)`
tasks, then orders exact source-positive phases for each task. The source
evidence union uses the established event, body, footprint, fine-phase,
restart, restart-turn and restart-velocity selectors. A selector row is
eligible only when its exact recording/ego/frame identity joins to a stride-50
source window that also passes the map preflight. The current union has 764
distinct source tasks. Family labels are derived from the selector's own
`task_evidence.kind` (with actor class as the family label fallback); raw
selector rows, source kinds, actor class and selector names remain attached to
each selected candidate.

The seed is `20261126`. Canonical unit populations are sorted numerically;
unit and phase order use SHA-256 over canonical JSON containing the protocol
version, seed, arm, selection stage and unit/window identity. Interactive tasks
are visited before random units so that the smaller established interaction
pool is selected before the random queue is conditioned on the chosen source
tracks. Equal-unit raw draw probabilities before constraints are 100/764 for
Interactive100 and 100/2,966 for Random100. The final inclusion probabilities
are constrained by source independence and are not claimed to equal those raw
values.

The v1 protocol has no per-recording cap. Split labels retain the existing
policy: location 4 is held out; other locations use recordings divisible by 5
for validation and all remaining recordings for adaptation. All locations 1,
2, 3 and 4 remain represented in the queues. The source-randomized selections
retain their resulting location proportions. The first batch uses a separate
frozen SHA-ranked round-robin to cover all four locations and the available
interaction family strata.

## Context actors and source independence

The selector reuses the movement rule in `sources/ind.py` through a matching
source-window reconstruction. It loads every supported source class in the
window, includes a track in converted context when it has at least two raw
rows and at least two valid evaluator samples, and marks it moving when the
trimmed raw source path is at least 1.0 m. `context_actor_ids` lists every
converted source actor, including stationary context and ego;
`moving_track_ids` lists the full moving subset. Catalog `nearest_actors`
remains a local-neighborhood summary; full actor scope comes from the
source-window reconstruction.

Each new primary must have no same-recording inclusive-window overlap and no
shared moving track with any of the frozen 16 anchors or any earlier new
primary. The independence check spans Interactive100 and Random100. All 200
frozen primary candidates pass this check against the 16 anchors and one
another. The frozen 16 identity rows and their moving IDs are included in the
queue so the check is reviewable.

The queue reconstructs exact actor identity and movement membership under the
converter definition for all 200 rows. It records 4,898 source actor instances
and 2,247 moving-track instances. Source visibility remains partial for some
actors: 1,275 actor instances, including 1,224 moving instances, have fewer
than 91 valid source samples because the source track begins or ends inside the
window. Their available source rows still determine membership and movement;
unobserved motion remains unknown.

For each selected unit, all other source phases are stored in the frozen
randomized order as alternates. An alternate can replace a primary only before
planner execution, only if the unchanged source/map/task checks still pass and
a fresh inclusive-window plus all-moving-track independence check passes
against retained primaries. Planner results never trigger replacement.

## Frozen first batch and current composition

The immutable first batch has 24 candidates: 12 per arm, 12 interaction
candidates across all three source families, and candidates from locations 1,
2, 3 and 4. Its family counts are 3 cyclist, 4 pedestrian and 5 longitudinal
following. The full selected queue has 100 unique tasks in each arm. Interactive
selection currently contains 33 cyclist, 47 pedestrian and 20 longitudinal
following tasks; its location counts are 10, 87, 2 and 1 for locations 1, 2,
3 and 4. Random selection has 26, 45, 8 and 21 rows for locations 1, 2, 3
and 4. The larger location-2 share reflects its source population size and is
preserved as a stratum requiring later semantic review.

Every selected row stores source task/maneuver fields and the catalog's nearby
actor counts with their 12 m scope. Full corridor density remains unavailable
from those counts. Each row also stores exact track, metadata, recording
metadata, background, Lanelet2 and OpenDRIVE SHA-256 values for the recording. The
separate provenance sidecar records SHA-256 values for the selector, helper,
converter, all catalog/selector/preflight inputs, queue and first batch. The
candidate rows have no planner-outcome fields; a boolean protocol marker states
that planner outcomes are absent.
