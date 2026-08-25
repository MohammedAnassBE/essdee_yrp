# MRP Branch Handoff — Production API to Essdee YRP

Last verified: 2026-08-25
Canonical continuation branch: `apps/essdee_yrp` → `MRP`
Base app branch: `apps/yrp` → `develop`
Source reference: Frappe 15 `mrp3.site:8002` / `production_api`
Target: Frappe 16 `essdee_yrp.site:8003` / `yrp` + `essdee_yrp`

## Read this first

This is the current handoff for the MRP migration. Read it before changing the
MRP branch. It separates completed implementation and local verification from
the remaining production cutover and deliberately excluded external contracts.

Supporting documents contain the detailed inventories and evidence:

- `docs/audits/2026-08-20-mrp-doctype-functional-audit.md` — screenshot-led
  Production Order/IPD/cutting/stock workflow audit, final fixes, tested record
  states, and the current 434-test validation result.
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

## 2026-08-25 source-growth and transaction gate

The committed F15 source inventory grew to 263 schemas. The current read-only
planner sees 263 source / 326 target schemas, classifies them as 228 identity,
32 mapped, and three custom, and reports zero blockers. The three new source
DocTypes are `Cutting Bulk Lay Sheets`, `Cutting Bulk Lay Sheet Detail`, and
`MRP HR Shift`; MRP Settings also gained HR connection/shift configuration and
GRN Rework gained the source-versus-target warehouse option.

The new behavior is owned entirely by `essdee_yrp`. Bulk Lay Sheets now drive
split-lot LaySheet creation, consolidated Lot Transfer, per-lot submitted DCs,
stock prerequisite checks, and label completion. Base-DocType links on Delivery
Challan are shipped as Essdee Custom Field fixtures; Essdee-owned DocTypes use
their normal schema fields. Sewing Details includes the HR Strength Report,
whose server endpoint requires Sewing Plan read permission and never returns
stored credentials.

The complete Essdee run passed 514/514 tests: 23 unit, 295 integration, 110
legacy-category, and 86 migration/optimizer tests. After the independent
permission hardening, the focused Strength suite passed 7/7 and runtime
acceptance passed 6/6. `bench build --app essdee_yrp`, Python compilation, JSON
parsing, JS syntax checking, targeted `git diff --check`, and the rendered Bulk
Lay Sheets and Sewing Strength pages passed with no browser-console errors.
The local target's previously blank HR settings were then copied from the
configured F15 source through the existing in-memory password bridge and
Frappe encrypted-password storage; no credential was printed or stored in the
repository. A real Desk fetch returned HTTP 200 and rendered 181 active
employees plus 42 summary rows (223 table rows total) with zero console errors.
The integrated run includes exact/collapsed bundle DC, return, redelivery,
LIFO cancellation, split-DC stock-ledger matching, GRN, rework, Sewing,
Finishing, and dispatch paths. No base `yrp` production file was changed for
this addition.

## 2026-08-20 screenshot-led MRP functional gate

The migrated operational chain was driven in the rendered Desk and `/web` UI
across normal, draft, submitted, in-progress, partially completed, approval
pending, bundles generated, label printed, completed, and cancelled records.
The evidence set has 237 workflow screenshots plus the six authenticated
canonical `/web` screenshots. See the audit linked above for exact records and
states.

The audit corrected Work Order address scoping and calculation routing,
matrix overflow, Approved-IPD authority, cancelled Cutting Plan and terminal
LaySheet server/UI guards, Cut Panel Movement single-root transaction
ownership, and the duplicate Production Order Lot card. Base `yrp` owns only
the two generic Work Order address filters; every other audit change remains
Essdee-owned.

The follow-up on exact record `YRP-WO-2026-00038` restored Production API's
non-cloth **Calculate Items** flow in Essdee Desk while retaining the separate
cloth-specific calculator. The garment service covers Cutting, Stitching,
Packing, IPD extra processes, and grouped processes. Approved legacy IPDs also
expose **Generate / Regenerate IPD Process Matrix**, which rebuilds only derived
matrix documents. `CS-34820 Heavy Tee-1` currently generates 24 Cutting
matrices and explicitly skips eight Navy variants because the approved source
IPD has no Navy stitching/panel-colour mapping.

The final independent pass also closed direct-save spoofing into LaySheet
Approval Pending, Label Printed, and Cancelled states. Grammage requests and
physical label-print confirmation now pass through locked server actions; the
label transition verifies the submitted GRN belongs to that LaySheet.

