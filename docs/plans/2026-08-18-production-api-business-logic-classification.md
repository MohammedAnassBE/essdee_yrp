# Production API Business-Logic Classification

Date: 2026-08-18
Source: Frappe 15 `production_api`, branch `fix/packing-dpr-box-count`, HEAD
`8ad0f3e18b2118387fbe16fb3b45c01c868071f5`
Target: Frappe 16 `yrp` `develop` + `essdee_yrp` `MRP`
Scope: complete business behavior for the 85 classified controllers, including
server logic, source-data queries, lifecycle/cancellation, Desk JS, Vue dialogs,
print data providers, and other view integrations that are required to operate
the workflow. Visual redesign of the separate `/web` SPA is not implied; any
workflow surface ported there must remain owned by `essdee_yrp`.

## Purpose

The schemas and historical data are present. The remaining work is not one
large controller copy. This document classifies the current F15 behavior by
the way it must enter F16:

1. reuse the stronger/current base-YRP implementation;
2. port a self-contained Essdee controller;
3. extend a base-YRP transaction through an Essdee hook/service;
4. implement a complete cross-DocType orchestration slice;
5. retain only historical storage or replace an obsolete legacy concept;
6. review an external/security-sensitive integration separately.

The classification is derived from the current Python source, hooks, call
targets, and current F16 controllers. It is not inferred from DocType names.

## Current code inventory

The current F15 server code contains:

| Area | Executable files | Non-comment code lines |
|---|---:|---:|
| DocType controllers | 85 | 35,394 |
| Non-DocType support/services | 46 | 16,189 |
| Report data providers | 40 | 6,020 |

Some of the 85 controllers contain only an index hook; they are listed
separately below. This inventory describes the source used for classification;
it is not the current target-completion status.

## 2026-08-18 implementation and verification overlay

All 85 classified source controllers now have an explicit F16 outcome: reuse
the current base-YRP behavior, an Essdee direct port, an Essdee adapter, a
tested cross-DocType orchestration, or an intentional replacement/exclusion.
The target does not copy the legacy F15 stock ledger, valuation engine, remote
stock RPC, or obsolete replacement DocTypes.

Implemented operating surfaces include the controller/service logic, required
Desk JS and dialogs, 18 operational reports, and 32 Essdee-owned print formats.
The Sewing Details Desk page includes entry, closed-Work-Order GRN, dashboard,
status, SCR, history, DPR, monthly summary, item summary, FI updates, and
consumption workflows. The separate `/web` SPA is outside this classification
unless a workflow is explicitly assigned to it.

Current local evidence on `essdee_yrp.site`:

- the complete Essdee test run passes 402/402 tests;
- all 32 print formats render against migrated documents;
- all 18 operational report providers execute against the F16 schema;
- normalized SQL parity matches F15 for Sewing Plan, Sewing Plan Order Detail,
  Sewing Plan Entry Detail, Sewing Plan Detail, Consumption Details, and Cloth
  Accessory Data;
- the Sewing Details Dashboard renders for a real System Manager session with
  no browser-console error;
- the Desk asset build, JavaScript syntax checks, Python compilation, DocType
  JSON parsing, and `git diff --check` pass.

The remaining exclusions are deliberate external contracts, not unclassified
internal controllers: remote FG OMS/DC synchronization, Telegram approval,
and global automatic notification delivery. `GRN Rework Item` remains
historical/read-only by the owner's decision; active rework uses the two F16
flows documented below.

## Classification rules

### R — Reuse current F16 behavior

Do not copy the F15 controller. Compare the required business outcome and add
only a proven missing generic seam to base YRP. This applies to generic master,
stock, valuation, procurement, and accounting behavior already owned by YRP.

### D — Direct Essdee port

The controller is Essdee-owned and does not post into the generic stock or
accounting engine. Rewrite its imports and approved renamed concepts, add
permissions, and port its tests. “Direct” does not mean blind file copy.

### A — Essdee adapter on a base-YRP DocType

The DocType/controller remains owned by YRP. Only the company-specific delta is
implemented in `essdee_yrp` through hooks, a small override, or an Essdee
service. Never duplicate the complete YRP controller.

### O — Cross-DocType orchestration

