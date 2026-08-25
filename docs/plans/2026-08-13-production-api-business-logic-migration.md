# Production API Business-Logic Migration Plan

Date: 2026-08-13; source status refreshed 2026-08-14
Target site: `essdee_yrp.site`
Branches: `apps/yrp` → `develop`, `apps/essdee_yrp` → `MRP`
Status: Plan ready for owner review; business-logic implementation has not started

Current concise handoff: `docs/MRP_BRANCH_HANDOFF.md`. The source snapshot in
this plan is evidence from its date, not a permanent pin.

Current server-side ownership/port classification:
`docs/plans/2026-08-18-production-api-business-logic-classification.md`.

## Objective

Migrate the required Frappe 15 `production_api` behavior into Frappe 16 without
reintroducing `production_api` as a monolith. The already-created DocType schemas
are the storage contract. This plan covers controllers, client scripts, Vue Desk
components, document-event wiring, reports, print formats, permissions, scheduled
jobs, tests, and the links between DocTypes.

Historical data migration now precedes the remaining business-logic slices, per
the owner's 2026-08-13 sequencing decision. The historical loader preserves
source state without firing incomplete F16 workflow side effects. Each business
slice is then ported and tested against the migrated records. UI migration still
follows the approved backend contract; UI code must not become the only
enforcement layer.

## Source baseline — always include the current working tree

The source of truth is the **current Frappe 15 working tree**, not only its last
commit.

- Repository: `/home/anas/frappe-15/apps/production_api`
- Branch/HEAD at the 2026-08-14 handoff: `develop` /
  `bdc8aa9349975eded7825402c8f5baa28d6e193e`.
- That HEAD adds bulk Work Order close and closed-work-order GRN behavior. It
  introduces `Goods Received Note.from_closed_wo_sewing_details`, which is the
  current F16 schema-planner blocker.
- The F15 tree is dirty with owner work in Manufacturing workspace, Work Order,
  Work Order Bulk Close, and the two Spine sync files. Preserve it exactly.
- The earlier `9c1538d0` Finishing/OCR snapshot and diff hash remain useful
  historical evidence, but they are not the current full source inventory.

The Finishing contract recorded during the earlier review still has to be
preserved when that slice is implemented:

1. Legacy OCR aggregation increments parent `packed_box` and `dispatched_box`
   totals along with per-size totals.
2. Dynamic-ratio packing uses physical packing-batch box totals for parent
   totals rather than summing size allocations.
3. The corresponding source tests must be adapted and pass in F16.

Before implementing any slice, recalculate source HEAD, dirty-file list, and
diff hash. If they changed, refresh the slice inventory before writing target
code. Never commit or reset F15 owner changes from an F16 Essdee task.

## Confirmed current state

- All current source DocType names are structurally classified. One newer
  Goods Received Note field remains a schema blocker, as recorded in the
  current handoff.
- The 150 formerly missing schemas exist: 65 parents and 85 child tables.
- Their target controllers are deliberately minimal schema stubs.
- Of the 65 created parent DocTypes, 64 have a source client script; 26 contain
  substantive client behavior rather than generated boilerplate.
- 35 created parent DocTypes have substantive controller and/or client logic.
- F16 currently has no Finishing Plan, Finishing Plan Dispatch, or Cutting
  LaySheet client scripts and no corresponding Vue Desk component bundle.
- The source Finishing UI contains 21 JS/Vue files and 4,930 lines. The source
  Cutting LaySheet/Marker UI contains six Vue files and 2,385 lines.
- The source app also contains 40 report definitions and 36 print formats. These
  must be audited as feature dependencies; a DocType is not complete merely
  because its controller imports.

Therefore, today's Finishing correction cannot be copied as an isolated two-line
patch. The F16 controller containing that calculation does not yet exist. It must
be included in a complete, tested Finishing vertical slice.

## Ownership and implementation rules

### Base `yrp`

Base YRP remains authoritative for generic behavior:

- Item/variant APIs and attribute/dependent-attribute contracts
- Supplier, Purchase Order, Work Order, Delivery Challan, Goods Received Note,
  Stock Entry, Stock Reconciliation, Bin, ledger, valuation, and reposting
- the metadata-driven stock-dimension engine
- the full stock bucket: Item Variant + Warehouse + every configured dimension
- generic submit/cancel, permission, and posting-date rules

Modify base YRP only when the migration proves that a missing seam is reusable
for every customer. Keep such a change small, independently tested, and available
for owner review. Do not commit base-YRP changes without explicit approval.

### `essdee_yrp`

Essdee YRP owns:

- cutting, bundle/panel movement, sewing, finishing, Time and Action, product
  development, labels, P&L, and company approval behavior
- the 149 Essdee-owned schemas from the created set
- hooks extending base transactions for Essdee workflows
- Essdee Desk scripts, Vue components, reports, print formats, and fixtures

