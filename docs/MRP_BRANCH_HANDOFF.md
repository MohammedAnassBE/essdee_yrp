# MRP Branch Handoff — Production API to Essdee YRP

Last verified: 2026-08-17
Canonical continuation branch: `apps/essdee_yrp` → `MRP`
Base app branch: `apps/yrp` → `develop`
Source reference: Frappe 15 `mrp3.site` / `production_api`
Target: Frappe 16 `essdee_yrp.site` / `yrp` + `essdee_yrp`

## Read this first

This is the current handoff for the MRP migration. Read it before changing the
MRP branch. It separates completed implementation from tested rehearsal,
pending decisions, and work that has not started.

Supporting documents contain the detailed inventories and evidence:

- `docs/MRP_MIGRATION_CONTEXT.md` — full structural decision history.
- `docs/plans/2026-08-13-production-api-data-migration.md` — migration engine,
  rehearsal, attachment, and cutover details.
- `docs/plans/2026-08-13-production-api-business-logic-migration.md` — ordered
  business-logic slices.
- `docs/audits/2026-08-14-sd-yrp-spine-data-parity.md` — local Spine identity
  and count snapshot.
- `docs/audits/2026-08-14-sd-yrp-spine-field-value-audit.md` — mapped field and
  child-table audit.
- Bench document
  `docs/yrp/2026-08-13-yrp-essdee-lot-packing-boundary-handoff.md` — the base
  YRP versus Essdee Lot/packing boundary.

If an older status paragraph conflicts with this file, this file and the
current code/tests win. Re-run the checks instead of trusting an old count.

## Why this work exists

The Frappe 15 `production_api` app has more than three years of Essdee
production data and business behavior. The goal is to move the required
schema, historical data, business logic, and UI into Frappe 16 without copying
`production_api` as another monolithic app.

The migration is deliberately split:

1. `yrp` owns reusable stock, procurement, work-order, accounting, permission,
   and metadata-driven stock-dimension behavior.
2. `essdee_yrp` owns Essdee-specific Lot, cutting, sewing, finishing, product,
   Time and Action, custom fields, mappings, and UI.
3. Historical data is migrated before the remaining business logic so real
   records can be used to verify each functional slice.
4. UI parity is completed after the data and server behavior are approved.

## Branch and repository boundary

Current intended state:

| Repository | Branch | Rule |
|---|---|---|
| `/home/anas/frappe-16/apps/yrp` | `develop` | Already contains the approved generic base work. Do not edit, commit, or switch it as part of Essdee MRP work unless the owner explicitly asks. |
| `/home/anas/frappe-16/apps/essdee_yrp` | `MRP` | Contains the migration schema, Essdee customization, migration engine, tests, and these documents. |
| `/home/anas/frappe-15/apps/production_api` | `develop` | Read-only source/reference during F16 work. It currently has owner changes; do not commit them from this repository task. |

Essdee `develop` and `MRP` are intentionally separate. The 2026-08-17 review
selectively ports approved runtime fixes from `develop` into the MRP working
tree; it does not merge or rebase either branch. MRP Settings dependency
schemas are prepared in a separate `develop` worktree so those edits do not
pollute the MRP branch.

## 2026-08-17 combination review decisions

Approved and implemented in the current MRP working tree:

- `/web` now owns its complete engine under `essdee_yrp/frontend/src/engine`;
  it no longer links to a removed base-YRP frontend package.
- The Essdee `CutPlanItems` component is restored and registered for Lot Desk.
- Lot BOM calculation uses YRP's matrix engine plus the Essdee garment
  accessory adapter.
- IPD approval uses only base YRP's `Not Approved` / `Approved` contract.
- The obsolete cross-bench **Create Stock in MRP** action, endpoint, hook, and
  three audit fields are removed from MRP.
- Every fixtured Custom Field is explicitly owned by module `Essdee YRP`; the
  fixture export filter is strict and no longer captures module-less fields.
- The two redundant Production Order naming-series Property Setters are
  removed because base YRP already declares the same values.
- Essdee contributes its fabric-reference fields through YRP's generic stock
  row-extension hook, so grouped Work Order deliverables/receivables preserve
  their calculated final-cloth route without making base YRP Lot-aware.
- Work Order keeps base YRP's generic free-text `close_reason`. Essdee owns the
  fixed Production API vocabulary in `sd_close_reason`, plus the conditional
  `close_other_reason`; historical `close_reason` maps to the Essdee field.
