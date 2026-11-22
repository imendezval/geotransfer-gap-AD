# Final-corpus composition and third-family execution

## Standards fixed before new runs

Step1: freeze the prospective50-scene composition, interaction/control balance,
location/recording/maneuver/density targets, source-only definitions and existing
splits. Retain the13-scene baseline unchanged and bind the selection document
and baseline manifest/freeze by SHA256. No outcome-based scene selection.

Step2: establish at least3 independent cyclist-crossing admissions across2 or
more recording clusters, coexisting with all13 anchors. Apply current source,
physical, semantic, expert/lifecycle, essential-context and actual SMART input
gates. Manually inspect provider imagery. Verify fresh single/batch identity
and timeline parity. A source-positive pair, technical pass or visible cyclist
alone is insufficient. Investigate failures generically and keep searching;
no admission tolerance relaxation or scene-specific actor removal.

## Step1 outcome

`2_final_corpus_selection.md` and
`pilot/audits/final_corpus_selection_v1.json` freeze20 pedestrian,15 following,
5 cyclist and10 control targets, locations1/3/4,15 recording clusters sought,
maximum4 scenes per recording, reviewed maneuver targets and source density
strata. Existing recording/location splits persist. These are prespecified
expansion targets, not achieved counts or a power claim. Source-only inspection
of the existing13 anchors informed density definitions before any new rollout.
The composition-planning step is complete.

## Step2 initial experiment

`select_third_family.py` merges earlier body/fine-phase/centreline source-positive
bicycle pairs and re-evaluates raw source footprints with current source rules.
It excludes known anchor ego/claimed-actor conflicts, binds source CSV hashes,
and fixes timing-based order before model outcomes. Other context-track
conflicts are checked after conversion before corpus admission. The existing
progressive queue performs cheap geometry/rule checks, then physical/full
technical checks, visiting distinct tasks before alternate phases. It never
grants research admission. Prior unsupported candidates remain in the ledger;
a phase shift cannot automatically waive the same governing rule.

The first source catalog produced378 eligible windows/246 tasks; after156
progressive attempts, most failures concern genuinely unrepresented applicable
priority. The r07/e200 cyclist emergence passes source/manual/SMART admission.
Its straight main-road route has no direction-compatible entry to the mapped
yielding side-arm connectors; cyclist190 crosses/turns into the ego corridor.
This is a collision-avoidance encounter, not cyclist-precedence compliance.

A diagnostic native directed-route certificate identifies a generic polygon
association defect: a main-road source point can lie in a curved side-arm yield
polygon. Certification requires a connected native successor path covering
all91 source samples within0.35rad, traversal of the same relation's protected
lane, and zero direction-compatible source samples in its yielding lanes.
Actual yielding or an incomplete directed route prevents certification. Tests
on genuinely yielding r08/e20, r14/e58 and unsupported r20/e416 refuse to clear
their obligations. The certificate is not yet an admission waiver.

The older stride catalogs contain few straight-road cyclist emergence tasks.
Before more model outcomes, open a generic event-centred cohort across all33
recordings: synchronized source pair distance<=12m at5-source-frame samples;
centre the9s window at step45 of the nearest event and use uniform source-frame
offsets -50/-25/0/25/50. Retain all existing coverage/motion/body-crossing/goal
standards. Prioritize source-straight tasks within location strata. The new
source-only catalog contains921 positive windows/351 tasks, including previously
unsearched straight candidates in recordings1/15/17. No planner performance is
read by either selector. Distinct tasks with an already faithful source window
are not repeated merely for a different planner outcome.

Two independent cyclist scenes now pass manual/SMART admission: recording7,
ego200/frame25439 with cyclist190, and recording9,ego136/frame11030 with
cyclist133. The latter's source-selected earlier phase passes the prescribed
initial ego perturbation; its later phase does not. The recorded source route
and actual applicable rules are unchanged. The directional-rule certificate is
now optional admission evidence requiring explicit rule IDs and proof SHA256.
Five source regression fixtures preserve real yield/stop exclusions, and the
SMART gate adds missing/stale/uncertified-certificate rejection cases. A helper
recording-state bug discovered during cross-map tests was fixed by setting the
recording explicitly and checking map hashes; no construction-map proof may be
computed against the non-construction map. Older gates are archived pending
current refresh, never pooled.

The event-centred five-frame refinement gives4982 source-positive windows/394
tasks. Most are genuine unsupported-priority tasks, physical/map rejects, or
false candidate crossings requiring manual rejection. The supported r02/e40
bike32 task is not an interaction admission: its minimum source box gap exceeds
5m and it has zero source-close frames, even if background traffic is repaired.
The threshold is not relaxed.

The r01/e280/frame18833 scene exposes two general issues: its endpoint is legally
reachable in native Germany/Vehicle routing with lane changes, but the old
source audit only searches following edges; and background281's native route
collides with expert cyclist279. An isolated logged-background-route test on
runtimea50f3d9ee6c71955 preserves279, removes no background actors and passes
the full expert/hybrid ego perturbation. Its controller excludes the ego from
source route intent. Source-speed guidance alone fails the perturbation; it is
not promoted. Before any route-intent promotion, test all13 anchors and both new
cyclist fixtures for nominal lifecycle, source encounter fidelity and perturbed
lifecycle, then apply the same interface/runtime proof in both US references.
Any promoted runtime/controller gets fresh technical/model/admission/batch
proofs for every retained scene.

