# Production API → YRP / Essdee YRP Migration Context

Last updated: 2026-08-25
Working site: `essdee_yrp.site`
Working branches: `apps/yrp` → `develop`, `apps/essdee_yrp` → `MRP`

## Read this first

The concise canonical resume document is now `docs/MRP_BRANCH_HANDOFF.md`. Any
AI agent continuing this branch must read that file, the bench `AGENTS.md`, and
this detailed decision history before changing code.

The owner may temporarily switch `essdee_yrp` to `develop` for unrelated work
and return to `MRP` later. Base `yrp` currently remains on `develop`. Do not
treat this work as finished merely because a previous session ended. Update
the handoff whenever a durable migration decision is made.

The latest execution contract is configuration-driven. `MRP Data Migration`
does not accept a bench path or site as editable data. The active site is the
target, while `essdee_yrp_migration` in server-owned site configuration names
the reviewed local/mounted F15 bench and source site. Production must restore
or mount the F15 database plus public/private files on the controlled migration
host; the runner intentionally has no arbitrary remote-command adapter.

The 2026-08-18 post-load hardening removed exact local record exceptions and
environment values from deployable code. Source snapshots now fingerprint
effective runtime schema, every parent and child table count/maximum-modified
value, the exact source-invalid-Link manifest, deployed migration code, target
schema/mappings, and reviewed server defaults. The source must be in
maintenance mode for a write run, and the pre-cutover target must stay isolated
from other writers. The same change made stock reconciliation metadata-driven
across every configured YRP dimension.

After that hardening, the owner-approved fresh local reset/load/verify completed
under `MRP-MIG-2026-00002`. It migrated 3,437,124 parents, matched 6,325,639
parent/child identities and 161,573,787 transformed field values, reconciled
293,115 stock buckets, audited all 25 source-invalid Links with zero unexpected
target-invalid Links, and verified all 171 source series counters. The local
backup contains metadata for 1,004 Files but physical content for only two;
967 attached missing blobs and 35 orphan attachments are explicitly audited.
Production must supply the complete public/private archives and run strict file
mode. Pre-reset and verified post-load backups are recorded in the canonical
handoff.

The 2026-08-20 Production Order UAT correction is also recorded in the
canonical handoff. Essdee now owns the ratio/price entry presentation and
Custom Field mapping while base YRP continues to own generic variant and
quantity expansion. Production Order request JSON uses whole-second Datetime
strings so approval dialogs do not reject server-generated timestamps.

The same handoff now records the complete cutting/printing transaction audit:
PPO → Lot → IPD → cutting Work Order → Cutting Plan → Marker → LaySheet →
cutting DC → label GRN → printing Work Order → CPM Stock Entry → CPM DC → CPM
GRN. Remaining Lot/PO and Cutting Plan Lot Transfer actions, cutting cancel
permissions, CPM address defaults, closed-Work-Order server guards, and full
CPM DC/GRN reversal coverage are implemented only in `essdee_yrp`. The final
local Essdee suite passes 427/427.

The 2026-08-25 source-growth overlay supersedes older current-count statements:
the planner now reports 263 source / 326 target schemas with zero blockers
(228 identity, 32 mapped, three custom). F15 added Bulk Cutting Lay Sheets and
MRP HR Shift. Their F16 implementation, fixture-owned Delivery Challan fields,
Sewing Strength UI/API, permissions, and full 513-test transaction gate are
recorded in `docs/MRP_BRANCH_HANDOFF.md`. Historical 260/318 and earlier test
counts below remain dated evidence rather than the current inventory.

## Goal

The Frappe 15 `production_api` app has carried Essdee's production data and
business flows for more than three years. The goal is to migrate all required
schemas, logic, data, and UI into Frappe 16 without copying the old app as one
monolith.

- F15 reference: `/home/anas/frappe-15/apps/production_api`, site
  `mrp3.site:8002`
- F16 base platform: `/home/anas/frappe-16/apps/yrp`
- F16 Essdee layer: `/home/anas/frappe-16/apps/essdee_yrp`
- Target site: `essdee_yrp.site:8003`

The migration must preserve business meaning and data traceability while using
the stronger F16 YRP stock and UI architecture.

## Ownership rule

Put reusable production, stock, accounting, permission, and workflow behavior
in base `yrp`. Put Essdee-only masters, fields, cutting/finishing/sewing flows,
and customer-specific UI in `essdee_yrp`.

Never edit upstream `frappe` or `erpnext`. Do not duplicate base behavior in
Essdee merely to match an old field name. A renamed F16 concept is preferred
when it represents the same business meaning.

The owner must review base-YRP changes. Do not commit `apps/yrp` unless the
owner explicitly asks.