- Goods Received Note carries the hidden, read-only, no-copy
  `from_closed_wo_sewing_details` Check so its historical value can migrate.
  The protected closed-Work-Order Sewing Details workflow remains a later
  Essdee business-logic slice; schema presence does not enable that route.
- Historical migration includes the complete Time and Action graph, including
  every Lot link row and standalone Time and Action record.

An earlier MRP Settings draft exists in a separate Essdee `develop` worktree.
It must not be merged as-is: the approved target-capability rule excludes AQL,
CLS, notification, Sewing Plan, and legacy remote-site credential settings
whose business modules are absent from `essdee_yrp.site`.

The fabric-reference and historical Time and Action scope decisions are now
closed. The separate ongoing Spine real-time-sync scope is unchanged.

## Durable ownership decisions

### Base `yrp`

- Generic stock dimensions and the complete stock bucket.
- Generic Purchase Order, Work Order, Delivery Challan, GRN, Stock Entry,
  reconciliation, ledger, valuation, reposting, and terms behavior.
- Neutral item/BOM and variant APIs.
- No knowledge of Essdee `Lot` or `includes_packing`.
- Base stock behavior receives dimensions through metadata, not hard-coded
  Essdee fields.

### `essdee_yrp`

- `Lot`, Lot packing, linked-Lot procurement, Lot BOM persistence, and Lot UI.
- `Process.includes_packing` and `Work Order.includes_packing` integration.
- Cutting, bundle/panel movement, inspection/rework, sewing, finishing, Time
  and Action, product/FG, price/profit, sticker, and Telegram approval schemas.
- Essdee fields and property changes on base YRP DocTypes.
- F15 compatibility mappings and historical migration rules.
- Essdee `/web` registry/extensions and business-specific client behavior.

Do not move Essdee concepts back into base YRP merely because an old F15 field
was present on a base DocType.

## Approved renamed concepts

These are semantic replacements, not missing DocTypes:

| F15 concept | F16 concept |
|---|---|
| `GRN Item Type` | `Received Type` |
| `Stock Settings` | `YRP Stock Settings` |
| `Essdee Debit` | `Debit` |
| `Vendor Bill Tracking` | existing `Bill Tracking` behavior |
| `Essdee Raw Print Format` / detail | `ZPL Raw Print Format` contract |
| `Purchase Order Lot` | Essdee-owned `Lot MultiSelect` |
| Supplier used as a stock location | mapped Warehouse where the F16 stock contract requires Warehouse |

No target Link option should point to legacy `GRN Item Type`. Migrated values
must retain the business value/name while linking to `Received Type`.

## Completed work

### 1. Structural audit and missing schemas

- All source schema concepts were inventoried against F16.
- The original 150 missing schemas were created in `essdee_yrp`: 65 parent
  DocTypes and 85 child tables.
- Parent/child options, ordering, Dynamic Links, renamed Link targets, naming,
  permissions, and module ownership were structurally checked.
- All originally changed DocTypes received a reviewed keep/customize/map
  decision; unchanged same-structure rows were removed from the active review.
- The schemas are storage contracts. A generated/minimal controller does **not**
  mean the corresponding F15 workflow has been ported.

Major schema groups now present include cutting, finishing, sewing, product/FG,
Time and Action, inspection/rework, price/profit, stickers, Telegram approval,
and supporting children. The exact logic-bearing parent checklist is in the
business-logic plan.

### 2. Reviewed F16 customizations

The MRP branch packages the approved fields and property changes for the
reviewed base DocTypes, including:

- Supplier and Process compatibility fields.
- Purchase Order and Purchase Order Item Essdee Lot/location behavior.
- Purchase Invoice and Purchase Invoice Item compatibility fields while using
  base `bill_tracking` instead of recreating vendor bill tracking.
- Work Order selection, production-detail lookup, supplier terms, packing,
  no-receivables, and related reviewed metadata.
- Delivery Challan, Delivery Challan Item, Goods Received Note, Goods Received
  Note Item, Stock Entry, Stock Entry Detail, Stock Reconciliation, Lot
  Transfer, Production Order, Production Ordered Detail, Work Station, Lot,
  Process Cost, Item Production Detail, and Repost Item Valuation decisions.
- Complete configured stock dimensions on stock-moving child rows. `lot` and
  `received_type` are generated through the base metadata-driven dimension
  mechanism where they are stock dimensions; they are not duplicated as
  unrelated direct fields.
- Inspection/rework aggregation avoids storing an arbitrary first Inspection
  Entry when several inspections exist for one GRN/item bucket.

Detailed field-by-field decisions remain in `docs/MRP_MIGRATION_CONTEXT.md` and
the focused customization tests.

