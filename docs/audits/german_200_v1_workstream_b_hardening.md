# German-200 v1 Workstream B hardening review

## Scope and outcome

This review covers the immutable 24-row first batch and four attempted same-arm/task alternates. The queue, ledger, candidate runs, fallback artifacts, admission reports, and production converter/runtime remain preserved. The compact machine-readable record, including pair-level physical metrics and evidence paths/hashes, is in [`candidate_taxonomy.json`](../../runs/german_200_v1_workstream_b_hardening/v1/candidate_taxonomy.json). Original runs remain under [`artifacts/german_200_v1_workstream_b`](../../artifacts/german_200_v1_workstream_b).

The primary outcomes remain 6 technical gate passes awaiting human review, 6 technical rejections, 3 review-blocked rows, 7 source-physical rejections, and 2 source-geometry rejections. Of four attempted alternates, two are source-physical rejections, one is a source-geometry rejection, and one is review-blocked. The human-review manifest has no reviewer actions, physical clearances, semantic findings, or research admissions. Technical passes await review before research admission.

The failure taxonomy assigns no row to “semantic-rule unsupported.” Saved rule audits carry `evidence_only` status, and their flags are reviewer prompts. Technical failure reports give the causes for the rejection rows. The location-2 pedestrian case at r22/e187 has a technical lifecycle failure alongside a reviewable parked-box overlap. Its status is technical rejection, separate from the three `review_blocked` primaries.

## Per-scene failure taxonomy