For the MRP branch, the owner strengthened this on 2026-08-20: do not edit
base `yrp` at all. Manage base behavior from `essdee_yrp` through supported
hooks, Custom Fields, client scripts, overrides, and extension points. Stop for
explicit approval if a future requirement genuinely cannot be implemented
from the Essdee app.

## Migration phases

1. Audit every Production API DocType and feature against F16.
2. Create missing DocType schemas with correct parent/child links and ordering.
3. All structure decisions are now resolved with explicit base YRP versus
   Essdee ownership.
4. Build and verify the strict data-migration engine without reading either
   site's business data.
5. Resolve every reported data mapping, then run read-only dry run, rehearsal,
   and the approved historical-data load.
6. Port and test business logic against the migrated historical records.
7. Complete Desk and `/web` UI parity after the underlying model is approved.

The structural review is complete. On 2026-08-13 the owner explicitly changed
the sequence: migrate historical data before porting the remaining business
logic, so the real records can be used to verify each functional slice. The
historical loader must bypass runtime workflow side effects and preserve source
state; newly created/edited records use the F16 controllers only after those
controllers are implemented.

The business-logic implementation plan is documented at
`docs/plans/2026-08-13-production-api-business-logic-migration.md`. Its first
vertical slice is Finishing Plan + Finishing Plan Dispatch, preceded only by
their required shared compatibility helpers. Its recorded F15 commit and dirty
file list are a historical snapshot. Future agents must re-inventory the
current F15 HEAD and working tree before implementing any slice.

The current 2026-08-17 code/decision overlay is recorded in
`docs/MRP_BRANCH_HANDOFF.md`. In particular, the MRP `/web` engine, Lot Desk,
Lot BOM adapter, approval-status contract, obsolete remote stock action, and
fixture ownership have been corrected in the working tree. Fabric references
are preserved through the generic YRP stock-row extension hook. Historical
migration includes every Time and Action parent/child row, including Lot link
rows and records not linked to a Lot.

## Current audit status

- The 2026-08-14 local Spine parity audit found that the existing
  `sd_yrp_master` pipeline is not current enough to treat its target records as
  already migrated. All 31 source publish DocTypes and target consumer mappings
  are configured, but only six are exact for synchronized identities/values and
  four more contain all source rows plus target-only records; 21 remain out of
  parity in the local clone. Examples: Item Variant is missing 3,240 source identities, Item BOM
  Attribute Mapping 195, Production Order 91, Lot 82, and Item Production
  Detail 21. The target scheduler is disabled and 187 received Spine messages
  remain Pending. This local scheduler/backlog state is not evidence of the
  production scheduler state. Before the historical SQL load, repeat the
  production-side sync and mapped-value preflight rather than assuming either
  environment is current. Exact local evidence is in
  `docs/audits/2026-08-14-sd-yrp-spine-data-parity.md`.
- All 150 formerly missing Production API schema concepts are accounted for on
  `essdee_yrp.site`. Source `Purchase Order Lot` maps to the existing
  Essdee-owned `Lot MultiSelect`; it is not a base YRP DocType. This is schema
  parity, not confirmation that all old controller logic has been migrated.
- The 2026-08-13 re-audit used then-current Production API commit `9c1538d0`. The
  hidden packing-trace fields introduced by `4d48b222`,
  `Finishing Plan Dispatch Item.packing_source` and
  `packing_piece_quantity`, are present in Essdee YRP and on the live site.
  The later `9c1538d0` finishing-dispatch change is logic-only and introduces
  no additional DocType schema drift.
- 0 changed DocTypes remain open; the structure evaluation is complete.
- Work Order and its three reviewed child tables were removed from the open
  changed list after their decisions were implemented.
- Target-only WhatsApp DocTypes are excluded from this migration audit.
- No production data migration has been performed.
- A fresh schema analysis on 2026-08-17 against F15 HEAD `9cc4329c66ab`
  reports zero blockers. Work Order keeps base YRP's free-text `close_reason`;
  historical Production API values map to the Essdee-owned Select
  `sd_close_reason`, while Essdee supplies `close_other_reason`. Goods Received
  Note now carries the hidden storage-only `from_closed_wo_sewing_details`
  Check; its special protected Sewing Details behavior is still a later logic
  slice.
- The strict document dry run completed on 2026-08-13 for all 3,437,046
  source parent records with zero transformation failures. It audited, rather
  than invented, known historical blanks: Process Cost supplier 492/Lot 546,
  multi-Lot Purchase Order header 388, pre-field Cut Panel warehouse 43, and
  multi-Lot Goods Received Note header 809.