Final `essdee_yrp` validation passed all 434 tests (12 unit, 258 integration,
78 compatibility-category, 86 remaining), including the complete CPM → DC →
GRN and CPM → Stock Entry lifecycles. The production frontend built cleanly and
authenticated `/web` verification captured 6/6 pages with zero console/page
errors or configuration warnings. No migrate, historical-data rewrite,
commit, or push was performed.

## 2026-08-18 production-portability gate

The complete local SQL migration has now run: 3,437,124 source parents and
6,325,639 parent/child documents were migrated, and 161,573,787 transformed
field values were verified. That local result does not make a hardcoded local
runner safe for production, so the execution boundary was hardened afterward.

Current production contract:

- The live migration runner contains no F15 bench path, source site, target site,
  record-name exception list, date cutoff, Received Type name, Item Group
  name, or Lot BOM process name. The separate filesystem-only schema-planner
  CLI retains a local developer default; it does not execute the live migration
  or write site data.
- The active F16 site is always the target. The source bench/site and the few
  source-specific legacy defaults come only from server-owned
  `site_config.json`; Desk/API users cannot change them through the migration
  document.
- Only the reviewed `local_bench` source adapter is accepted. The configured
  F15 bench must be on the same controlled host or mounted/restored locally
  with its database and public/private files. Arbitrary remote URLs, SSH
  commands, and credentials are deliberately not accepted.
- The source must be in maintenance mode for **Migrate**, and the not-yet-live
  target must remain isolated from business users/writers. A
  successful Dry Run is reusable only while the source runtime-schema hash,
  every parent/child table count and maximum modification timestamp, and the
  exact source-invalid-Link digest remain identical. The deployed migration
  code, target schema/mapping contract, and server defaults are fingerprinted
  too, so a deployment or profile edit forces a new Analyse and Dry Run.
- Historical broken Links are discovered from the frozen source and matched by
  target DocType/field/row/value. No local record IDs are approved in code.
- Stock verification uses every live YRP stock dimension and the complete
  Stock Ledger Entry population; it has no Lot/Received Type or naming-prefix
  shortcut.

Configure each target site before creating or saving `MRP Data Migration`:

```bash
bench --site <f16-target-site> set-config --parse essdee_yrp_migration \
'{"adapter":"local_bench","source_bench":"/absolute/path/to/frappe-15","source_site":"<f15-source-site>","source_app":"production_api","required_defaults":{"IPD Settings.default_knitting_process":"<source-process>","IPD Settings.default_dyeing_process":"<source-process>","Lot BOM.process_name":"<reviewed-process-for-legacy-blank-rows>"}}'
```

Do not put passwords or API secrets in this profile. MRP Settings Password
fields use the normal source/target encryption handling and can be configured
again after cutover when source encryption keys are unavailable.

Read-only verification after this hardening passed against the current local
source/target combination: live plan 260 source / 318 target DocTypes, 0
blockers; 293,115 stock buckets exact; all 25 source-invalid Links audited and
0 unexpected target-invalid Links; 75 focused migration tests passed. No
historical data was rewritten during this hardening pass.

### Fresh destructive rehearsal after hardening

The owner-approved fresh rehearsal completed on 2026-08-18 through audit run
`MRP-MIG-2026-00002`:

- The source and target were put in maintenance mode, the target worker and
  Kafka consumer were paused, and a full pre-reset backup was taken
  (`20260818_110356-essdee_yrp_site-*`).
- Analyse reported 260 source / 318 target DocTypes and zero blockers. A fresh
  Dry Run transformed all 3,437,124 parents with zero failures and locked the
  source/schema/code/default fingerprint used by Migrate and Verify.
- The reset removed exactly 3,437,113 non-Single parents, 2,892,711 child rows,
  969 migrated File records, 3,218 generated supplier warehouses, and 171
  source series counters. It preserved the 11 Single/configuration DocTypes
  required to rebuild the live stock-dimension contract. Post-reset checks
  found zero remaining migration-owned parent, child, File, or series rows.
- Migrate then wrote all 3,437,124 parents with zero skipped and zero failed.
  Verify matched 6,325,639 parent/child identities and 161,573,787 transformed
  field values with no target-only or missing source identity.
- Stock matched across all 293,115 configured-dimension buckets. Link scanning
  checked 704 fields: all 25 exact source-invalid values were audited and there
  were zero unexpected invalid target Links. All 171 source naming counters
  passed.
- The restored local source has 1,004 File records but only two physical blobs;
  967 attached records have an audited missing blob and 35 are audited orphan
  attachments. The two available blobs passed disk/hash/size/privacy checks.
  This is a limitation of the local production backup, not permission to omit
  files in production: a production cutover with complete public/private
  archives must use strict file mode.