| Candidate | Recording / ego / frame, task actor | Saved outcome and precise reason | Gate stage |
|---|---|---|---|
| `Random100-0-ed3193d495c0` | r17 / e290 / f19941, random | Technical rejection: actor 291 is removed offroad on source-valid birth step 3 (`collision_state=2`, no collided actor). Dynamics and IDM birth checks fail. | Native spawn/lifecycle diagnosis |
| `Random100-1-5a28ea459305` | r14 / e232 / f15437, random | Technical pass with source/rule review pending. | Human review |
| `Random100-2-c3394652267d` | r12 / e30 / f2957, random | Technical pass with source/rule review pending. | Human review |
| `Random100-3-c25194f5ec78` | r19 / e318 / f22291, random | Source-physical rejection: 13 ego-box contacts with curbstone edges 100101/100271 beginning at step 55. | Source physical screen |
| `Random100-4-03d7c2db37de` | r18 / e361 / f23857, random | Review-blocked: static pairs 15–16 and 16–17 need physical clearance. | Human physical review, then semantic/source review |
| `Random100-5-adca7f68d071` | r23 / e422 / f21646, random | Source-physical rejection: moving actor 420 overlaps parked actor 28. The pair is marked unreviewable. | Source physical screen |
| `Random100-6-93825a093a19` | r31 / e11 / f244, random | Source-physical rejection: moving pair 0–8 has 0.462 m maximum penetration and is unreviewable. Three other parked pairs are reviewable. | Source physical screen |
| `Random100-7-947545952a10` | r31 / e235 / f14719, random | Technical rejection: actor 236 is removed offroad at step 54 in IDM/hybrid. Expert replay passes. | IDM/hybrid lifecycle diagnosis |
| `Random100-8-6be6bc5d7aec` | r31 / e202 / f12623, random | Technical rejection: all four counterfactual modes terminate the ego offroad at step 1 despite source center samples inside lanelets, reachable route, and no source ego-boundary contacts. | Native/map discrepancy reproduction |
| `Random100-9-357e0fd2356b` | r04 / e101 / f8897, random | Technical rejection: actor 108 is removed offroad at step 1. Actor 109 is removed offroad on its source-valid birth at step 10. The source audit records curb contacts for both. | Native background lifecycle/spawn diagnosis |
| `Random100-10-b80e615825be` | r01 / e12 / f590, random | Technical rejection: actor 13 is removed offroad on birth step 7. Actor 16’s birth at step 83 follows the ego goal terminal at step 77, so the gate did not test it. | Native background lifecycle/spawn diagnosis |
| `Random100-11-104d04eadf1e` | r05 / e260 / f21256, random | Source-geometry rejection: occupied start-goal route unreachable. Separately, ego has 21 curbstone contacts from step 70. | Source geometry/physical screen |
| `Interactive100-12-6d1c4400b0a2` | r14 / e310 / f20146, cyclist crossing, actor 308 | Technical pass with source/rule review pending. | Human review |
| `Interactive100-13-064b40df776b` | r08 / e93 / f6029, pedestrian crossing, actor 95 | Technical pass with source/rule review pending. | Human review |
| `Interactive100-14-2cb0814b0b63` | r16 / e388 / f25377, longitudinal, actor 385 | Source-physical rejection: pair 6–381 is unreviewable. | Source physical screen |
| `Interactive100-15-dd4ddf99b83e` | r18 / e251 / f15941, cyclist crossing, actor 249 | Review-blocked: static pairs 15–16 and 16–17 need physical clearance. | Human physical review, then semantic/source review |
| `Interactive100-16-01096bb714f4` | r22 / e187 / f9126, pedestrian crossing, actor 184 | Technical rejection: source-valid background vehicles 191 and 193 are removed in collisions at step 49. Parked pair 18–19 is separately reviewable. | Hybrid lifecycle diagnosis |
| `Interactive100-17-9b6dcd25e54c` | r29 / e203 / f9718, longitudinal, actor 200 | Review-blocked: static pairs 14–15 and 28–29 need physical adjudication. Actor 200 also has three low-road-border contacts at steps 13–15, recorded separately. | Human physical review, then semantic/source review |
| `Interactive100-18-5fcd6bbc0e93` | r32 / e74 / f3605, longitudinal, actor 72 | Source-physical rejection: stationary pairs 7–8 and 9–10 are marked unreviewable near the ego route. | Source physical screen |
| `Interactive100-19-7578dcf4eef9` | r01 / e114 / f7561, longitudinal, actor 113 | Technical pass with source/rule review pending. | Human review |
| `Interactive100-20-b944318377cf` | r13 / e290 / f20235, longitudinal, actor 289 | Technical pass with source/rule review pending. | Human review |
| `Interactive100-21-d0d1690740f0` | r28 / e105 / f5317, cyclist crossing, actor 106 | Source-geometry rejection: occupied start lanelet 1177 cannot reach goal lanelet 1088 through supported successors. Three parked pairs are reviewable and leave the geometry result unchanged. | Source geometry screen |
| `Interactive100-22-648c4d318e8e` | r18 / e310 / f20699, pedestrian crossing, actor 313 | Source-physical rejection: ego 310 overlaps moving actor 321 by 0.600 m (minimum ego-box gap 0). This pair is unreviewable. | Source physical screen |
| `Interactive100-23-28aa616c026d` | r28 / e449 / f26008, pedestrian crossing, actor 448 | Source-physical rejection: parked pair 17–137 is unreviewable near the ego (0.029 m overlap, 1.595 m ego gap). Three other stationary pairs are recorded separately. | Source physical screen |
| `fallback_003_01_00307595e507` | r19 / e318 / f21991, Random100 alternate for q3 | Source-physical rejection: unreviewable near-ego pair 11–12 and moving actor 321 overlaps parked actors 12 and 13. | Fallback source physical screen |
| `fallback_005_01_f2d2e1df3f55` | r23 / e422 / f21696, Random100 alternate for q5 | Source-geometry rejection: route unreachable. Pair 17–18 is also an unreviewable near-ego overlap. | Fallback source geometry/physical screen |
| `fallback_021_01_021753457336` | r28 / e105 / f5267, Interactive100 alternate for q21, cyclist actor 106 | Review-blocked: three stationary pairs 8–9, 20–21, and 21–22 need physical clearance. | Human physical review, then semantic/source review |
| `fallback_023_01_df381437c41c` | r28 / e449 / f25958, Interactive100 alternate for q23, pedestrian actor 448 | Source-physical rejection: three parked pairs 17–137, 19–240, and 21–22 are unreviewable near the ego. | Fallback source physical screen |