- A later full dry run added supporting-master and physical-attachment gates.
  Missing target Address/User/Role/Letter Head/Email Account/Print Format rows
  are now an explicit read-only supporting-master phase and passed rehearsal.
  The attachment gate found that the local `mrp3.site` clone was restored from
  a database-only production backup: 999 original in-scope File records
  (526,847,048 metadata bytes) have no local blob. The owner confirmed that the
  production cutover source will include its public/private file archives; this
  expectation must still be proven by the same file-health preflight before
  production writes begin. A deeper byte-integrity check on 2026-08-14 found
  that the three original blobs which physically exist in the local restore
  also disagree with their File metadata hashes. Therefore all 1,002 original
  attachment blobs in this local database-only restore are unavailable: 999
  absent and three hash-mismatched.
- On 2026-08-14 two controlled `Product Image.image` samples were created
  through Frappe on the local source, one public and one private. Both 68-byte
  files migrated through the real F15 subprocess bridge and F16 File lifecycle.
  File identity, attachment owner/field, privacy URL, byte size, MD5 hash,
  physical target blob, and repaired Attach Image value all passed. An
  idempotent rerun returned both files as existing and passed the same checks.
  The local inventory is now 1,004 File rows. Only the two controlled samples
  are byte-valid; 999 originals are absent and three originals have stale/wrong
  bytes. The selective smoke test is diagnostic only and does not weaken the
  full-run production file gate.
  The reusable samples are `Product Image`
  `MRP-MIGRATION-PUBLIC-20260814` / File `e7238db485` and
  `MRP-MIGRATION-PRIVATE-20260814` / File `54482b72ce`. Rerun only this scoped
  diagnostic with
  `essdee_yrp.migration.live.run_attachment_smoke_test`; never use it as a
  substitute for the full Dry Run.
- On 2026-08-14 the complete local rehearsal was rerun with the unavailable
  backup blobs explicitly audited. It passed 3,437,048 / 3,437,048 parent
  documents with zero transformation failures, validated 1,524 external Link
  values, preserved/derived 240,390 required values, audited the known
  historical blanks, accounted for all 1,004 File metadata rows and all 846
  unique content keys, and checked all 171 F15 naming-series counters. Live
  migration merges `tabSeries` by SQL using
  `GREATEST(target_current, source_current)` so it can never reduce an existing
  counter or generate a duplicate historical name.
- Business logic has not yet been ported for the 150 schema-created DocTypes.
  Do not describe the Finishing, Cutting, Sewing, Product, or Time and Action
  features as migrated until their plan slice passes its logic gate.

Open changed DocTypes: none.

The final decision was Repost Item Valuation: Essdee YRP owns the optional
`via_landed_cost_voucher` compatibility checkbox. Production API currently has
no MRP caller that sets it to 1. Base YRP remains solely responsible for
generating its Lot and Received Type stock-dimension fields.

## Canonical audit files

These bench-level reports contain the exact field-by-field evidence:

- `docs/superpowers/specs/2026-08-12-production-api-doctype-parity-table.html`
- `docs/superpowers/specs/2026-08-12-production-api-changed-doctype-details.html`
- `docs/superpowers/specs/2026-08-12-production-api-action-doctypes.md`
- `docs/superpowers/specs/2026-08-12-production-api-resolved-doctype-mappings.md`

The HTML parity table intentionally shows only `Created` and still-open
`Changed` rows. Resolved equivalent/renamed records are documented separately.

## Confirmed renamed concepts

| Production API | F16 decision |
|---|---|
| Vendor Bill Tracking | Bill Tracking |
| Vendor Bill Tracking Assignment Detail | Bill Tracking Assignment Detail |
| Essdee Raw Print Format / Detail | ZPL Raw Print Format / Detail |
| Essdee Debit | Debit |
| GRN Item Type | Received Type |
| Stock Settings | YRP Stock Settings |

Do not recreate the old names or count these as missing.

## Stock-dimension design

Stock dimensions are metadata-driven in base YRP. Use
`yrp.stock.dimensions`; never hardcode only `lot` or `received_type` in new
stock flows.

- Every configured dimension is generated on stock child DocTypes.
- The production-group dimension is also generated on relevant operational
  parents.
- `Work Order Deliverables` and `Work Order Receivables` receive dimensions
  through this engine, not through direct fields in their JSON.
- Work Order child rows inherit the header production group when missing and
  receive configured defaults such as the default Received Type.
- Delivery/receipt/rework matching must use the complete stock bucket: Item
  Variant + Warehouse + every configured stock dimension.
- On `essdee_yrp.site`, the live configured dimensions are `lot` (production
  group and valuation) and `received_type` (valuation). The generated fields
  are present on Delivery Challan Item, Goods Received Note Item, Stock Entry
  Detail, Stock Update Detail, Stock Reconciliation Item, Work Order
  Deliverables, Work Order Receivables, and Inspection Entry Item, as well as
  the supporting ledger/bin/reservation/repost DocTypes.