### 3. Lot and packing boundary

- Base YRP is kept Lot-neutral.
- Essdee owns linked-Lot Purchase Order behavior, Lot UI, packing controls,
  audit data, and GRN packing policy.
- Neutral base BOM APIs are reused; Essdee supplies the Lot-specific context.
- Work Order item selection is constrained by Lot, and Essdee derives/stores
  the matching Item Production Detail from the selected item.
- Lot Transfer keeps the Essdee child table, finishing-plan trace, and guarded
  posting date/time edit behavior.

### 4. Historical migration engine

One generic dependency-ordered engine was implemented under
`essdee_yrp/migration/`; this is not one script per DocType.

It includes:

- filesystem-only schema planner;
- identity, declarative mapped, and custom transformer classifications;
- recursive parent/child transforms and contextual child mappings;
- renamed DocType, field, Link-option, and value mappings;
- deterministic dependency groups, including Link cycles;
- content-hash checkpoints and resumable/delta behavior;
- fixed F15 subprocess bridge for `mrp3.site` reads;
- controlled F16 SQL bulk upserts that preserve source parent and child names;
- Single DocType and Single child-table handling;
- supporting-master, password-field, attachment, stock-summary, and `tabSeries`
  phases;
- verification and audit reporting;
- an Essdee-owned `MRP Data Migration` DocType with Analyse, Dry Run, Migrate,
  and Verify actions restricted to System Manager.

Historical target writes intentionally use database-level batched operations,
not `get_doc().insert()` or business controllers. This preserves source
identity/state and avoids firing incomplete F16 workflows. New records created
after cutover must use normal F16 controllers.

The standalone `scripts/mrp_data_migration.py` command is only the repository
schema planner. Live/rehearsal execution is implemented in
`essdee_yrp.migration.live` and invoked by `MRP Data Migration` jobs. Do not
confuse the schema-only CLI with the live adapter.

### 5. Completed read-only rehearsal evidence

Against the local F15 clone before today's new source schema change:

- 3,437,048 documents processed in the complete rehearsal.
- 0 transformation failures.
- 240,390 required values preserved or derived.
- 1,524 external Link values validated.
- 1,004 File rows and 846 content keys accounted for.
- 171 source naming-series counters validated.
- Source document names, child names, docstatus, audit timestamps, and series
  merge behavior were exercised without starting the live historical load.

This proves the implemented runner on that source snapshot. It is not approval
to write current data without repeating the preflight against the frozen source.

### 6. Attachments

- Public and private controlled Product Image samples passed byte transport,
  privacy/path/metadata checks, direct Attach Image repair, target disk read,
  MD5/size checks, and idempotent rerun.
- The local `mrp3.site` restore is database-only. Of the 1,002 original File
  rows, 999 blobs are absent and the three present blobs do not match stored
  hashes.
- Therefore the local clone cannot prove original production attachment
  migration. Production must include public/private file archives and pass the
  strict file-health gate before any write run.

### 7. Spine field mapping fixes

The F16 consumer/mapping work covers:

- Production Ordered Detail direct `lot` plus dynamic fields.
- MRP Settings imports only target-supported values; absent-module child-table
  configuration, including Sewing Plan, stays excluded.
- Historical migration includes every Time and Action parent/child row and
  every `Lot Time and Action Detail`. The existing Spine real-time consumer
  exclusion is a separate contract and is not changed by this decision.
- Supplier Users retained on Supplier and mapped Warehouse.
- Address GSTIN and User Telegram ID compatibility fields.
- Production Order parent fields and child-table mapping.
- IPD `stage` mapped into the F16 in/out-stage contract.

The matching F15 `production_api/sd_yrp_sync.py` and test edits remain in the
F15 working tree and are **not** part of the Essdee MRP commit. They must be
reviewed and committed separately in the F15 repository if the owner wants
them retained.

## Current source-schema reconciliation

The F15 source moved after the successful rehearsal. Current reviewed F15 HEAD
is `9cc4329c66ab`.

The Work Order close fields are resolved without changing base YRP: source
`close_reason` maps to Essdee `sd_close_reason`, and Essdee supplies
`close_other_reason`. The new GRN sewing marker has an Essdee-owned storage
field. Fresh schema analysis now reports zero blockers.

Current schema result:

| Result | Count |
|---|---:|
| Source DocTypes | 260 |
| Target DocTypes | 318 |
| Identity | 224 |
| Declaratively mapped | 33 |
| Custom | 3 |
| Blockers | 0 |