Pair metrics, boundary contacts, gate checks, rule-annotation flags, evidence paths, and SHA-256 digests appear in the linked machine-readable taxonomy. It preserves physical evidence alongside geometry and technical outcomes.

## Location 2: nine primary windows

The location-2 map audits agree across the nine conversions: 103 lanelets, 106 emitted successors with shared boundary IDs, all ego center samples inside lanelets, and zero unsupported heuristic successors. The recorded failures are localized: one route is unreachable, one ego box touches curbs, several box overlaps occur in the source, and one technical gate fails on hybrid background collisions. These map-wide counts support no shared converter defect.

- Random r19/e318/f22291: route is reachable, but ego 318 contacts curbstone edges 100101 and 100271 for 13 recorded edge contacts starting at step 55. Pair 11–12 is a separate reviewable stationary overlap with 0.091 m penetration and 11.819 m ego gap. Source-physical rejection.
- Random r18/e361/f23857: two reviewable stationary pairs overlap over all 91 samples. Pair 15–16 reaches 0.0011 m penetration with 4.925 m ego gap. Pair 16–17 reaches 0.1392 m with 4.688 m gap. The technical gate awaits human adjudication.
- Random r23/e422/f21646: pairs 14–30 and 17–18 are stationary and reviewable. Pair 28–420 is an unreviewable moving/static overlap with 0.0047 m penetration and 2.713 m ego gap. Source-physical rejection.
- Interactive r18/e251/f15941, cyclist actor 249: same stationary pairs 15–16 and 16–17 recur, with 30.057 m and 32.926 m ego gaps. Both need human physical adjudication. The Random100 window supplies no clearance for this candidate.
- Interactive r22/e187/f9126, pedestrian actor 184: parked pair 18–19 is reviewable at 0.143 m penetration and 30.354 m ego gap. Hybrid lifecycle separately removes background vehicles 191 and 193 in collisions at step 49. The saved outcome is technical rejection.
- Interactive r29/e203/f9718, longitudinal actor 200: review-blocked on stationary pairs 14–15 (0.092 m penetration, 16.704 m gap) and 28–29 (0.156 m penetration, 43.579 m gap). Actor 200 separately touches low road-border edge 100014 at steps 13–15.
- Interactive r28/e105/f5317, cyclist actor 106: the source start lanelet 1177 cannot reach goal lanelet 1088 through supported successors. Center samples remain inside lanelets. Three separate stationary pairs are reviewable. The f5267 alternate has its own review-blocked status and three stationary overlaps.
- Interactive r18/e310/f20699, pedestrian actor 313: unreviewable dynamic source overlap between ego 310 and moving actor 321 with 0.600 m penetration and zero ego gap. Parked pairs 15–16 and 16–17 are separate reviewable overlaps.
- Interactive r28/e449/f26008, pedestrian actor 448: near-ego stationary pair 17–137 is unreviewable with 0.029 m penetration and 1.595 m ego gap. Pairs 8–9, 19–240, and 21–22 are separately recorded as reviewable.

Parked tracks 15–16 and 16–17 show the same overlap penetrations in separate windows of recording r18 (q4, q15, and q22). A reviewer can assess whether a site-static annotation finding applies to each window after checking its source geometry. Each candidate remains independently pending. The pattern supports no collision-tolerance change or converter edit.

## Systematicity, repair candidates, and gate stage