- Data migration must copy configured dimension values by fieldname on every
  stock-bearing row. Source `lot` maps directly; source `received_type` values
  linked to `GRN Item Type` map to the equivalent target `Received Type` name.
  Reconcile migrated balances by Item Variant + Warehouse + the complete
  configured dimension bucket, never by Item and Warehouse alone.
- Purchase Order Item receives every configured stock dimension through the
  base YRP engine. On this site that creates optional `lot` and `received_type`
  Links. Purchase Order must not ask users to enter Received Type; that display
  rule belongs to the later UI phase. Its explicit
  `hash` autoname setting was removed from base YRP to match Production API's
  empty setting; Frappe still automatically assigns every child row a unique
  hash as its normal `name`. Base YRP also preserves row-level
  `delivery_location`, the original `expected_delivery_date`, and
  `additional_parameters`. Source `pending_qty` and `cancelled_qty` map to the
  existing F16 `pending_quantity` and `cancelled_quantity`. The remaining F16
  quantity, UOM, grouping, amount, and combination structure is approved, so
  Purchase Order Item is closed in the changed list.
- Delivery Challan is closed in the changed list. Essdee YRP owns the 15
  Production API-only fields plus the approved metadata overrides. From
  Location is mandatory; Is Internal Unit, Is Rework, Lot, and Includes
  Packing are enforced from Work Order; Lot is mandatory/read-only; internal
  transfer fields are conditionally visible; STE Transferred uses precision 2;
  and Vehicle No is editable after submit. Base YRP's comments, posting-time
  control, supplier/warehouse flow, totals, Production Detail, and
  `DC-.YYYY.-` naming series remain unchanged.
- Item Production Detail now includes hidden Essdee payload fields
  `compacting_details_json` and `panel_wise_cloth_mapping_json`.
- Delivery Challan Item includes the four source business fields
  `additional_goods_value`, `additional_parameters`, `is_calculated`, and
  `stock_value`. Source `item_type` is deliberately not duplicated: its old
  `GRN Item Type` link maps to the generated `received_type` stock dimension.
  Its stronger base metadata and Essdee precision 3 for `secondary_qty` remain.
- Goods Received Note Item includes the six source fields `received_types`,
  `rework_quantity`, `secondary_qty_json`, `ste_delivered_quantity`,
  `stock_uom_rate`, and `tax`. Stock Entry Detail includes Essdee JSON field
  `set_combination`.
- Delivery Challan Item, Goods Received Note Item, and Stock Entry Detail keep
  every configured stock dimension generated through base YRP. Explicit
  `hash` remains on the two DC/GRN child tables: blank naming also falls back
  to a random row name, while explicit `hash` adds collision retry.
- Stock Reservation Entry, Stock Reconciliation Item, and Stock Update Detail
  are closed in the changed list. Their F16 Warehouse/dimension/status and
  calculated-field differences are intentional generic base-YRP stock
  controls, not Production API gaps.
- Goods Received Note is closed after adding 40 Production API-only fields
  through Essdee YRP. Obsolete `essdee_yrp_stock_entry` and
  `essdee_yrp_stock_entry_created` were deliberately excluded. Base YRP's
  optional Warehouse-derived Delivery Location, default-zero Freight Charges,
  and mandatory editable generated Lot dimension remain approved.
- Stock Entry is closed after adding six Production API-only fields through
  Essdee YRP. Essdee Property Setters add `Stock Dispatch` to Purpose and make
  Additional Amount editable only for `Send to Warehouse`. Base YRP continues
  to fetch Terms and Condition from `to_supplier.po_terms_and_condition`, with
  no edit-after-submit override.

### Inspection and rework decision

Multiple Inspection Entries are allowed against one submitted GRN. Submitting
an Inspection Entry does not move stock; an authorized `Convert Stock` action
does. Stock balance prevents over-conversion.

Rework Work Orders must not store an arbitrary first Inspection Entry Item.
When rework choices are loaded, base YRP queries all converted Inspection Entry
rows against the parent Work Order's submitted GRNs and aggregates quantity by:

`Source GRN Item + Item Variant + Warehouse + complete target stock-dimension bucket`

The Work Order Deliverable stores only `source_grn` and `source_grn_item`.
`source_inspection_entry_item` has been removed. Inspection detail remains
queryable from the GRN chain when needed.

## Confirmed completed decisions

### Base YRP

- `Item BOM` and `Item BOM Attribute Mapping` were strengthened for source
  compatibility while retaining F16 behavior.
