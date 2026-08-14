# Production API Historical Data Migration

Date: 2026-08-13; status refreshed 2026-08-14
Source: Frappe 15 `mrp3.site` / `production_api`
Target: Frappe 16 `essdee_yrp.site` / `yrp` + `essdee_yrp`
Status: Complete rehearsal passed on its frozen snapshot; current source has one new Goods Received Note schema blocker; live writes not started

Current concise handoff: `docs/MRP_BRANCH_HANDOFF.md`. This file retains the
detailed migration evidence. If an older execution statement conflicts with
the handoff or current code, rerun the planner and use the current result.

## Current execution evidence (2026-08-13)

- Source business backup completed; target full backup completed.
- Schema plan: 260 source schemas, zero blockers.
- Full read-only document dry run: 3,437,046 / 3,437,046 parent records,
  zero transformation failures.
- Supporting external master rehearsal covers missing Address, User, Role,
  Letter Head, Email Account, and Print Format identities without overwriting
  target identities that already exist.
- Original attachment inventory: 1,002 File records, 844 unique content hashes,
  526,862,642 metadata bytes. The database-only local restore has 999 absent
  originals; the other three physical originals fail their stored MD5 hashes.
  No remote storage hook or same-hash local recovery copy was found. The owner
  states the production cutover source will include the actual public/private
  file archives; production must prove both existence and hash/size integrity
  with file-health preflight rather than assuming it.
- Attachment transport smoke test (2026-08-14): two controlled Product Image
  samples, one public and one private, passed source disk read, base64 transport,
  target File insertion, identity/metadata/privacy checks, byte-size and MD5
  checks, physical target read, direct Attach Image repair, and an idempotent
  second run. The local inventory is therefore 1,004 rows / 846 unique contents;
  only the two controlled samples are byte-valid. The local rehearsal audits
  the 1,002 unavailable originals without weakening production's strict gate.
  Public sample File `e7238db485` and private sample File `54482b72ce` remain
  available for an isolated rerun through
  `essdee_yrp.migration.live.run_attachment_smoke_test`.
- Complete 2026-08-14 local rehearsal result: 3,437,048 documents processed,
  zero failures, 240,390 required values preserved/derived, 1,524 external Link
  values validated, all 1,004 File metadata rows and 846 content keys accounted
  for, and 171 source `tabSeries` counters validated. The live merge preserves
  source document/child identities through SQL and advances each target naming
  counter with `GREATEST(target, source)` only.
- Live database writes have not started. `mrp3.site` remains out of maintenance
  mode and `essdee_yrp.site` business data remains unchanged.

## Execution contract

This is one generic migration engine, not one script per DocType and not a
direct database copy.

- Identity DocTypes use the generic parent/child transformer.
- Renamed fields and DocTypes use declarative rules.
- A custom transformer is required only when the target meaning or structure
  genuinely differs.
- Names, child identities, owners, timestamps, docstatus, amendment references,
  and links are preserved where the target contract supports them.
- Content-hash checkpoints make a stopped run resumable and reprocess a source
  document only when its content changes.
- Any unknown source field, incompatible Link target, missing transformer, or
  unresolved dependency blocks the run before writes.

## Implemented migration safety

`essdee_yrp/migration/engine.py` provides:

1. Schema-to-schema planning and identity/mapped/custom classification.
2. Recursive parent/child transformation.
3. Renamed DocType, field, Dynamic Link controller, and child parent-metadata
   handling.
4. Registered whole-document and field-value transformers.
5. Dependency ordering with safe grouping of cyclic Link graphs.
6. SHA-256 checkpoints and delta/resume detection.
7. A hard dry-run path that never calls the target adapter.
8. In-memory adapters for focused transformation tests.

`essdee_yrp/migration/live.py` and `scripts/f15_source_bridge.py` provide the
fixed-source F15 read bridge, F16 database-level bulk target adapter,
supporting-master handling, Single handling, password transport, attachment
transport/preflight, stock-summary checks, naming-series merge, queued jobs,
and verification.

`scripts/mrp_data_migration.py` intentionally remains a filesystem-only schema
planner. It reads repository DocType JSON, Essdee fixtures, Property Setters,
and the code-declared dimension profile; it does not connect to a site. Its
read-only scope must not be mistaken for the scope of the live runner.

`MRP Data Migration` is the Essdee-owned trigger and audit DocType. Each record
stores the fixed source/target identity, schema totals, one child audit row per
source DocType, dependency group, mapping JSON, blockers, checkpoints, counts,
and errors. Only System Manager can access it. Direct API/form mutation of an
existing audit record is rejected; its server actions own all state changes.
Analyse, Dry Run, Migrate, and Verify are implemented as server-owned actions.
Dry Run/Migrate/Verify enqueue reviewed jobs, enforce the previous successful
state, require zero schema blockers, and remain System Manager-only.

## Current schema-only result — 2026-08-14

| Result | Count |
|---|---:|
| Source DocTypes | 260 |
| Target DocTypes | 318 |
| Generic identity | 225 |
| Declaratively mapped | 32 |
| Custom | 3 |
| Explicit blockers | 1 |

The prior 22 mapping blockers were reviewed and resolved through declarative or
custom rules. The current blocker was introduced later by F15 commit
`bdc8aa93`, which added the closed-work-order sewing GRN flow:

```text
Goods Received Note: from_closed_wo_sewing_details:
target field 'from_closed_wo_sewing_details' does not exist
```

Review the new F15 field, server controller, sewing page, and tests. Resolve it
as schema + mapping + behavior; do not add it to an ignore list merely to make
the planner ready.

## Rehearsal result on the earlier zero-blocker snapshot

- Full read-only document pass: 3,437,048 records, zero failures.
- Required values preserved/derived: 240,390.
- External Link values validated: 1,524.
- File inventory: 1,004 rows / 846 content keys.
- Source naming-series counters validated: 171.
- Supporting masters and controlled public/private attachment transport were
  rehearsed.
- No live historical target writes were started.

The source schema changed after this result. Repeat Analyse and Dry Run after
resolving the current blocker; do not reuse the previous Ready state as current
approval.

## Useful commands

```bash
/home/anas/frappe-16/env/bin/python -m unittest \
  essdee_yrp.migration.test_engine \
  essdee_yrp.migration.test_schema \
  essdee_yrp.migration.test_planner \
  essdee_yrp.migration.test_transformers -v

/home/anas/frappe-16/env/bin/python scripts/mrp_data_migration.py --summary
```

Run Frappe-bound tests through the named site rather than bare unittest because
`frappe.db` must be bound to a site context. The schema command intentionally
exits `2` while the current blocker remains. That is a safety result, not a
failed data operation.

## Remaining execution stages

1. Resolve the one current Goods Received Note blocker and adapt its F15 tests.
2. Freeze the current F15 revision and working-tree state.
3. Confirm source public/private file archives pass existence, size, and hash
   preflight.
4. Repeat Analyse and the complete read-only Dry Run.
5. Back up and rehearse against a disposable target copy.
6. Load masters, operational documents, children, files, and logs in dependency
   order using controlled batches and checkpoints.
7. Verify counts, broken links, totals, amendment chains, and Item Variant +
   Warehouse + Lot + Received Type stock buckets.
8. Final cutover: freeze F15 writes, migrate only the final delta, rerun every
   verification, then reopen F16. The actual downtime estimate is calculated
   from rehearsal throughput; it is not guessed in advance.

No live historical write migration or final cutover has been performed. The
local rehearsal did read source data, but its dry-run path did not write
historical target business records.