- A verified post-load backup was taken
  (`20260818_124059-essdee_yrp_site-*`). Both sites, the worker, and the Kafka
  consumer were restored to their original non-maintenance state; the target
  health endpoint and rebuildable MyISAM tables passed.

No production-server cutover was performed. Migration-code changes remain
uncommitted for owner review.

## 2026-08-18 business-logic implementation gate

The F15 controller inventory has been classified and implemented as F16
outcomes across all 85 source controllers. An outcome can be a retained
stronger base-YRP implementation, an Essdee controller, a small Essdee adapter,
a complete orchestration slice, or an intentional replacement/exclusion. This
does not mean 85 legacy files were copied.

Completed internal scope includes:

- production setup, PPO changes/pricing, Lot/IPD/Work Order integration;
- cutting definition, planning, bundle generation, label-to-GRN, panel
  movement, recut, and exact cancellation/retry behavior;
- quality/debit/rework mapping through current F16 contracts;
- Sewing entry, closed-Work-Order GRN, dashboard, status, SCR, history, DPR,
  monthly summary, item summary, FI updates, and consumption;
- Finishing/dispatch, dynamic packing, old-Lot, OCR, return/rework, Lot Transfer,
  and set-item DPR multiplication without multiplying physical boxes;
- F16 dimension-aware FG stock entry, Item Conversion, Stock Summary, and
  stock-facing Essdee adapters;
- Time and Action, Product local behavior and secured files, local FG Item
  generation, stickers, pricing/profitability, and bulk Work Order close;
- required Desk JS/dialogs, 18 operational reports, and 32 print formats.

During the final audit, Cutting LaySheet diameter-change stock adjustment was
found to be carrying a legacy Supplier value into the F16 Warehouse dimension.
It now resolves the supplier's mapped Warehouse through the base YRP contract,
and the regression is covered by the complete suite. Sewing permissions were
also corrected so System Manager retains the standard create/read/write/delete
contract when the Stock User Custom DocPerm exists.

Verification on `essdee_yrp.site`:

- complete Essdee app suite: 402/402 tests passed;
- six Sewing parent/child tables match normalized F15 SQL values;
- all 18 operational reports execute against migrated F16 data;
- all 32 print formats render against migrated documents;
- Desk build and all JavaScript syntax checks pass;
- Python compilation, DocType JSON parsing, and `git diff --check` pass;
- a real System Manager session opened Sewing Details Dashboard without a
  browser-console error.

The implementation remains uncommitted for owner review. Base `yrp` was not
changed by this business-logic completion pass.

## 2026-08-20 Production Order manual-UAT overlay

Owner UAT found that the migrated Production Order client script had retained
the approval/quantity/status workflows but had omitted the F15 order-entry
mount. Base YRP's generic entry grid therefore collected quantity only, leaving
Essdee `Production Order Detail.ratio` and the original price fields at zero.

The Essdee layer now replaces the generic grid inside the existing
`details_html` field with an Essdee-owned Vue grid for Qty, Ratio, read-only
Wholesale/Retail Price, and editable MRP. It emits base YRP's generic grouped
item payload plus the Essdee values: base YRP still owns variant creation and
quantity expansion, while the Essdee `before_validate` hook maps only its
Custom Fields onto those child rows. A prior-row fallback preserves values
owned by later workflows, including `production_order_mrp`, when a submitted
document is saved again. New unsaved orders use DocType create permission for
grid editability because Frappe does not supply the saved-document `__onload`
action-role flag until the document exists; saved drafts retain the configured
Production Order action-role gate. Server permissions remain authoritative.

The UAT warning `Date 2026-08-20 10:24:28 must be in format DD MM YYYY` came
from JSON approval-request timestamps containing microseconds. Quantity/ratio,
status-change, and incoming-transfer requests now store whole-second Frappe
Datetime strings, and `onload` normalizes already-pending request JSON before a
Datetime dialog renders it.

Verification on `essdee_yrp.site`: 12/12 focused Production Order business
tests and 2/2 customization tests passed; the tests cover generic-grid storage
of ratio/prices, Production Order-to-Lot ratio propagation, and whole-second
timestamp formatting. The complete Essdee suite then passed 422/422, and
`bench build --app essdee_yrp` passed. Browser checks on `PPO-00254` and a new
unsaved Production Order confirmed the custom grid, all eight editable ratio
inputs, Qty 12 / Ratio 3 / MRP 199 output, and zero console/page errors. A
post-build browser repeat again returned Qty 12 / Ratio 3 with zero errors. No
document was saved during browser verification, and base `yrp` was not changed.