- `Supplier` owns `is_company_location` and `terms_and_condition`.
- `Process` owns the generic `is_manual_entry_in_grn` flag. Packing is not a
  base YRP concept.
- Work Order Expected Delivery Date is mandatory but editable.
- Work Order fetches/stores the generic manual-entry flag, Supplier
  internal-unit status, and Supplier Terms and Condition. Terms remain editable
  after submit.
- Work Order Deliverables/Receivables use generated stock dimensions.
- Stock Reconciliation posting date/time are read-only until
  `edit_posting_date_and_time` is checked.
- Production Order `naming_series` uses the Production API structure: visible,
  mandatory Select with `PPO-` and no default. The current editable submitted
  Delivery Date and Don't Deliver After behavior is approved.
- Current F16 Production Order Detail structure is approved without changes.
- Existing F16 structures were approved for Item, Item Price, Item Price Value,
  Terms and Condition, Process Cost Value, Stock Update, Stock Ledger Entry,
  Bin, and Work Order Calculated Item.
- Purchase Order owns the reusable supplier/contact, delivery destination,
  address, and print-detail fields in base YRP. Supplier/address/contact
  snapshots are populated server-side and destination type is validated. The
  F16 warehouse, totals, naming, receipt-status, and Terms behavior remains
  approved. Purchase Order Item is resolved separately through the base
  dimension engine and approved row-level field mappings.
- `Purchase Order.items` remains hidden for the approved grouped-item UI. Its
  metadata is intentionally not `reqd`, because Frappe rejects a hidden
  mandatory field without a default; `PurchaseOrder.validate_items` remains the
  authoritative server-side requirement and rejects an empty order.

### Essdee YRP

- The 150 missing schemas were created here because they are Essdee business
  DocTypes unless later review promotes a reusable concept to base YRP.
- Essdee owns `Process.includes_packing`, `Work Order.includes_packing`, the
  Purchase Order `default_lot`/`sd_lot` Custom Fields, linked-Lot APIs/UI/audit,
  and the GRN linked-Lot policy. Source `Purchase Order Lot` maps to Essdee
  child `Lot MultiSelect`. The post-model-sync migration is prepared to copy
  legacy rows idempotently while retaining the old physical table; it has not
  been executed because no site migration was authorized in this work session.
- YRP's canonical pure BOM entry point is
  `calculate_bom_for_variant_demands`. The old pure `calculate_lot_bom` name is
  retained only as a compatibility alias for the separate `yrp_essdee` app;
  it performs no Lot lookup or persistence. Essdee Lot persistence calls the
  neutral entry point after checking write permission and derives variant
  demands only from the saved Lot; client-supplied rows are never trusted as
  calculation input.
- Process Cost Lot-dependent field behavior remains an Essdee customization.
- `MRP Settings` follows target capability, not blind source parity. Migrate
  only settings whose referenced feature/DocType exists on `essdee_yrp.site`;
  exclude AQL, CLS, notification, Sewing Plan, and obsolete remote-site API
  key/secret/URL settings rather than creating absent modules for them.
- Supplier source fields `supplier_users` and `price_html` remain Essdee-owned.
- Work Order has Essdee field `no_receivables`.
- Work Order Item is never auto-selected. Lot + Process produce a filtered Item
  list; the user selects an Item, and Essdee derives/stores the matching Item
  Production Detail.
- Work Order calculation has two Essdee Desk routes. An explicitly
  `Process.is_cloth_process` Process uses **Calculate Fabric Deliverables**;
  every other saved draft non-rework garment Work Order uses the F15-compatible
  **Calculate Items** dialog. The garment route reads the process-appropriate
  Lot quantity, supports Cutting/Stitching/Packing, IPD extra processes and
  Process groups, and writes calculated deliverables/receivables plus cutting
  tracking JSON.
- Migrated approved IPDs may predate generated `IPD Process Matrix` records.
  **Generate / Regenerate IPD Process Matrix** rebuilds derived matrices without
  changing the approved IPD itself. Invalid variants are returned individually;
  matrix generation must never invent missing Cutting mappings or silently
  under-demand cloth.
- Lot Transfer uses Essdee child `Lot Transfer Item`, includes the hidden
  `finishing_plan` link, and unlocks posting date/time only through its checkbox.
- Purchase Invoice receives the nine approved Production API ERP/GST/ITC fields
  as Essdee Custom Fields. Base `bill_tracking` replaces source
  `vendor_bill_tracking`; the old field is not recreated.
- Purchase Invoice Item receives direct Essdee fields `lot` and `expense_head`
  (not stock dimensions), while its existing `item_group` is mandatory. Current
  F16 Amount, Qty precision, and `set_combination` behavior are retained.