The schema planner is ready. This does not authorize a live migration: repeat
the read-only Dry Run and its data/attachment gates before any historical write.

## Work that has not been done

- No live historical business-data migration has been executed on
  `essdee_yrp.site`.
- No final production cutover, downtime window, final delta, or rollback has
  been executed.
- The 150 schema ports are not all functional workflow ports. Most substantive
  F15 controllers, JS/Vue components, reports, print formats, scheduled jobs,
  and permissions still require slice-by-slice review and adaptation.
- Finishing Plan/Dispatch and Cutting LaySheet behavior is planned but not yet
  complete merely because their schemas and some UI assets exist.
- The current F15 working tree has additional owner changes. Its earlier HEAD,
  dirty-file list, and hash recorded in the 2026-08-13 plan are historical,
  not a safe current baseline.
- Local Spine target data was audited but not bulk-republished or converged by
  this branch handoff. Production sync health must be measured at cutover; do
  not infer production state from the local disabled scheduler/backlog.
- No full `bench migrate` was run as part of this final documentation/commit
  handoff.

## Ordered continuation plan

### Gate 1 — refresh and freeze the source contract

1. Switch only `apps/essdee_yrp` back to `MRP`.
2. Re-read this handoff and inspect all three repositories without resetting
   owner changes.
3. Record current F15 HEAD, branch, dirty-file list, and diff hash.
4. Re-run schema analysis and require zero blockers.

### Gate 2 — metadata and environment readiness

1. Apply packaged schema only to the reviewed development/rehearsal target.
2. Run `bench migrate` only with the owner's explicit approval and only on the
   named non-production site.
3. Verify installed apps, live columns, Custom Fields, Property Setters,
   permissions, stock-dimension metadata, queues, and available disk space.
4. Confirm the source public/private file archives are mounted and readable.

### Gate 3 — repeat read-only migration verification

1. Create/save an `MRP Data Migration` record.
2. Click **Analyse Schema**; require `Ready` and zero blockers.
3. Click **Dry Run**; wait for the queued job and require `Dry Run Complete`.
4. Review per-DocType counts, required-value audit, links, files, stock buckets,
   Single values, password fields, children, naming series, and error log.
5. Rehearse against a disposable target and verify repeat/idempotent behavior.

Creating or saving the audit record does not itself migrate data. The owner or
System Manager must invoke the actions in order.

### Gate 4 — controlled historical load

1. Take verified source and target backups.
2. Freeze F15 writes for the measured cutover window.
3. Run **Migrate** only after the final dry run passes.
4. Resume from checkpoints if interrupted; never start a separate ad-hoc copy.
5. Run **Verify** and reconcile parent/child counts, broken links, files,
   amendments, series, totals, ledgers, bins, and complete Item Variant +
   Warehouse + every configured dimension stock buckets.
6. Run the final source delta, repeat verification, and reopen only after every
   gate passes.

### Gate 5 — business-logic slices

After historical-data verification, implement and test in this order:

1. Shared F15-to-F16 compatibility seams.
2. Complete Finishing Plan + Finishing Plan Dispatch, including current F15
   packing/OCR behavior and tests.
3. Cutting Order/Plan/Marker/LaySheet, including label-to-GRN behavior with
   server-safe retry/idempotency.
4. Panel movement, inspection, rejection, rework, and recut.
5. Sewing and Time and Action.
6. Product/FG, uploads, labels, pricing, and profitability.
7. Remaining utilities, reports, print formats, permissions, schedules, and
   integrations.

For each slice, adapt behavior to F16 stock dimensions and permission rules;
do not blindly copy F15 controllers.

### Gate 6 — UI parity

Complete Desk and `/web` behavior after the backend contract is stable. Use
the registered-experience versus configurable-layout decision in the bench
`AGENTS.md`, and verify rendered UI/console rather than code alone.

## Verification requirements for future work

A migration or logic slice is not complete until applicable checks pass:

1. JSON parses and Python compiles.
2. Focused unit/integration tests pass in the correct Frappe site context.
3. The schema planner has zero unexplained fields or Link targets.
4. Forward, cancel, retry, duplicate-request, and resume behavior is tested.
5. Complete stock-dimension buckets reconcile.
6. Attachments pass existence, size, hash, privacy, metadata, and disk-read
   checks.
7. Server permissions are authoritative; hidden UI is never treated as access
   control.
8. Changed UI is built and inspected in the browser with no console errors.
9. `apps/frappe` and `apps/erpnext` remain untouched.
10. An independent diff review finds no secret, generated site data, source
    behavior loss, or unrelated owner change.