The behavior creates, submits, cancels, or reconciles several documents. It
must be implemented and tested as one vertical slice, with F16 stock dimensions,
permissions, retry/idempotency, and exact cancellation.

### X — Replaced, obsolete, or historical-only

Preserve migrated history where required, but do not reactivate the F15 runtime
implementation. Use the approved F16 replacement.

### I — Integration/security review

The behavior crosses a site/system boundary or controls files, links,
notifications, or external APIs. Port only after its production contract and
authorization rules are explicit.

## 1. Reuse current base YRP — no legacy controller copy

| DocTypes / services | Decision |
|---|---|
| `Bin`, `Stock Ledger Entry`, `Repost Item Valuation` | Use the F16 dimension-aware stock/valuation engine. Never port F15 `mrp_stock/stock_ledger.py`, `valuation.py`, or Bin mutation code. |
| `Stock Reconciliation`, `Stock Reservation Entry`, `Stock Update` | Keep current F16 controllers. Essdee may supply metadata/options, but not a second stock implementation. |
| `Item`, `Item Attribute`, `Item Dependent Attribute Mapping`, `Item Variant`, `Item Variant Attribute` | Keep YRP's generic item/variant engine. Existing Essdee yarn/fabric validation remains a downstream hook. |
| `Item BOM Attribute Mapping` | Keep the YRP matrix/BOM engine and its current `item_production_detail` relation. Essdee supplies garment/fabric adapters, not a duplicate mapping engine. |
| `Item Price`, `Process Cost` | Keep current F16 validation/workflow behavior. The reviewed F16 metadata decisions remain authoritative. |
| `Department`, `Holiday List`, `Tax Slab`, `Terms and Condition`, `Vendor Bill Delivery Person` | Current base controllers already contain the generic behavior. |
| `Notification Template` | Keep YRP notification behavior; do not port the legacy controller wholesale. Telegram approval is a separate integration. |
| `Excel Sticker Print` | Already ported in base YRP and correctly uses `ZPL Raw Print Format`. |

Before declaring these complete, run outcome-level parity tests. Function-name
parity is not the gate; current F16 behavior can intentionally be stronger than
the legacy behavior.

## 2. Existing F16 split implementations — retained and parity-tested

| Area | Current F16 position | Implemented verification outcome |
|---|---|---|
| `Lot` | Substantial Essdee controller already exists. Thirty source/target function names overlap; the F16 file also contains the approved YRP matrix/Essdee garment adapter changes. | Order calculation, Production Order links, IPD/BOM calls, Work Order links, permissions, and cancellation are covered against migrated records. |
| `Lot Template` | All 13 source function names exist in the Essdee target; changes are principally target import paths. | Target imports and live behavior are covered by the app suite. |
| Item Production Detail | Intentionally split: generic calculation/matrix logic in YRP; Essdee garment/fabric logic in `ipd_ui.py`, `ipd_validations.py`, `fabric_*`, `garment_bom.py`, and `garment_bom_matrix.py`. | The garment/packing endpoint split is implemented without copying the 1,511-line legacy controller into either app. |
| `Lot Transfer` | Rewritten in F16 to post through the dimension-aware stock engine. | Finishing trace/update and guarded posting-date behavior are implemented without restoring F15 stock-ledger calls. |
| Supplier / PO linked Lots / packing flags | Essdee hooks and services exist in `purchase_order_lots.py`, `packing_hooks.py`, and `work_order_hooks.py`. | They are regression-tested with dependent vertical slices. |

## 3. Direct Essdee controller families

These can be ported without replacing a base transaction controller. They still
require target imports, field/DocType mappings, row-level permission checks, and
adapted tests.

| Family | DocTypes / code | Important mapping |
|---|---|---|
| Time and Action masters | `Action Master`, `Action Master Template`, `Time and Action`, `Time and Action Gantt Chart` | Port as one family because Action Master calls Time and Action scheduling and Work Station lookup. |
| Cutting definition/calculation | `Cutting Order`, `Cutting Order Detail`, `Cutting Marker`, `Cutting Laysheet Planner` plus `utils/lay_optimizer/*` | These calculate/prepare cutting data. They do not own the label-to-GRN stock transaction. |
| Sticker rendering | `Box Sticker Print`, `Sales Piece Sticker Print` | Map `Essdee Raw Print Format` and its child rows to `ZPL Raw Print Format` and `zpl_raw_print_format_details`. |
| Small Essdee records | `Location`, `Lotwise Item Profit`, `Purchase Order Log` | Preserve permissions and link semantics; these are small controllers. |
| FG definition helpers | `FG Item Master Template`, `FG Item Size Range` | Port local validation/loading logic. External FG sync is classified separately as integration work. |
| Product read models | `Product Image`, `Product Release` | Local table/onload logic can move with Product, while file mutation remains security-sensitive. |
| Settings validation | `Telegram Approval Settings` | Controller validation may port with the Telegram service slice. |