- Production Order receives the 13 requested Production API fields as Essdee
  Custom Fields. The F16-only `item_details` field is retained.
- Work Station receives the mandatory `action` Link through Essdee YRP while
  retaining the F16 workstation-name naming model and other F16 fields.
- Lot stores hidden `lot_time_and_action_details` rows using the Essdee-owned
  `Lot Time and Action Detail` child table; current F16 fabric tables remain.
- Production Ordered Detail receives Essdee field `lot`; `quantity` uses the
  source `Int` type through an Essdee Property Setter, while the F16 reference
  fields remain. Base `reference_doctype` is a Link to DocType so its
  `reference_name` Dynamic Link satisfies the Frappe 16 schema contract.

## Important exclusions and pending plans

- Do not add old remote API credential fields or absent-module configuration
  fields to MRP Settings.
- No data patch is needed for those settings fields; target data will be reset
  before fresh entries are created.
- The 150 created schemas still require controller/JS/report/permission review
  before they can be considered fully migrated features.
- The migration engine, live adapters, read-only document dry run, supporting
  master rehearsal, attachment smoke test, and full local rehearsal are
  implemented. The actual historical write migration, final reconciliation,
  production cutover, and rollback execution are still pending.
- Current F15 schema analysis is zero-blocker after adding the Essdee-owned GRN
  marker field. A fresh Dry Run is still required because the earlier rehearsal
  belongs to its frozen source snapshot.

## Data-migration execution design

Use one dependency-ordered, resumable migration engine rather than one copied
Python script for every DocType and rather than direct cross-database inserts.

1. A migration manifest classifies every source DocType as `identity`,
   `mapped`, or `custom` and declares its dependency phase.
2. `identity` DocTypes use the generic extractor/loader. The engine copies the
   parent document and child rows from paginated source exports while preserving
   names, links, docstatus, timestamps, owners, amendments, and file references
   where the target contract allows it. No per-DocType Python function is
   written for these unchanged schemas.
3. `mapped` DocTypes use declarative source-to-target DocType, field, child
   table, and value mappings. Approved examples include `GRN Item Type` →
   `Received Type`, `Stock Settings` → `YRP Stock Settings`, and
   `pending_qty` → `pending_quantity`.
4. A dedicated transformer is written only for a `custom` DocType whose data
   must be calculated, split, grouped, or rebuilt and cannot be represented by
   the declarative mapping.
5. The historical target loader uses controlled database-level batched upserts,
   not Frappe document insertion/controllers. It records source identity and
   checkpoints and is safe to resume without duplicating a completed document.
   A dry run and a disposable-site rehearsal precede the final load.
6. Verification compares document/child counts, broken links, totals,
   amendment chains, files, and stock balances using Item Variant + Warehouse +
   the complete configured dimension bucket.

The target must never retain a Link option to the legacy `GRN Item Type`
DocType. Migrate its master records first into `Received Type`; then copy the
same linked value/name into target `received_type` fields. The 150-schema port
already applies this option remap automatically. A 2026-08-13 packaged-file and
live-site audit found zero DocFields or Custom Fields on `essdee_yrp.site`
whose Link options reference `GRN Item Type`; the corresponding target links
reference `Received Type`.

### Migration implementation status — updated 2026-08-14

- Confirmed source site: `mrp3.site`; confirmed target directory/site:
  `essdee_yrp.site`. There is no `sd_yrp.site` directory in this bench; that was
  treated as voice transcription of Essdee YRP.
- Planner, strict transformers, dependency-cycle grouping, content-hash
  checkpoint/resume, dry-run write guard, F15 source bridge, F16 SQL target
  adapter, supporting-master/file/series phases, and verification are
  implemented under `essdee_yrp/migration/` and `scripts/f15_source_bridge.py`.
- `scripts/mrp_data_migration.py` currently performs schema-only analysis. It
  intentionally has no site adapter and reports `reads_site_data=false` and
  `writes_site_data=false`. Live/rehearsal execution is in
  `essdee_yrp.migration.live`; the CLI's scope does not describe the full
  implementation.
- Essdee-owned `MRP Data Migration` and child `MRP Data Migration Detail` are
  packaged on the `MRP` branch as the run/audit surface. Analyse, Dry Run,
  Migrate, and Verify are wired through server-owned status gates and System
  Manager permission.
- The complete local read-only rehearsal processed 3,437,048 documents with
  zero transformation failures and validated supporting masters, links,
  required values, File metadata/content gates, and 171 series counters.
- Live historical target writes have not started.
- The current schema-only plan sees 260 source DocTypes and 318 target
  DocTypes: 225 identity, 32 declaratively mapped, and three custom. It stops on
  the one newly introduced Goods Received Note field blocker. No blocker is
  silently dropped.