## 2026-08-17 validation overlay

- The query-only capped live rehearsal now passes all mapped DocTypes: 1,469
  parents, 18,633 children, and 396,709 stored field values were read back and
  matched, with zero failed DocTypes. It used F15 effective live metadata and
  included Lot Time and Action rows that are not safe to infer from stale
  repository metadata alone.
- The Stock Reservation Entry `voucher_type` decision is resolved: base YRP
  uses an unopinionated Select and Essdee supplies `Work Order`, `Stock Update`,
  and legacy `Packing Slip` through a scoped Property Setter. Base YRP stores
  `voucher_no` as plain Data, matching F15 and preserving the legacy reference
  without requiring a fake Packing Slip DocType. The remaining migration
  decisions are two locally undecryptable MRP Settings secrets and the
  not-yet-run attachment/blob rehearsal. See `docs/MRP_MIGRATION_CONTEXT.md`
  for exact counts and options.
- The standalone planner remains read-only and reports 260 source DocTypes,
  318 target DocTypes, and zero blockers.
- The local `/web` production build passed after removing the YRP frontend
  package link (505 modules transformed).
- Local-engine Node tests passed 3/3.
- UI ownership/mirror tests passed 16/16.
- Garment BOM adapter/matrix tests passed 5/5 and Lot controller tests passed
  2/2.
- Python compilation, JSON parsing, `git diff --check`, fixture ownership,
  Property Setter scope, and patch registration passed.
- Migration engine/schema unit tests pass with the GRN marker preserved as a
  storage field. Its special server behavior is intentionally still pending.
- No `bench migrate`, live data migration, commit, or push was performed.

## Historical 2026-08-14 validation snapshot

Checks run on 2026-08-14 before the MRP commit:

- All packaged Essdee JSON parsed successfully.
- All intended changed/new Python files compiled successfully.
- `git diff --check` passed.
- `npm run build` in `apps/essdee_yrp/frontend` passed.
- `bench build --app essdee_yrp` passed.
- The 19 site-bound live migration adapter tests passed 19/19.
- The full Essdee app test run passed the broad schema, customization, stock,
  Lot boundary, Spine mapping, Work Order, and migration adapter coverage, but
  ended with three explicit failures:
  1. planner zero-blocker assertion — expected until the new Goods Received
     Note source field is resolved;
  2. one Goods Received Note transformer test — blocked by the same field;
  3. existing `/web` home-queue mirror drift: Essdee `HomeQueues.vue` contains
     `open_lots`, while base YRP's generic `HOME_QUEUE_METRICS` registry does
     not. Do not fix this by teaching base YRP about Essdee Lot; resolve it as
     an Essdee-owned metric-registry extension during the UI slice.
- Browser `verify-ui` could not authenticate because the local verification
  credentials returned HTTP 401. The frontend build passed, but rendered UI
  verification must be repeated after the test credentials are repaired.
- Ruff was not installed in this environment.

These are reported limitations, not hidden passes. The first two are the same
single migration blocker; the third is a separate pending UI ownership seam.

## Resume commands

From `/home/anas/frappe-16`:

```bash
git -C apps/essdee_yrp status --short --branch
git -C apps/essdee_yrp switch MRP
git -C apps/yrp status --short --branch
git -C /home/anas/frappe-15/apps/production_api status --short --branch

sed -n '1,260p' apps/essdee_yrp/docs/MRP_BRANCH_HANDOFF.md

cd apps/essdee_yrp
/home/anas/frappe-16/env/bin/python scripts/mrp_data_migration.py --summary
```

The schema command is read-only and must report `ready: true` with zero issues.

## Important safety rules

- Never reset or discard the owner's dirty F15 working tree.
- Never commit `apps/yrp` as part of an Essdee-only task without explicit
  approval.
- Never run a production `bench migrate`, restore, reinstall, or data deletion
  without explicit approval.
- Never write directly into `sites/*/public/files` or `sites/*/private/files`.
- Never commit credentials, site data, backups, `env`, or `node_modules`.
- Never bypass the Analyse → Dry Run → Migrate → Verify state gates.
- Never claim that schema presence equals migrated business logic.

## Commit-scope note

This MRP commit intentionally includes the migration schemas, customizations,
migration engine, tests, UI/support code, and canonical documents in
`apps/essdee_yrp`.

`essdee_yrp/dev/seed_hamic_v2.py` is an older standalone development seed and
is unrelated to the MRP migration. It is preserved in the working tree but is
not included in the MRP commit. The F15 `production_api` changes are also left
untouched and uncommitted by this task.
