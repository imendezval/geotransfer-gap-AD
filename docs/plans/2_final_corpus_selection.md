# Prospective final-corpus selection v1

## Step1: composition before further planner outcomes

Problem: a larger collection can remain dominated by easy controls, duplicated
actors, one recording or the two existing interaction families. This document
and `pilot/audits/final_corpus_selection_v1.json` freeze the next selection
rules before new policy outcomes. Existing feasibility diagnostics are already
known; this is a prospective expansion protocol, not a claim of a blinded
initial pilot. Keep the original13-scene frozen baseline intact.

Completion standard for this planning step: machine-readable target counts,
source-derived stratum definitions, deterministic candidate order, source/track
independence and existing recording/location splits are recorded and hashed.
Targets are not claims of achieved coverage or statistical power.

The primary50-scene composition is20 pedestrian crossings,15 longitudinal
following tasks,5 cyclist crossings and10 uncontested controls (40/10 balance).
Pedestrian approach/ahead variants are one family; stopped/restarting/creeping
leaders are one family. Different labels do not manufacture diversity. All ten
existing genuine interactions remain eligible anchors. Five cyclist crossings
are a minimum for the final corpus; they are not a powered sample alone.

Location targets are15 at location1,10 at location3 and25 at location4, with a
hard floor of10 per included location. Location2 is not used to pad coverage
while applicable priority is unsupported. Seek at least15 recording clusters,
with at most4 selected windows per recording. Preserve location4 as held-out;
else recording%5==0 is validation and remaining recordings are adaptation.
No overlapping source windows or shared moving track IDs within a recording;
this includes moving context actors, not just the ego/claimed actor. Existing
accepted windows have selection precedence. Final inference must account for
recording/site clustering.

Maneuver targets: at least20 straight tasks,10 left turns and10 right turns;
the remaining10 may fill supported maneuvers. Source net heading change through
goal entry supplies an initial label (abs(change)<0.35rad straight, positive
left, negative right); manual route review distinguishes an intersection turn
from a curved through-road. Targets concern the reviewed task, not this proxy.

Traffic density is the maximum simultaneous number of other source-moving
actors within30m of the source ego, from step10 through first goal entry.
Source-moving means at least1m path within the window; require valid samples
at that instant. Low=0–3, medium=4–8, high>=9. Aim for10 low,30 medium,10 high,
with minimum5 low and5 high. Density is computed from source, never from a
planner rollout; a count is not proof of an interaction.

Candidates must retain91 samples at0.1s, source goal85/first entry>=75, full ego
coverage, source path>=5m and displacement>=4m. Keep all source actors and
physical boxes, native-verified maps, existing startup/runtime/input protocol,
manual semantic decisions and complete technical/SMART gates. Source task
screens are necessary search criteria, not admission. Rank source cohorts by
location then crossing-time gap rounded to1ms, decision midpoint distance from
step45, recording, ego, frame and actor. Visit distinct source tasks before
alternate phases; choose on source/fidelity evidence, never planner success.

If a target is unsupported, publish the shortfall and investigate additional
source cohorts or generic semantic representation. Do not silently replace
cyclists with more pedestrian scenes or convert controls into interactions.
Any amendment gets a new version, justification and timestamp before new
planner outcomes under that amendment. A controller/interface repair requires
versioning and refresh of affected admissions, not pooling old/new passes.

## Step2: establish the third family

Problem: source proximity and turning coordinate frames have previously made
parallel/sidewalk cyclists appear to cross the ego path. Even a genuine source
crossing can depend on priority meaning absent from SMART.

First inspect all previously source-positive bicycle pairs, retaining earlier
semantic/physical failures as evidence. Re-screen raw oriented source footprints
and timing. Exclude anchor moving-track conflicts, then freeze the queue before
expensive runs. Prefer source-supported cyclist crossings; if they fail, search
additional raw-source cohorts and inspect generic rule/geometry issues. Vehicle
conflicts are a possible additional family only after their applicable rules
are represented or source-proven irrelevant, never a label substitution.

Before model runs, require a moving cyclist's body corridor to cross the ego
body corridor at a nonparallel angle, a relevant encounter after warmup and
before source-goal completion, manual source/route/rule review, and a bounded
goal that does not end upstream of the encounter. Record crossing timing,
actor IDs, source response without unsupported causal attribution, and all
essential vehicle context. Mere proximity is insufficient. Priority/sign
obligations stay excluded if they govern the tested task and are unrepresented.

Completion standard for this run: at least3 independent cyclist-crossing
admissions across at least2 recording clusters, each passing current full
technical, manual and actual SMART-input gates, source/model actor-identity
checks and fresh single/batch reproduction. They must coexist independently
with the original13 anchors. Final corpus target remains at least5 cyclists.
If new defects appear, test generic repairs and refresh affected baselines;
keep searching other source tasks while investigating failures. Do not stop at
a failed batch or a missing-rule candidate. Stop only for an intervention-only
blocker that prevents all remaining work in this scope.