`IPD Compacting` is not placed in this direct list even though it does not post
stock. Its source behavior overlaps the newer F16 fabric process/matrix engine;
it needs a function-by-function adaptation into that engine to avoid two sources
of fabric truth.

## 4. Base-YRP DocTypes that need Essdee adapters

These source controllers mix generic transaction logic with Essdee behavior.
The target implementation must keep the YRP controller and port only the listed
company delta.

| Base DocType | Essdee-owned delta to implement or finish |
|---|---|
| `Production Order` | PPO approval/change requests, quantity/ratio transfer history, Lot creation/linking, alternative-plan transfer, price overrides, Box Sticker price propagation, and Essdee status/comment audit. The target base controller must remain the owner of generic Production Order storage. |
| `Purchase Order` | Linked-Lot policy/audit and Essdee Lot defaults are already downstream. Reconcile only remaining Essdee item-detail/print behavior; keep generic supplier, terms, price, pending quantity, status, and address behavior in YRP. |
| `Purchase Invoice` | Keep YRP GRN billing, approval, totals, and `Bill Tracking`. Port only proven Essdee expense-head/Lot/work-order calculation deltas. Never recreate `Vendor Bill Tracking`. |
| `Supplier` | Keep YRP contacts/addresses and Bill Tracking department behavior. Essdee-only company-location/terms behavior belongs in a small downstream hook if not already covered. Do not port old remote CRUD handlers. |
| `Work Station` | Keep the generic YRP master/default validation. Add Action/Time-and-Action propagation through Essdee hooks/services. |
| `Work Order` | Keep YRP process costing, dimensions, deliverable/receivable accounting, generic rework, close permissions, and status. Essdee adds Lot-filtered item/IPD selection, packing, Box Sticker creation, Sewing/Finishing triggers, accessory-change workflow, and company audit behavior. |
| `Delivery Challan` | Keep YRP pending validation, dimensions, valuation, ledger posting, Work Order updates, and cancellation. Essdee adds cutting/panel/Finishing aggregation, return flows, and company flags. |
| `Goods Received Note` | Keep YRP PO/WO pending validation, rates, dimensions, Received Type, ledger posting, freight, rework, and cancellation. Essdee adds dynamic packing, cutting label receipt, sewing/Finishing aggregation, bundle ledger, and closed-WO sewing route. |
| `Stock Entry` | Keep YRP stock posting, rates, completion links, and dimensions. Essdee adds only Cutting/Finishing/Dispatch trace updates and company-specific guards. |
| Item Production Detail | Keep generic matrix/BOM calculation in YRP and route garment/fabric behavior to the existing Essdee modules. |

Concrete evidence for this rule: F15 GRN currently has 97 functions and F16
GRN has 72, but only eight names overlap. F15 GRN directly imports legacy stock
ledger, Finishing Plan, cutting bundle ledger, remote-site requests, dynamic
packing, and legacy item helpers. Replacing the F16 controller would discard the
new base stock and Received Type contract.

## 5. Cross-DocType orchestration slices

These must not be implemented one DocType at a time.

### O1 — Production setup and downstream triggers

`Production Order` + `Lot` + `Item Production Detail` + `Work Order` +
`PPO Price Request` + Box Sticker pricing.

Required result: one approved production context feeds the correct Lot/IPD/item,
price, quantities, Work Orders, and later cutting/sewing/finishing flows without
duplicating base Production Order or Work Order accounting.

### O2 — Cutting definition, label, and cutting receipt

`Cutting Order` + `Cutting Order Detail` + `Cutting Plan` + `Cutting Marker` +
`Cutting LaySheet` + `Cut Bundle Movement Ledger`.

The critical transaction is:

```text
Generate bundles
  -> validate approval, tolerance, source stock and WO receivables
  -> create/submit one cutting GRN through the F16 GRN contract
  -> post complete stock dimensions
  -> persist GRN link and bundle ledger
  -> render/print label
```

Retry must reuse the active GRN. Revert/cancel must reverse the exact GRN,
dimension bucket, bundle ledger, and parent quantities once.

### O3 — Bundle/panel movement and recut

`Cut Bundle Edit` + `Cut Panel Movement` + `Cut Bundle Movement Ledger` +
`Recut and Print Panel` + `WO Recut`.

These create or reverse DC/GRN/Stock Entry/ledger effects. All movement must use
the base document APIs or a small reviewed stock adapter; none may call the F15
ledger implementation.

### O4 — Quality and rework

`Essdee Quality Inspection` + F16 `Debit` + Received Type conversion + Work
Order/DC/GRN rework.

Several Inspection Entries may exist for the same GRN/item. Resolve the complete
set by source GRN/source row/dimensions when needed; never persist an arbitrary
first Inspection Entry as the business truth.

### O5 — Sewing

`Sewing Plan` + its children + the server functions under
`page/sewing_details/sewing_details.py` + Work Order + GRN.

This includes both normal sewing data entry and the protected closed-Work-Order
GRN route. The migrated `from_closed_wo_sewing_details` checkbox is storage only
until this slice adds the authoritative checks.

### O6 — Finishing and dispatch

`Finishing Plan` + `Finishing Plan Dispatch` + Work Order + GRN + DC + Stock
Entry + Lot Transfer + dynamic packing + OCR/P&L state.

This was implemented as the first owner-approved slice after the shared
compatibility layer. It includes the current F15 packing-DPR set multiplier:
size-wise pieces and total pieces use the set-item multiplier, while the
physical `total_boxes` and `pieces_per_box` values are not multiplied.

### O7 — Stock-facing Essdee utilities

`FG Stock Entry`, `Item Conversion`, and `Stock Summary` create or reverse stock
transactions. Their document/UI contracts may be retained, but every posting
must be rewritten against the F16 YRP stock engine and all configured dimensions.

## 6. Replaced, obsolete, and historical-only runtime

| F15 runtime | F16 decision |
|---|---|
| `Essdee Debit` | Use base `Debit`. Migrate/history-map names; do not port the legacy controller. |
| `Vendor Bill Tracking` | Use base `Bill Tracking` and its assignment child. Do not port the old controller. |
| `Essdee Raw Print Format` | Use `ZPL Raw Print Format`. Adapt sticker callers only. |
| `GRN Item Type` / `item_type` | Use metadata-generated `received_type` and `Received Type`. |
| `Stock Settings` | Use `YRP Stock Settings`. |
| `production_api.mrp_stock.stock_ledger`, `mrp_stock.utils`, `valuation.py` | Never port. Use the base dimension-aware engine. |
| Source `sd_yrp_sync.py` producer hooks | Do not copy into the F16 consumer. Historical migration and Spine real-time sync remain separate contracts. |
| `post_yrp_request`, `create_essdee_yrp_stock_entry`, and old **Create Stock in MRP** behavior | Removed by owner decision; no cross-bench stock RPC in the new business logic. |
| Duplicate F15 repost/daily schedulers | Reuse base YRP scheduler jobs where already present. |
| `Signature` controller helper | The required read helper already exists in `essdee_yrp.print_helpers`; no separate controller port is needed unless a missing behavior is proven. |
| `MRP Settings.post_erp_request` / `post_yrp_request` | Do not port. Keep only settings values used by installed target capabilities. |

### Resolved GRN Rework Item decision

The schema and historical records are retained, and the older migration plan
listed the controller in the quality/rework slice. A later durable YRP decision
replaced its runtime with two clearer flows:

- in-house reclassification through Inspection Entry/Received Type;
- supplier rework through Work Order + Delivery Challan + GRN.

Therefore `GRN Rework Item` is classified as **historical/read-only by default**.
Do not port its 829-line controller unless the owner explicitly reverses that
later decision after reviewing a concrete missing use case.

## 7. Integration and security-sensitive work