## 2026-08-20 cutting and printing workflow UAT overlay

The owner-defined transaction chain was compared record by record between F15
`mrp3.site:8002` and F16 `essdee_yrp.site:8003`. The connected historical
oracle is:

`PPO-00081` → `C0326-28` →
`EE-36221 SHORTS SET HALF SLEEVE (CORD)-3` → `WO-2526-02637-2` →
`CP-2603-00030` → `CM-2603-00135` → `CLS-2603-00251` →
cutting DC `DC-2526-07291` → label GRN `GRN-2526-12944` → printing Work
Order `WO-2627-00005` → internal CPM `CPM-2603-00364` / Stock Entry
`STE-2026-05590` → outward CPM `CPM-2604-00015` / DC `DC-2627-00057` →
inward CPM `CPM-2604-00036` / GRN `GRN-2627-00183`.

All document links and persisted business payloads in that chain match the
migrated F15 source. The corresponding 16 F15/F16 Desk routes were rendered;
there were zero console or page errors. The audit then found and closed these
remaining current-source/UI gaps, entirely in `essdee_yrp`:

- Lot again exposes permission-gated **Actions → Link to PO / Unlink from PO**.
  Both routes use the existing server-authoritative linked-Lot APIs and require
  an audit reason.
- A submitted Cutting Plan can create a draft **Lot Transfer** for positive
  balance cloth. The server validates read/create permission, the submitted
  plan, a different readable target Lot, the Work Order supplier-to-Warehouse
  mapping, the configured default Received Type, and dimension-aware rows.
- System Manager cancel authority for Cutting Marker and Cut Panel Movement is
  restored by an idempotent Essdee setup task. The task is wired into install
  and migrate hooks and was also applied directly to the current target site;
  it does not alter base-YRP metadata files.
- CPM-created Delivery Challans and GRNs now receive the Work Order address
  snapshots required by the F16 schemas even though the CPM client opens the
  new document by assigning defaults directly. A new server guard rejects a
  closed, cancelled/draft, or different-Lot Work Order even if a caller bypasses
  the Desk Link filter.
- Regression coverage now performs a real CPM → DC → incoming CPM → GRN
  round trip, asserts bundle-ledger/backlink creation, and cancels it in reverse
  while proving both ledgers and backlinks are cleared. Separate tests cover
  CPM Stock Entry, collapsed/non-bundle submit and cancel routing, label-to-GRN,
  and Cutting Plan balance-Lot-Transfer creation.

The old F15 System Manager **Calculate Pieces** Work Order action was reviewed
but not copied. It is a repair utility built around superseded F15 DC/GRN piece
recalculation engines, not part of the forward transaction chain, and its
legacy implementation can increment delivered quantities twice. F16's normal
DC/GRN lifecycle is already covered directly; any historical repair requirement
must be specified and implemented as a separate audited, idempotent repair
operation. Likewise, the F16 omission of **Create Debit** on a closed Work Order
is an intentional stronger guard, not a missing migration action.

Final verification after these fixes: complete Essdee suite 427/427; cutting
module 15/15; Lot/PO boundary module 10/10; JavaScript syntax and Python compile
checks passed; `bench build --app essdee_yrp` passed. Browser verification as a
System Manager showed the Lot actions, Cutting Plan Lot Transfer, Cutting
Marker and CPM Cancel controls, and CPM Stock Entry/DC/GRN Create menu with
zero console/page errors. The base `yrp` repository was not edited by this
overlay.

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
| `/home/anas/frappe-15/apps/production_api` | `feat/cutting-plan-lot-transfer` (current reference branch; re-check before every continuation) | Read-only source/reference during F16 work. It currently has owner changes; do not switch, commit, or discard them from this repository task. |

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

### Hard repository rule from the owner — 2026-08-20

For this MRP work, **do not change the base `yrp` app**. Manage and customize
base-YRP behavior from `essdee_yrp` using its hooks, Custom Fields, client
scripts, overrides, and published extension points. If a future requirement
appears impossible without a base change, stop and obtain the owner's explicit
approval instead of editing `apps/yrp`.

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
- server-configured, read-only F15 subprocess bridge;
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

The successful migration reconciliation recorded F15 source snapshot
`9cc4329c66ab`. The current business-logic reference checkout is branch
`fix/packing-dpr-box-count` at
`8ad0f3e18b2118387fbe16fb3b45c01c868071f5`; therefore neither value may be
treated as the production cutover fingerprint. Freeze and fingerprint the
actual source again at cutover.

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