No F16 runtime file may import `production_api.*`. Source helper behavior must be
adapted into `yrp` or `essdee_yrp` according to ownership.

### Renamed concepts

Every logic port must apply the approved mappings:

| F15 concept | F16 contract |
|---|---|
| `Stock Settings` | `YRP Stock Settings` |
| `GRN Item Type` / `item_type` | generated `received_type` dimension |
| `Essdee Raw Print Format` | `ZPL Raw Print Format` |
| `Essdee Raw Print Format Detail` | `ZPL Raw Print Format Detail` |
| `Essdee Debit` | `Debit` |
| `Vendor Bill Tracking` | `Bill Tracking` |
| `Vendor Bill Tracking Assignment Detail` | `Bill Tracking Assignment Detail` |

Do not recreate the legacy names merely to make imports easier.

## Required port method

Each slice follows the same order:

1. Inventory the source DocType folder completely: JSON, controller, JS,
   list JS, tests, dashboard, report, print format, hooks, public components,
   patches, and external helper imports.
2. Write a source-to-target call map. Compare target helper **signatures and
   return shapes**, not only function names.
3. Port the source tests first and make their imports target the intended F16
   owner.
4. Implement server behavior and authoritative validation.
5. Add document-event hooks for interactions with base-YRP DocTypes; do not copy
   a whole legacy base controller into Essdee.
6. Port/rewrite the Desk client and Vue components with all RPC paths changed to
   F16 paths.
7. Port required reports, print formats, and Jinja methods with the same slice.
8. Verify save, submit, cancel, retry/idempotency, permissions, stock postings,
   generated dimensions, and print/UI behavior.
9. Record the result in `MRP_MIGRATION_CONTEXT.md` and mark only that tested
   slice logic-complete.

## End-to-end manufacturing flow

```text
Production Order / Lot
        ↓
Work Order + DC/GRN stock movement
        ↓
Cutting Plan or Cutting Order
        ↓
Cutting Marker → Cutting LaySheet → bundles
        ↓                           ↓
panel/bundle movement        label request → cutting GRN
        ↓                           ↓
quality / recut / sewing → packing Work Order
                                   ↓
                           Finishing Plan
              inward / packing / return / rework / transfer
                                   ↓
                      Finishing Plan Dispatch
                                   ↓
                          Stock Entry / OCR / P&L
```

Every arrow is a tested contract. The test must prove both the forward mutation
and its cancellation/reversal path.

## Slice 1 — shared compatibility layer

Build only the shared helpers required by the first business slice:

- JSON normalization and set-combination key helpers
- variant attribute lookup and dependent-stage attribute construction
- item grouping helpers
- Finishing Plan row serialize/deserialize helpers
- process-to-Work-Order lookup
- dynamic packing constants, batch normalization, and piece aggregation
- source-to-target stock adapter using F16 keyword stock dimensions

For every source helper call, compare its source signature with the F16 target.
Known high-risk differences include `make_sl_entries`, `get_stock_balance`,
variant construction, stock cancellation, Warehouse versus Supplier storage,
and dimension arguments. Do not pass F15 positional arguments into a same-named
F16 function without a signature test.

Acceptance:

- helper unit tests pass without database fixtures where possible
- import smoke test resolves every target symbol
- `rg "production_api\." apps/essdee_yrp` finds no newly ported runtime import
- Lot and Received Type always travel through the complete dimension mapping

## Slice 2 — Finishing Plan + Finishing Plan Dispatch (first priority)

This is one atomic feature slice. Do not mark one DocType complete without the
other and their Work Order/GRN/DC/Stock Entry seams.

### Finishing Plan creation and refresh

1. Submitting an Essdee Work Order with `includes_packing = 1` queues one
   idempotent Finishing Plan creation job.
2. The plan is seeded from the Lot, Item Production Detail, relevant Work Orders,
   calculated items, submitted GRNs, Received Type buckets, cutting quantities,
   rework/rejection records, and packing configuration.
3. Repeated jobs return the existing active plan; they must not create a
   duplicate.
4. Cancellation reverses linked stock effects and removes/rebuilds only the
   records that the cancelled Work Order owns.
5. On load, the plan rebuilds the UI payloads for inward, finishing quantity,
   packing, return, rejection, ironing excess, old-Lot transfer, incomplete
   transfer, OCR, stock balance, and consumption.

### Packing, returns, rework, and transfers

- Preserve both legacy fixed-ratio and current dynamic-ratio packing.
- Dynamic packing rows carry packing calculation version, batch identity,
  box count, piece count, size breakup, dispatched boxes, and cancellation
  history.
- Create/cancel GRN, Delivery Challan, Stock Entry, Lot Transfer, material
  receipt, pack return, loose-piece conversion, and rework through target F16
  APIs and complete dimensions.