### Spine field-value gate — 2026-08-14

The Spine master-data gate must compare field values and child-table values,
not only document counts. Canonical audit:
`docs/audits/2026-08-14-sd-yrp-spine-field-value-audit.md`.

Confirmed and fixed mapper gaps are: Production Ordered Detail direct `lot`,
supported MRP Settings values, Supplier Users retained on
both Supplier and Warehouse, Address GSTIN, and User Telegram ID. Production
Order otherwise covers all 25 source parent fields and all five child tables.
IPD `stage` deliberately maps to both `in_stage` and `out_stage`; 808 live
common rows matched that transformation.

Historical migration separately includes the complete Time and Action graph,
including every `Lot Time and Action Detail`. This does not silently broaden
the ongoing Spine real-time consumer contract.

User sync remains a safe bootstrap rather than a credential clone. Never copy
passwords, API credentials, reset keys, sessions, last-IP/login/activity, or
social-login state across sites. Apply the two newly packaged Essdee Custom
Fields and complete an ordered Spine resync before historical migration. The
audit itself performed no bulk republish, historical migration, scheduler
change, or destructive cleanup.

## Verification status through 2026-08-13

- The read-only pre-remediation check found 0 rows in the legacy
  `tabPurchase Order Lot` table and 0 rows in `tabLot MultiSelect` on
  `essdee_yrp.site`. The copy routine therefore has no current relationship
  data to move, but remains in place for any site that does contain legacy
  rows. No copy or schema migration was executed in this session.
- Fresh source inventory: 260 JSON files / 259 unique DocTypes. All 259 are
  accounted for by 251 exact target names plus the eight approved renamed
  replacements; no unaccounted source DocType remains.
- The source-parity verifier accounts for all 150 schema concepts: 65 parents,
  85 child tables, and 11 approved Link-option remaps. This includes the
  `Purchase Order Lot` → `Lot MultiSelect` replacement and the two current
  finishing packing fields.
- All 57 removed same-structure DocTypes still match on data-bearing field
  presence, field type/options, and key DocType flags. All 45 originally
  changed DocTypes have an explicit resolved mapping.
- The broad base stock-engine regression suite passes 38/38 with the complete
  configured dimension bucket (`lot` + `received_type`).
- Purchase Invoice integration coverage passes 8/8 after its PO/WO builders
  were aligned with current mandatory GRN address snapshots and the Essdee
  Lot/Process/Item selection contract.
- Across the final migration-focused verification run, 123 distinct selected
  tests passed: 42 Essdee schema/customization tests and 81 base YRP
  stock/procurement/terms/work-order/invoice tests.
- Every generated stock-dimension Custom Field is explicitly owned by the
  `YRP` module. The Essdee fixture audit found zero YRP-managed dimension
  fields, zero YRP E-Waybill fields, and zero duplicate Custom Field names.
  Recalculate raw fixture counts after later field additions instead of
  treating an older count as a contract.
- Missing-schema structural tests passed after creating the 150 DocTypes.
- Purchase Order Item schema/default/stock-dimension tests pass after its base
  YRP resolution; the existing Purchase Order price-validation tests also pass.
- Delivery Challan Essdee metadata/fetch tests and naming-series tests pass.
  The legacy base internal-transfer integration module is currently blocked in
  its setup by the already-documented live Lot/Item mismatch and by the current
  Process Cost Value Item requirement; none of its Delivery Challan assertions
  run before those setup failures.
- Focused migration child tests pass for the two IPD payload fields, four
  Delivery Challan Item business fields, six Goods Received Note Item fields,
  Stock Entry Detail `set_combination`, and complete configured stock-dimension
  coverage on all three stock-transfer child tables.
- Goods Received Note customization tests pass for all 40 Essdee fields,
  excluded obsolete stock-entry references, exact source metadata, and the
  three approved base-YRP field decisions.
- Stock Entry customization tests pass for all six Essdee fields, Purpose and
  Additional Amount metadata, unchanged base Terms behavior, and complete
  stock-dimension coverage on Stock Entry Detail.
- Repost Item Valuation tests pass for the Essdee-owned
  `via_landed_cost_voucher` compatibility checkbox and prove that every
  configured dimension on that DocType remains generated and marked by base
  YRP. The focused structure, dimension, and migration-child suites pass 11/11.
- Production Ordered Detail now passes Frappe's Dynamic Link schema validation;
  focused reviewed-production customization tests pass after reloading only
  that DocType on `essdee_yrp.site`.
- Focused Work Order, Supplier, Terms, stock-dimension, Lot Transfer, and
  Essdee Work Order selection tests passed during implementation.