A dashed-boundary lane-change permission prototype is diagnostic only. Native
routing has a legal1085→1047 route for r01/e280 when lane changes are enabled.
Native traffic rules confirm that some direct shared-boundary changes are legal
even where the routing graph uses intermediate overlapping lanelets. Preserve
that distinction; do not insert lateral changes as IDM following successors.
A production source-route repair must retain native permission evidence and
manual source boundary review, without making a solid/opposing crossing legal.


The unrestricted logged-route, speed-guided, selective-disagreement and branch
ranking variants fail retained fixtures and remain diagnostic. A progress-
covered route prior passes all16 source/perturbation fixtures: at each route
build, retain native routing when any of the next11 valid source speeds is
below1m/s; otherwise use the contiguous logged path only if its length covers
max(current speed,native desired speed) times the remaining observed duration.
Native IDM keeps speed/brake/control limits; the ego is explicitly excluded.
The production runtime is nowbeedf8f1b0e9c490, traffic version
startup_sustained_departure_route_coverage_v2. Old reports are archived and all
affected technical/input/admission/rollout evidence is being refreshed.

Native Germany/Vehicle validation confirms102 conservative unambiguous dashed
lateral edges on five maps, with no extra/forbidden routing edges. They are
source permissions only, never IDM following successors. Dense0.01s centre/
direction checking proves the actual r01/e280 route uses legal1044→1043 across
dashed100059 at68.6; it is not merely an existential start/goal connection.

The candidate exposed a further real input defect: upstream SMART treats a
long sparse crosswalk edge as a missing-data gap, dropping1160 to a dummy type0
token. A uniform US/German preprocessing step now samples consecutive crosswalk
edges at <=2m before the unchanged tokenizer. It preserves original corners
and geometry and adds no closing edge or new feature class. This is separately
versioned as crosswalk_edge_sampling_max2m_v1 / planner protocolv3; all actual
model-input and single/batch evidence must be refreshed. No extra semantic
meaning is attributed to generic lane tokens: the third task's late source
lane change is native-permitted, while lane-rule compliance and SMART goal/
route-choice failures remain outside the claimed crossing response scope.

## Verified outcome of the two requested steps

**Step1 complete.** The prospective composition remains50=20 pedestrian+15
following+5 cyclist+10 controls, with location targets15/10/25,15 recording
clusters sought, maximum4 scenes per recording, fixed source-only strata and
unchanged recording/location splits. Active selectionv3 records the fidelity
amendments; the original composition and its hashes are preserved. This is a
planning target, not achieved coverage or a power claim.

**Step2 complete in the stated SMART interaction scope.** Three independently
admitted cyclist examples coexist with all13 original source anchors:

| Recording / ego / first frame | Cyclist | Source task |
| --- | --- | --- |
|7 /200 /25439 |190 | Cyclist emergence/crossing into the main-road corridor |
|9 /136 /11030 |133 | Cyclist crossing the main-road ego corridor |
|1 /280 /18833 |279 | Continuous cyclist crossing after source ego passage |

These cover three recording clusters and two locations. The last is explicitly
not a mandatory yielding/braking example. Its permitted source lane change is
later than the primary crossing interval; source route legality does not imply
SMART receives dashed-versus-solid semantics or navigation-goal conditioning.
Those interpretation limits remain explicit, rather than being presented as
new checkpoint capabilities.

The combined corpus has16 independent admissions: six pedestrian encounters,
four following tasks, three cyclist crossings and three controls, across three
locations/ten recording clusters. All original13 binaries remain. Seventeen
per-scene research passes yield16 selected scenes after one moving-track
independence exclusion. The current audit includes20 candidate decisions and
retains the original pilot's counterfactual failure and location2 rule exclusions.

All16 canonical single-scene timelines reproduce exactly in fresh batch
subprocesses under runtimebeedf8f1b0e9c490, traffic route-coveragev2 and SMART
full-map protocolv4. The input/physical/admission/batch evidence was refreshed
under one protocol; old/new results are not pooled. Thirty-four SMART rejection/
restoration regressions pass. The independent native lateral oracle verifies
102 conservative edges on five maps. The seven-map US/German normalization
audit checks1,832 supported polylines, restores116 representable objects and
retains ten <=0.5m intrinsic-resolution omissions in the diagnostic references.
No supplied polyline geometry or original vertex is changed; no closing edge
or feature class is invented. Actual US model/source-state and execution checks
pass, including nonzero ego identities and unchanged ego route construction.

The historical flow contains814 retained ledger rows over695 distinct source
windows, with versions and source catalogs kept separately. Older runners
consolidated some same-window actor assessments, so this is not an exhaustive
actor-pair attempt denominator. The queue now preserves pair/version records
and serializes shared-scene mutations across threads/processes. A real dual-
actor/two-version/resume regression retains four records without change on
resume. Historical failures are not a pooled current rejection rate.

Full Step2 remains incomplete at16/50. The remaining target shortfalls are14
pedestrian,11 following,2 cyclist and7 control scenes, with further recording,
location/density/maneuver balance and sample-size justification. Full physical/
human-response faithfulness is not established: expert VRUs, imputed dimensions,
annotation exceptions, map quantization, source visibility limits, the logged
traffic prior and unobserved route intent remain limitations. No geographic
planner-performance or PPO-admission claim is made.


Final pipeline checks also confirm US ego indices74/12 retain exactly the native
ego route, while the covered fast background route changes and the short bus
route remains native. The current map audit's ten intrinsic short omissions
are four in excluded location2 and six in one US diagnostic map; none is a
standalone omission in the admitted German map variants. Codebook/short-tail
quantization remains a general limit. The persisted US reference producer can
refresh or hash-validate existing proofs, and the queue regression now preserves
pair/version records under scene locks. Current reproduction commands require
no unrecorded session patch.