| Area | Why it is separate |
|---|---|
| `Product` uploads/deletes and Product images | Local read/mutation behavior is ported with attachment ownership, allowed-path, privacy, and delete-permission tests. Physical historical blobs remain a production migration gate. |
| `FG Item Master` / `FG Item Settings` | F15 posts to OMS/DC endpoints. Confirm which external systems still exist before porting remote calls. Local Item creation/sync must use F16 item APIs. |
| `Shortened Link` | Ported with expiry, document read permission, safe redirect, token-management, and unknown-token tests. |
| Telegram approval service | Global document hooks, role authorization, callback verification, replay/idempotency, and secret handling must move together. |
| Automatic notifications | F15 hooks every DocType on insert/submit/cancel. Do not add a global target hook until duplicate delivery and target Notification Template behavior are audited. |
| `api/ppo_report.py` and Python report providers | Ported with their owning vertical slices; 18 operational reports execute against the F16 schema. |

## 8. Index-only child controllers

These source files do not contain workflow behavior; most only define
`on_doctype_update` indexes:

- `Delivery Challan Item`
- `Goods Received Note Item`
- `GRN Deliverable`
- `Purchase Order Item`
- `Stock Entry Detail`
- `Work Order Deliverables`
- `Work Order Receivables`

Keep or recreate only a proven useful index through the owning F16 app. Do not
count these as business-logic ports.

## 9. Shared support-code decision

| Source module | Treatment |
|---|---|
| `dynamic_packing.py` | Port to Essdee and test with Finishing/GRN. |
| `lot_pricing.py` | Port with Production Order/PPO/Box Sticker pricing. |
| `panel_wise_cloth_mapping.py`, `panel_wise_consumption.py` | Reconcile with the existing Essdee fabric/IPD modules; retain one implementation only. |
| `utils/lay_optimizer/*` | Port with Cutting Laysheet Planner; it is calculation code, not stock posting. |
| `production_api/utils.py` | Never copy the 3,958-line utility module wholesale. Move only functions demanded by a selected slice into named Essdee capability modules, or replace them with YRP helpers. |
| `api/stock.py` | Keep only Essdee orchestration entry points that remain required; replace all stock/reservation implementation with YRP APIs. |
| `mrp_stock/*` helpers | Do not port the ledger/valuation implementation. |
| `page/work_order_bulk_close/*.py` | Adapt as an Essdee action over the authoritative F16 Work Order close API, with row permission and partial-failure tests. |
| `page/sewing_details/*.py` | Port as part of the Sewing orchestration, including the closed-WO GRN authorization. |

## 10. Implemented sequencing and release rule

1. Freeze the F15 source commit/working tree for the selected slice.
2. Build the small shared compatibility layer: JSON normalization, variant and
   attribute lookup, dimension mapping, packing helpers, and a narrow adapter
   to base YRP document APIs.
3. Keep the approved first vertical slice: Finishing Plan + Dispatch, including
   only the required Work Order/GRN/DC/Stock Entry/Lot Transfer adapters.
4. Port the direct cutting definition/calculation family, then implement the
   Cutting LaySheet label-to-GRN orchestration.
5. Implement bundle/panel movement and Quality/rework.
6. Implement Sewing and Time and Action.
7. Implement Production Order pricing/approval/alternative-transfer gaps and
   product/FG/sticker/profitability logic.
8. Port the integration/security-sensitive services after their production
   contracts are confirmed.
9. Port report data providers with their owning slice.
10. Port each slice's F15 Desk JS/Vue/view integration immediately after its
    server contract is stable, then verify the rendered workflow. Do not mark a
    slice complete while its required popup, editable grid, action, print-data
    provider, or status view is missing.

Every slice must prove create/save/submit/cancel/retry, permissions, complete
stock dimensions, and parity against migrated F15 records. Schema presence and
successful import are not proof of business-logic completion.

## 11. Resolved classification decisions

The classification is final for the current MRP scope:

1. `GRN Rework Item` remains historical/read-only. Active rework uses the F16
   Inspection Entry/Received Type flow or Work Order + Delivery Challan + GRN.
2. Local FG Item generation is implemented. Remote OMS/DC synchronization is
   not reactivated without a separately approved production contract.
3. Telegram approval and global automatic notifications are separate
   integration projects and are not blockers for the internal MRP workflow.

Everything else has an implemented or intentionally reused F16 outcome above.