- The Essdee frontend production build passed after Work Order selection work.
- Inspection-to-rework aggregation has focused coverage proving that several
  converted inspections become one GRN/dimension bucket without saving an
  Inspection Entry reference.
- A broader legacy rework integration test is currently blocked before the
  changed path by live Essdee test data: Item `YRP E2E 30s Cotton Yarn` is not
  valid for Lot `YRP-AISH-11042026-01`; that Lot currently permits
  `AISHWARYA PRINT`. Do not misreport this as an inspection-query failure.

## Query-only sample rehearsal — 2026-08-17

- A target backup was taken before sample writes:
  `20260817_154345-essdee_yrp_site-database.sql.gz`.
- The rehearsal used the effective live metadata from F15 `mrp3.site`, not
  only repository JSON. This is required because source DocType metadata has
  historical migration/Property Setter drift, including Lot Time and Action.
- Target metadata was reloaded only from the current `yrp/develop` and
  `essdee_yrp/MRP` definitions. No full `bench migrate` was run.
- The final capped run migrated at most 20 parents per source DocType through
  direct SQL upserts, preserved source parent/child names, and immediately
  read every stored value back through SQL.
- Final result: 1,469 parents, 18,633 child rows, and 396,709 field values
  verified; zero DocTypes failed. The repeat run updated 1,446 existing sample
  parents and inserted 23 parents that had been rolled back by the first
  diagnostic pass, proving name-based idempotence without duplicates.
- Critical focused samples passed: Production Order (20 parents/236 children),
  Item BOM Attribute Mapping (20/247), Lot (20/778, including live Lot Time and
  Action rows), Time and Action (20/472), Work Order (20/5,600), Goods Received
  Note (20/553), Lot Transfer (20/75), and MRP Settings (1/5).
- MRP Settings migrated only supported values: three Purchase Invoice series
  rows and two Production Order action-role rows. AQL, CLS, notification
  automation, Sewing Plan configuration, and obsolete YRP remote credentials
  were not stored.
- The full read-only external-master audit checked 1,534 distinct values and
  passed. The controlled full load still needs to copy 22 Addresses, two
  Roles, two Users, one Email Account, one Letter Head, and one Print Format;
  these are supporting Frappe masters rather than Production API DocTypes.

Unresolved before the full destructive rehearsal:

1. The Stock Reservation Entry voucher-type mapping is now decided: base YRP
   exposes `voucher_type` as a generic Select, while Essdee's scoped Property
   Setter retains the base `Work Order`/`Stock Update` values and adds the
   legacy `Packing Slip` value used by all 322,187 source rows. The query-only
   migration can therefore preserve `voucher_type` without a fake Packing
   Slip DocType. Base YRP now also stores `voucher_no` as plain Data, matching
   F15 and avoiding an invalid Dynamic Link to the nonexistent Packing Slip
   DocType. All historical voucher references can be preserved unchanged;
   280,986 rows additionally have a valid `stock_entry` and 41,201 do not.
2. The restored local source contains encrypted MRP Settings values for
   `erp_api_secret` and `sales_api_secret`, but its site encryption key cannot
   decrypt them. They were not exposed or copied by the sample. The production
   encryption key/config or an explicit secret re-entry decision is required.
3. File metadata/blob migration was intentionally excluded from this
   query-only capped sample. The production public/private file archives must
   be available for the attachment rehearsal and hash/size/privacy checks.
4. The current target was not erased. A full reset/load still requires the
   owner's explicit evening authorization and a fresh backup immediately
   before deletion.

## Resume checklist

1. Confirm `apps/essdee_yrp` is on `MRP`, confirm `apps/yrp` remains on
   `develop`, and inspect all relevant working trees.
2. Preserve all unrelated owner changes; never reset the repositories.
3. Read `docs/MRP_BRANCH_HANDOFF.md`, this history, and the referenced plans
   and audits.
4. Confirm the working site is `essdee_yrp.site`.
5. Require zero schema blockers; keep the protected closed-Work-Order Sewing
   Details GRN behavior in the later business-logic plan.
6. Repeat the read-only dry run against a frozen current source before any
   historical writes.
7. For every decision, record ownership, schema mapping, logic impact, data
   mapping, tests, and whether the audit row can be removed.
8. Reload only the changed DocType metadata when required. Never run a full
   site migration without explicit owner approval.
9. Run proportionate tests, diff checks, and UI/build verification.
10. Update the handoff before ending a migration session.

## Commit policy

The owner explicitly authorized committing the intended Essdee migration work
on `apps/essdee_yrp` branch `MRP` on 2026-08-14, followed by switching only that
app to `develop`. This authorization does not cover `apps/yrp` or the F15
`production_api` working tree. Never commit or discard changes in those
repositories implicitly.