- **Source geometry:** the r28/e105 primary and r05/e260 Random100 primary have unreachable occupied start-goal paths. Location 2 retains supported successor geometry and in-lanelet ego centers elsewhere. These window/route outcomes give no evidence of a location-wide geometry defect.
- **Source physical:** location-2 parked-pair overlaps recur at one site. Other cases involve ego-curb contact, moving/static overlap, ego/moving-actor overlap, or near-route static pairs. The source screen runs before the technical gate, and each physical cause remains distinct.
- **Runtime/lifecycle:** three technical rows show source-valid background births removed offroad (actors 291, 109, and 13). Other rows show IDM/hybrid offroad removal (236), a step-1 ego offroad terminal state (r31/e202), and hybrid collisions (191 and 193). These symptoms have no established common mechanism. The q8 saved counterfactual report reproduces the step-1 terminal across all four modes while source geometry and ego-boundary screens pass. A scoped replay of the exact scene/map and native road-edge clearance is required before proposing a shared repair.
- **Possible generic repair:** this evidence supports no production change. A human may document a pair-specific site-static overlap finding for recurring parked actors with exact source/map references and overlap metrics. Each affected candidate still requires its own review. Runtime changes require reproduction of the exact actor/ego transition.
- **Gate stage:** source geometry and physical rejection occur before technical admission. Technical lifecycle failures require technical diagnosis before semantic review. Review-blocked candidates require physical adjudication first. Six technical passes await human source/rule review. Technical pass status alone does not grant research admission.
- **Per-candidate systematicity and generic-repairability fields** appear in `candidate_taxonomy.json`. They separate repeated symptoms from proven shared causes. The saved evidence supports no shared converter/runtime patch.

## Phase sensitivity: tested temporal windows

Gate stage above identifies the pipeline step. Phase sensitivity below records source-window shifts for four executed parent/alternate pairs with the same recording, ego, and task identity.

| Pair | Source-window shift | Observed outcome change | Limit |
|---|---:|---|---|
| Random100 q3, r19/e318: 22291–22516 → 21991–22216 | −300 frames (−12 s) | Both windows are source-physical rejects. The primary has ego-curb contacts and separate pair 11–12. The alternate has pair 11–12 and moving/static overlaps with actor 321. | These two windows show different physical evidence. They support no temporal trend or repair inference. |
| Random100 q5, r23/e422: 21646–21871 → 21696–21921 | +50 frames (+2 s) | The primary rejects on moving/static pair 28–420. The alternate rejects on an unreachable route and has a separate pair 17–18 overlap. | The change is window-specific. |
| Interactive100 q21, r28/e105: 5317–5542 → 5267–5492 | −50 frames (−2 s) | The primary route is unreachable. The alternate route is reachable and blocked for stationary pairs 8–9, 20–21, and 21–22. | The alternate is a separate window and leaves the primary result unchanged. |
| Interactive100 q23, r28/e449: 26008–26233 → 25958–26183 | −50 frames (−2 s) | Both windows are physical rejects. The alternate has three near-ego pairs (17–137, 19–240, 21–22). The primary has pair 17–137. | The pair counts provide no shared repair signal. |

The second frozen alternates for q3 (22241–22466) and q5 (21596–21821) were unattempted under the one-alternate cap. Structural primaries q6, q11, q14, q18, and q22 had no eligible prespecified alternate. Those windows remain untested. Phase-sensitive inference is bounded to the four listed comparisons.

## Human review index

The ten review dossiers and a short checklist are in the ignored, versioned package: [`human_review_index.md`](../../runs/german_200_v1_workstream_b_hardening/v1/human_review_index.md). It contains the six technical passes, three blocked primary overlaps, and the one blocked fallback overlap. Each dossier provides recording, ego, frame, task/actors, exact rule-applicability flags, technical result, pair-level physical evidence when relevant, two saved review images, evidence links/hashes, and blank reviewer fields. All remain pending.

The dossiers point to the repository’s hash-bound next-stage review formats. `physical_overlap_review.json` schema 1 binds physical-audit, binary, registered source-image, and pair-level `source_steps`/evidence hashes. `semantic_review_hybrid_startup.json` schema 2 records later source/rule review for a technically eligible scene. Validation lives in [`admit_scene.py`](../../src/geotransfer_gap/validation/admit_scene.py). A physical conflict or unresolved pair remains rejected or deferred and non-admitted. The current physical gate accepts only a human-supported minor stationary annotation overlap.

The original human-review manifest records `manual_reviews_created: false`:  [`human_review_manifest.json`](../../artifacts/german_200_v1_workstream_b/human_review_manifest.json). No semantic findings were invented or entered.
