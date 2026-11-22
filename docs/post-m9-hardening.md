# Post-M9 operations

M9 at `4706b42a0d6ea5a97b3e149dd32ddfdaeebeb804` is historical evidence for 480 integration passes and 24 blocked US source-hold slots. The blocked slots cover both US scenes, all four ego controllers and IDM, PPO or SMART traffic using source hold. The separate US-only generation at `0beb7d84d6b61357d6bbfa7b28c83cb72e08f95c` subsequently obtained 24 exact single-versus-batch passes. A future 504-slot certification would use one frozen revision for every slot.

## Corpus workflows

- Use `geotransfer check all` for the full validation suite. It requires Linux Bubblewrap with usable mount namespaces. Subprocesses see a private copy at the configured artifact path, so historical absolute references still resolve and fixture writes land in the copy. Check reports are under the configured runs directory. Individual low-level validation commands still require an explicitly isolated artifact root when they write evidence.
- Run `geotransfer corpus build` without `--publish-current` to evaluate candidates and write a preview. When intentionally replacing the current corpus, review the proposed manifest and use `--publish-current --expected-current-sha256 <sha256>`. The expected value is the SHA-256 of the current manifest, or `absent` for a first publication.
- Use `geotransfer convert` and a dedicated output root. Conversion rejects incompatible or partial existing outputs and stages fresh files before publication. Reuse requires identical output content. inD samples must have consecutive source-frame IDs within each converted track window. Interpolation between adjacent frames remains supported.
- Resume candidate screening with the same selection and ledger. The ledger records interrupted and failed work and retries it. Reuse is tied to tool, source and output hashes. If changed inputs imply different conversion bytes, use a fresh output root for the new scene generation.

## Native goal evidence

New matrix attempts include `goal_evidence.json`. It reads the raw native goal reward component from the ego slot of the completed transition. The public `reached_goal` flag, native event, terminal reason and cause classification remain separate. The two historical Expert/Expert reproductions reached a native goal at transitions 79 → 80 and 81 → 82 while the public flag remained false. Historical episodes without the raw event retain unknown goal evidence. Frozen M9 reports and traces retain their recorded fields.

## US source-hold and archived playback

The two US references use the original WOMD JSON in the configured WOMD validation directory. Source bytes are pinned, the pinned upstream writer must reproduce the frozen binary, and the in-memory normalization accepts the upstream omission of velocity `z` only. The frozen hold policy then computes the releases from recorded future motion, separately from learned-model inputs.

```bash
geotransfer run --scene us_hybrid_1002fdc9826fc6d1 \
  --ego expert --traffic ppo --traffic-startup source_hold
geotransfer view --campaign /path/to/saved/campaign \
  --scene r12_e151_f12041 --ego ppo --traffic smart \
  --traffic-startup source_hold --output /path/to/playback.html
```

Campaign playback resolves saved attempts inside the relocated archive and checks recorded hashes. Scene assets still resolve through the configured corpus and dataset paths.

## Preservation limits found during remediation

The frozen M9 archive and its 960 accepted attempts matched their saved hashes. Seven live SMART admission JSONs diverged from the pinned manifest during the session. The full admitted legacy command stops on this mismatch. Keep the historical manifest pinned and recover exact originals or create a separately reviewed admission generation. The fresh diagnostic comparison on all 16 scenes matched action and state evidence with only the deliberately different `admission_required` field. Nine scenes with exact live admission evidence also matched the original raw hashes through the admitted command.

Fresh matrix workers now verify and reuse aliases after simultaneous creation. Direct callers of the legacy `session.short_alias()` still have the original race. Editing that producer would change both the scene-admission and SMART execution fingerprints.