- No production-server cutover, production downtime window, final delta, or
  rollback rehearsal has been executed. The completed destructive rehearsal is
  local only.
- The local source restore does not contain the complete physical public/private
  file archives. Production attachment transfer still requires strict blob,
  hash, size, path, and privacy verification against the real archives.
- Remote FG OMS/DC synchronization is intentionally not reactivated. Its
  endpoint, authentication, authorization, retry, and idempotency contract must
  be approved separately if it is still needed.
- Telegram approval and the global automatic-notification hook are intentionally
  excluded until their production authorization and delivery contracts are
  reviewed as separate integration work.
- The required Desk workflows are ported. A separate `/web` redesign or new
  Registered Experience is not implied by this migration and must follow the
  bench UI architecture if requested later.
- The current F15 working tree can continue to move. Freeze and fingerprint the
  actual production source again before cutover; do not rely on an older HEAD.
- Local Spine behavior is covered by current mapping/consumer tests, but
  production synchronization health must still be observed during cutover.
- The current MRP implementation and its latest fixes have not been committed;
  they are intentionally left visible for owner review.

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

### Gate 5 — business-logic slices: completed locally

The internal business-logic slices, required Desk integrations, reports, print
formats, permissions, cancellation/retry paths, and F16 stock-dimension
adapters are implemented and covered by the 418-test local suite. Before
production release, repeat the complete suite on the exact deployment commit
and run owner UAT over the major end-to-end workflows. External FG OMS/DC,
Telegram approval, and global notifications remain separate contracts.

### Gate 6 — UI parity

Required migrated Desk JS, dialogs, report views, and Sewing Details views are
implemented. Any later `/web` surface must use the Registered Experience versus
Configurable Layout decision in the bench `AGENTS.md`; it is a separate design
scope, not an unfinished controller port. Repeat rendered UI and console checks
for the production deployment and owner UAT records.

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

## 2026-08-19 complete runtime acceptance overlay

- All 71 migrated parent DocTypes loaded through Frappe's form loader. The four
  parents without persisted rows also accepted rollback-safe sample documents;
  `WO Recut` completed an insert, submit, and cancel lifecycle.
- All 71 parent routes were opened in the real Desk browser while HTTP,
  JavaScript console, page, and request errors were captured. The only initial
  Item Group 404 was the verification user's correct lack of Item Master
  permission; a temporary role proved the route and was removed immediately.
  Finishing Plan Dispatch's two apparent failures were navigation-cancelled
  requests and completed cleanly when the route remained open for 20 seconds.
- All 209 distinct Essdee/YRP server methods referenced by the migrated JS/Vue
  were invoked with rollback protection: 122 returned, 86 stopped at an
  intended Frappe business/permission validation, and one Product tech-pack
  release could not read a deliberately omitted physical attachment. No other
  Python exception remained.
- All 55 Essdee `doc_events` handlers executed against valid migrated records.
  The 100 direct controller lifecycle methods were accounted for as 90 replay
  passes, six successful real stock lifecycle samples, and four intentional
  cancellation/audit guards.
- A real historical defect was found in F15 itself: 27,861 GRN rework detail
  rows store `set_combination` as JSON encoded twice. Migration correctly
  preserved the source bytes. Essdee Finishing now unwraps that legacy shape
  safely in every combination-key path; both previously failing Finishing
  quantity rebuild APIs pass on `FP-2627-00076`.
- Real forward-and-reversal tests pass for FG Stock Entry, Item Conversion,
  Recut and Print Panel, migrated Cutting LaySheet GRN creation, legacy packing
  GRN stock-only consumption, Cut Bundle Edit, and Cut Panel Movement.
- The complete Essdee suite passed 418/418. The complete base YRP Stock Entry
  module passed 13/13 after preserving owner-supplied cancellation backlink
  exemptions. Python compilation, `git diff --check`, `bench build --app
  essdee_yrp`, and `bench build --app yrp` passed.
- Physical Product attachments remain outside this acceptance because the
  owner explicitly excluded their blobs from the restored local backup. The
  attachment APIs' synthetic tests still pass; production release testing must
  use the real public/private file trees.

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
  storage field. Its special server behavior was still pending in this
  2026-08-17 snapshot and is completed in the current business-logic gate.
- At the time of the 2026-08-17 overlay, no `bench migrate`, live data
  migration, commit, or push was performed. The later local historical load is
  recorded in the 2026-08-18 overlay above.

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