- Alternative Plan creation/update must retain the F15 Lot, Production Order,
  Work Order, quantity-transfer, price, and traceability contracts.

### Dispatch

1. `fetch_fp_items` returns only Finishing Plans with a positive undispatched
   balance.
2. Saving a draft preserves the operator's size quantities, colour grid, and
   valid batch selections while refreshing live availability.
3. Removed/invalid batch rows are pruned on reload.
4. Negative quantities, quantities above live balance, zero-only selections,
   and an empty dispatch are rejected server-side.
5. A dispatch snapshot is frozen into child rows for audit and printing.
6. Submitting updates per-plan dispatch totals and batch dispatched-box totals.
7. `Dispatch Stock` creates the linked F16 Stock Entry using from/to locations,
   vehicle, goods value, and every configured dimension.
8. Cancelling the dispatch cancels the linked Stock Entry, batch quantities,
   plan totals, and dispatch logs exactly once.

### OCR and P&L

- Preserve `Planned → Dispatched/Fully Dispatched → OCR Requested/OCR Completed
  → P&L Submitted` behavior and server-side authorization.
- Apply today's working-tree OCR total correction.
- Several packing/dispatch records must aggregate without double counting.
- OCR completion locks business mutation server-side; JS read-only/hide behavior
  is presentation only.
- P&L upload/list/delete is allowed only under the approved role/status contract
  and retains File/document ownership.

### Desk and print dependencies

Port the full Finishing component family, not only the two form JS files:

- 21 Finishing JS/Vue source files
- Finishing Plan and Dispatch form/list scripts
- `frappe.production.ui` wrapper registrations
- Finishing Plan Inward, OCR, and Finishing Plan Dispatch print formats
- required Jinja methods and report endpoints

The F16 client must call `essdee_yrp.*`/`yrp.*` methods only.

### Mandatory regression evidence

- all source Finishing Plan and Finishing Plan Dispatch tests, adapted for F16
- source `test_dynamic_packing.py` cases relevant to this slice
- committed `9c1538d0` draft-preservation tests
- today's two uncommitted OCR-total tests
- one legacy packing plan, one dynamic plan, and one mixed legacy+dynamic
  dispatch
- draft save/reload; submit; stock dispatch; cancel; repeat-cancel guard
- multi-GRN/multi-batch aggregation
- live Desk load, browser console audit, save/reload, and print preview

## Slice 3 — cutting chain and label-to-GRN flow

Port together:

- Cutting Order, Cutting Order Detail, Cutting Plan
- Cutting Marker
- Cutting LaySheet and its parent adapter
- Cutting Laysheet Planner/optimizer
- Cut Bundle Movement Ledger and bundle/panel child tables
- the six Cutting LaySheet/Marker Vue components
- cutting reports, movement charts, label ZPL, and print formats

### Required label flow

1. User generates bundles from the submitted parent/marker definition.
2. `Print Labels` checks duplicate active GRN, grammage tolerance, approver role,
   bundle state, stock availability, and required Work Order receivables.
3. If approval is required, save `Approval Pending`; an authorized user approves
   before printing.
4. The server builds the ZPL and, for a Work-Order-based Cutting Plan, creates
   and submits exactly one cutting GRN, posts/reclassifies cloth stock, updates
   parent completion, and creates the bundle movement ledger.
5. The laysheet stores the GRN link before the print response is returned, so a
   printer/browser failure cannot leave an untraceable active GRN.
6. QZ success marks `Label Printed` and records print time. A retry reuses the
   same GRN and label payload; it never creates a second GRN.
7. Revert/Cancel is blocked after panel/accessory movement. Otherwise it cancels
   the GRN, reverses cloth stock and bundle ledger, recalculates the cutting
   parent, clears the link, and returns to `Bundles Generated`/`Cancelled`.

This retains the owner's rule—attempting the label workflow creates the GRN—
while closing the F15 orphan-GRN risk where the server creates the GRN before
QZ success but the browser stores the link only after printing.

## Slice 4 — panel movement, inspection, rejection, and recut

Port together:

- Cut Panel Movement, Cut Bundle Edit, Cut Bundle Movement Ledger
- Essdee Quality Inspection + AQL Level
- GRN Rework Item, Recut and Print Panel, WO Recut

Required behavior:

- fetch only unmoved bundle/panel balances
- create target Stock Entry/DC/GRN with complete dimensions
- prevent over-movement and duplicate consumption
- Quality Inspection creates the mapped F16 `Debit`, not `Essdee Debit`
- all converted/reworked/rejected quantities remain traceable to source GRN and
  source GRN item; never store an arbitrary first Inspection Entry row
- cancel/revert restores the exact source bucket

## Slice 5 — sewing and Time and Action

Port together:

- Sewing Plan and its child tables/data-entry APIs
- Action, Action Master, Action Master Template, Work Station Action
- Time and Action, Gantt Chart, Settings, and related child tables
- Action/Work Station customization already planned separately
- seven Time and Action reports and required Gantt assets

Verify schedule creation, revisions, completion/revert, user/role access,
department/work-station capacity, sewing data entry cancellation, consumption,
daily/monthly summaries, and print output.

## Slice 6 — product, finished goods, labels, pricing, and profitability

Port in dependency order:

1. Product and Product Release masters, uploads/images, measurements, colours,
   categories, and tech-pack print formats.
2. FG Item Master/Template/Settings/size masters and sync behavior.
3. FG Stock Entry through the F16 stock engine.
4. Box Sticker Print and Sales Piece Sticker Print using `ZPL Raw Print Format`.
5. PPO Price Request and Lot price overrides.
6. Lotwise Item Profit, templates, P&L document, and comparison reports.

File upload/delete APIs require permission, path, file-owner, and attachment
tests. Printer RPC must never trust a client-supplied format or quantity without
server validation.

## Slice 7 — remaining utilities and cross-cutting integrations

Audit and resolve:

- Item Conversion against F16 stock signatures and dimensions
- Stock Summary; reuse base stock reports where stronger/current
- Shortened Link and Signature Jinja helpers
- Telegram approval request/settings/routes and server authorization
- notification hooks and default posting-time behavior
- hourly reposting and daily task: reuse base scheduler behavior where already
  present instead of registering a duplicate job
- all remaining reports, print formats, fixtures, roles, and DocType permissions

Source sync-producer hooks are **not** copied into the F16 consumer app. Data
migration/synchronization uses the separately approved Spine/migration design.

## Logic-bearing DocType checklist

These 35 created parent DocTypes were identified as having substantive source
controller and/or client behavior. Child-table behavior is verified with its
owning parent.

| Group | DocTypes |
|---|---|
| Workflow masters | Action Master, Action Master Template, Time and Action, Time and Action Gantt Chart, Telegram Approval Settings |
| Cutting | Cutting Order, Cutting Order Detail, Cutting Plan, Cutting Marker, Cutting LaySheet, Cutting Laysheet Planner, Cut Bundle Edit, Cut Bundle Movement Ledger, Cut Panel Movement |
| Quality/rework | Essdee Quality Inspection, GRN Rework Item, Recut and Print Panel, WO Recut |
| Finishing | Finishing Plan, Finishing Plan Dispatch, Box Sticker Print, Sales Piece Sticker Print |
| Sewing | Sewing Plan |
| Stock | FG Stock Entry, Item Conversion, Stock Summary |
| Product/FG | Product, Product Image, Product Release, FG Item Master, FG Item Master Template, FG Item Settings |
| Pricing/profit | PPO Price Request, Lotwise Item Profit |
| Utility | Shortened Link |

The other created parents are still checked for permissions, naming, hooks, and
references even when their source controller/client file is boilerplate.

## Verification gate for every slice

A slice is complete only when all applicable checks pass:

1. Source-to-target endpoint and helper map has zero unexplained entries.
2. Python compiles; JS/Vue bundle builds; JSON parses; diff check is clean.
3. Ported source tests plus F16 adaptation tests pass.
4. All Link options and legacy names follow the approved mappings.
5. Stock rows contain every configured dimension and reconcile by the complete
   bucket.
6. Forward, cancel, retry, and duplicate-request behavior are tested.
7. Server permissions/roles enforce every action independently of hidden UI.
8. Live `essdee_yrp.site` metadata/columns match the packaged files.
9. Desk pages render in a browser with no console error; important actions are
   clicked through against safe test records.
10. Required print formats/reports render with real sample records.
11. `apps/frappe` and `apps/erpnext` remain untouched.
12. Independent diff review finds no source behavior silently dropped and no
   blind copy of weaker legacy base behavior.

No full `bench migrate`, destructive data reset, or commit is part of this plan
without separate owner authorization.

## Data-migration and business-logic handoff gate

Before any live historical-data load:

1. Freeze the final F15 source revision and working-tree state.
2. Build dependency-ordered extract/transform/load mappings.
3. Map renamed DocTypes and `GRN Item Type` values to `Received Type`.
4. Preserve names, child-row references, docstatus, posting timestamps, owners,
   and amendment chains where the F16 contract permits.
5. Load into a disposable rehearsal site first.
6. Compare row counts, links, document totals, stock ledgers, bins, valuation,
   complete-dimension balances, and representative workflow reports.
7. Rehearse rollback before touching the final target data.

After historical-data verification, the next business-logic action is **Slice
1, followed immediately by the complete Finishing Plan + Finishing Plan
Dispatch slice**. Re-snapshot the current F15 tree first and retain the reviewed
`9c1538d0` Finishing/OCR contract while also accounting for every later source
change.
