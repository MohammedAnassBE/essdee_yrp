# Actual Fabric Dia and GRN Source Allocation — Implementation Plan

Date: 2026-09-30
App: `essdee_yrp` on `frappe-16-yrp`
Site for verification: `yrp-test.site`
Status: **PLANNED — ON HOLD until the user-requested prerequisite is completed**

## Executive decision

Keep the cloth IPD as the planned recipe. Record a changed physical Dia on the
GRN where it is first observed, then carry that physical Item Variant through
every downstream fabric process. Use submitted GRN Items as the quantity source
and a receipt-level Work Order allocation ledger to reserve them safely.

This plan covers the fabric chain only. Cutting and the Frappe 15 Cutting Plan
port are explicitly out of scope for this implementation.

## Problem

A cloth IPD can plan one Dia for a colour/route, but knitting or another fabric
process can physically return multiple different Dias. Example:

```text
Planned knitting output: Grey / 18 Dia / 100 Kg
Actual knitting GRN:      Grey / 22 Dia / 60 Kg
                          Grey / 24 Dia / 40 Kg
```

The IPD must remain 18 Dia because it is shared planning/master data. The two
actual variants must become real stock and must feed the next process:

```text
Knitting GRN 22/24 Grey
  -> Dyeing WO deliverables 22/24 Grey
  -> Dyeing WO receivables  22/24 Red
  -> Dyeing GRN actual result
  -> Washing WO reads Dyeing GRNs, not Knitting GRNs
```

## Confirmed product rules

1. IPD Dia is the planned route/target and is never rewritten by a GRN.
2. The submitted GRN Item Variant is the truth for physical Dia, Colour and
   received quantity.
3. An operator enters Actual Dia only when physical output differs from the
   Work Order's expected receivable. Otherwise the expected Dia is carried
   automatically.
4. One planned Work Order receivable may be split into several actual Dia rows.
   Their combined quantity draws down that one planned receivable.
5. A downstream process reads submitted GRNs from its source process step.
   It never walks and recalculates the entire upstream history.
6. Multiple GRNs and suppliers form one eligible source pool, but every
   allocation retains the exact source GRN Item for audit and cancellation.
7. IPD Process Matrices define the transformation. Code must not hard-code
   process names such as Dyeing, Washing or Compacting.
8. No second stock ledger is introduced. YRP's Stock Ledger remains responsible
   for warehouse quantity and valuation. The new allocation data owns only
   reservation and process lineage.

## Scope

### Included

- Actual Dia split/override on regular Essdee fabric Work Order GRNs.
- All matrix-driven fabric process shapes currently supported by the cloth IPD:
  conversion, identity, swap and multi-swap.
- Exact predecessor-step resolution from the cloth IPD chain.
- Many source Work Orders, suppliers and submitted GRNs.
- Receipt-level allocation, reservation, release and cancellation guards.
- `Calculate Fabric Deliverables` popup changes in Desk and `/web`.
- Correct propagation into Work Order deliverables, receivables, DC defaults,
  GRN defaults, consumption and Lot fabric tracking.
- Query/index work required for predictable performance.

### Excluded

- Cutting Work Order, Cutting Plan, Cutting Lay Sheet and bundle flows.
- Changing an IPD or adding actual Dias to IPD master tables.
- A replacement Stock Ledger or valuation engine.
- Automatically accepting a changed Colour, cloth Item, Lot or other attribute
  as an execution variance. The first release permits only Dia variance.
- Re-planning garment demand or changing kg-per-piece cutting consumption.

## Existing foundation and identified gaps

### Foundation to retain

- `fabric_chain.get_fabric_steps()` already produces the ordered cloth-process
  chain from generic fabric-process rows.
- `fabric_source.get_source_availability()` already reads submitted GRNs and
  subtracts live downstream Work Order reservations.
- Work Order already carries `fabric_source_process` and
  `fabric_source_process_step`.
- Work Order child rows already carry `fabric_reference_variant` and
  `fabric_reference_allocations` for planned-route lineage.
- A GRN Item with `ref_doctype = Work Order Receivables` and a valid
  `ref_docname` can remain tied to its planned receivable.
- Submitted GRN tracking already reads the physical GRN Item Variant.

### Gaps to close

- The GRN UI cannot split one planned receivable into new physical Dias.
- Base validation trusts `ref_docname` but Essdee has no explicit guard that
  only Dia changed while Item/Colour/other attributes remained valid.
- Fabric GRN input calculation matches actual output attributes against the
  planned matrix output, so an unplanned Dia cannot resolve a group.
- Source availability currently aggregates by Item Variant and loses the exact
  GRN Item/supplier contribution.
- The source GRN SQL is scoped mainly by process name; it must also use the exact
  process-step snapshot and cloth production detail.
- The popup's `_matches_input` requires planned input Dia equality, so actual
  22/24 Dia receipts are rejected when the matrix expects 18.
- The calculated Work Order does not persist enough execution lineage to
  reverse a Dia-changing process safely at its GRN. Example: compacting may
  consume actual 22 Dia and receive planned 18 Dia; output 18 alone cannot tell
  the GRN calculator which physical input was allocated.

## Core model

There are three independent responsibilities:

| Record | Authority |
|---|---|
| GRN Item | Physical result: actual Item Variant, quantity and dimensions |
| Stock Ledger | Warehouse balance and valuation |
| Work Order Source Allocation | Reservation and exact GRN-to-downstream-WO lineage |

### Process-step identity

Every calculated fabric Work Order must snapshot:

- its current cloth-process step key;
- its selected/default source step key;
- the cloth IPD used to resolve those steps.

The default source is the immediately preceding operational step returned by
`get_fabric_steps()`. The source is never inferred from dates, supplier or the
latest GRN. Current IPD validation requires a distinct Process master per chain
stage, which keeps process selection unambiguous; the position remains part of
the snapshot so historical execution does not silently move when an IPD changes.

Proposed Work Order fields:

- `fabric_process_step` (Data, hidden, read-only)
- retain `fabric_source_process`
- retain `fabric_source_process_step`
- `fabric_source_ipd` (Link Item Production Detail, hidden snapshot if the
  existing `production_detail` cannot be used safely for this purpose)

If an IPD chain changes after a Work Order has allocations, recalculation must
show a stale-chain error and require the allocations to be released first.

### Work Order Source Allocation

Add a hidden child table on Work Order, one row per exact source receipt
contribution. It is queryable as a normal Frappe child table and follows the
parent Work Order lifecycle atomically.

Minimum fields:

- `execution_key` (Data; links the allocation to the generated input/output
  transformation row)
- `source_process` (Link Process)
- `source_process_step` (Data)
- `source_work_order` (Link Work Order)
- `source_grn` (Link Goods Received Note)
- `source_grn_item` (Data/Link to child row)
- `source_item_variant` (Link Item Variant)
- `source_received_type` (Link Received Type, if available as a field)
- `source_warehouse` (Link Warehouse, when applicable)
- `fabric_reference_variant` (Link Item Variant)
- `matrix` (Link IPD Process Matrix)
- `matrix_group_index` (Int)
- `allocated_qty`, `stock_qty`, `uom`, `stock_uom`, `conversion_factor`
- `target_item_variant` (Link Item Variant)

Availability is never stored as an independently editable balance:

```text
available(source GRN Item/reference)
  = submitted source stock quantity
  - active allocations on non-cancelled/non-closed target Work Orders
  - returned quantity, when returns affect the source receipt
```

The source GRN remains authoritative, which prevents a duplicated receipt
ledger from drifting away from stock.

### Execution lineage

Each server-generated transformation needs an `execution_key` that survives UI
grouping and row consolidation. The key associates:

- planned matrix + group;
- planned fabric reference route;
- actual physical source variant;
- projected output variant;
- source-allocation rows;
- generated Work Order deliverable/receivable rows.

The exact persistence shape (hidden execution child rows versus allocation JSON
on calculated children) must be chosen during the schema implementation spike.
The non-negotiable invariant is that a GRN row linked to a compacting output of
18 Dia can still resolve the allocated physical 22/24 Dia deliverable without
guessing from output attributes.

Do not use client-supplied attributes as the lineage authority. The server must
re-resolve the matrix group and allocation under lock on Apply/submit.

## Actual Dia GRN design

### UI

For an eligible fabric receivable, add an `Actual Dia` action to the received-
type editor. The default row shows the expected Dia. The operator can clone/split
it into physical Dias and enter quantities, for example:

```text
Expected 18 Dia / Allowed 100 Kg
  Actual 22 Dia / Accepted / 60 Kg
  Actual 24 Dia / Accepted / 40 Kg
```

Every clone retains the original:

- `ref_doctype` and `ref_docname`;
- pending/allowed context;
- planned route/execution context;
- stock dimensions other than Received Type;
- non-Dia Item attributes.

Only configured Dia values may be selected. Variant creation/resolution remains
server-owned through the existing stock-item grouping contract.

### Server validation

For every changed-Dia GRN row:

1. Resolve the referenced Work Order Receivable by `ref_docname`.
2. Require the same parent Item.
3. Require every declared Item attribute except Dia to equal the expected
   receivable's attribute.
4. Require the selected Dia to be a valid Dia attribute value.
5. Sum all actual-Dia and Received-Type splits against the referenced
   receivable's remaining allowance.
6. Preserve the reference even though the physical Item Variant differs.
7. Reject crafted payloads that change Colour, Item or route metadata.

The base Work Order pending quantity is reduced by the combined actual receipt
quantity. Stock is posted under the physical actual variants.

### Current-process consumption

The current process's input consumption must be calculated from its saved
execution/matrix context, not by asking the unplanned output Dia to exactly
match a planned matrix output. For a knitting GRN, the planned route still
selects the yarn/input ratio while the actual Dia controls received stock.

If a downstream GRN itself changes Dia unexpectedly, the same rule applies:
consume the inputs allocated to that receivable and post its output under the
new physical Dia.

## Generic transformation projection

Given a planned matrix group and an actual physical principal input:

1. Select the group by saved matrix/group key and fabric reference route.
2. Validate the actual source Item and all non-variable input attributes.
3. Start the effective input attributes from the physical source variant.
4. For each output attribute:
   - if planned input equals planned output, carry the actual input value;
   - if the process changes the attribute, use the planned output target;
   - if the process introduces an attribute, use the planned introduced value.
5. Resolve/create the projected output Item Variant server-side.
6. Scale input/output quantities using the matrix group's ratios and wastage.

Examples:

```text
Dyeing matrix:    Grey 18 -> Red 18
Actual input:     Grey 22
Projected output: Red 22

Washing matrix:  Red 18 -> Red 18
Actual input:     Red 22
Projected output: Red 22

Compacting:       Red 20 -> Red 18
Actual input:     Red 22
Projected output: Red 18
```

Auxiliary/BOM inputs continue to come from the planned matrix/BOM. Only the
physical principal fabric input is sourced from the selected GRN pool.

## Calculate Fabric Deliverables popup

### Source resolution

- Default to the immediately preceding IPD fabric step.
- Show only valid earlier operational steps as override options.
- Save the exact selected step on the Work Order.
- If a route legitimately bypasses a step, select the earlier valid source and
  persist it per execution/allocation row; do not silently mix histories.

### Data retrieval

Fetch all eligible source GRN Items in one indexed query, filtered by:

- submitted, non-return, non-cancelled GRN;
- same Lot;
- same cloth Item and cloth production detail;
- exact source process and process-step snapshot;
- eligible Received Type;
- positive unallocated stock quantity.

Join the referenced source Work Order Receivable to recover
`fabric_reference_variant` / `fabric_reference_allocations`. A consolidated
source receipt is split logically across its saved reference allocations.

### Display

Group receipt rows for readability by actual input variant and projected route,
while keeping the receipt breakdown behind the group:

| Planned route | Actual input | Projected output | Received | Reserved | Available | Qty |
|---|---|---|---:|---:|---:|---:|
| Grey -> Red | Grey 22 | Red 22 | 120 | 40 | 80 | 80 |
| Grey -> Red | Grey 24 | Red 24 | 90 | 20 | 70 | 70 |

An expandable source breakdown may show GRN, source Work Order and supplier.
When one source can feed several targets, leave target quantities at zero and
require an explicit allocation. A `Fill Available` action is safe only for a
unique target.

### Apply

Apply must run in one database transaction:

1. Lock the Lot and the selected source GRN Item rows (not every historical GRN).
2. Recompute availability, excluding the current Work Order's old allocations.
3. Reject stale/over-allocated requests.
4. Server-resolve transformations and variants.
5. Rewrite calculated deliverables, receivables, execution lineage and source
   allocations idempotently.
6. Save the Work Order.

Draft Work Orders reserve stock. Cancelled or closed Work Orders do not. Re-run
releases/replaces the current Work Order's previous reservations atomically.

## Multiple GRNs and supplier behavior

Ten source GRNs are not processed as ten document loads. A single SQL query
returns their child rows and aggregates the popup summary in the database or in
one server pass. Exact receipt identities remain in allocation rows.

Default allocation order:

1. earliest posting date/time;
2. GRN creation/name as a deterministic tie-breaker.

The popup may optionally filter or expand by supplier/GRN, but the database
always retains the exact FIFO/manual source split. Same physical variant from
several suppliers may appear as one summary line without losing provenance.

## Performance and indexes

Add/verify indexes supporting the source-pool query and allocation subtraction:

- Work Order: `(lot, production_detail, fabric_process_step, docstatus)` or the
  closest MariaDB-supported selective order;
- Goods Received Note: `(against, against_id, docstatus, is_return)`;
- Goods Received Note Item: `(parent, ref_doctype, ref_docname, item_variant)`;
- Work Order Source Allocation: `(source_grn_item)` and source step/reference
  fields needed by availability queries.

Do not lock during popup reads. Lock and revalidate only on Apply/submit. Ten or
hundreds of GRNs should remain a bounded indexed query; a materialized balance
table is not justified unless production measurements later show a need.

## DC and next-process behavior

- A DC is built from the calculated Work Order deliverables, which already
  contain physical source variants. The operator does not re-enter Dia.
- A GRN is built from projected Work Order receivables. The operator changes
  Actual Dia only if the physical result differs again.
- The next process reads this newly submitted GRN's physical variants.
- The system never keeps using the knitting GRN after dyeing has produced a
  dyeing GRN, unless the operator explicitly selects a valid bypass route.

## Cancellation, returns and edits

- Block source GRN cancellation while an active downstream allocation exists;
  list the dependent Work Orders in the error.
- Cancelling/closing/deleting a target Work Order releases its unused
  allocations according to existing Work Order lifecycle rules.
- Recalculating a draft Work Order replaces its allocations under lock.
- A submitted source GRN return reduces source availability. Block the return if
  it would make active allocations exceed the remaining receipt.
- Block changes to a Work Order's Lot, cloth IPD, process or process-step fields
  while source allocations exist.
- Cancellation must use persisted execution/allocation rows; never recalculate
  historical matrix rules from a possibly changed IPD.

## Reporting and audit

Provide enough data for:

- planned Dia versus actual Dia by GRN/process/supplier;
- source GRN -> target Work Order -> target GRN lineage;
- received, allocated, consumed and available quantity per physical variant;
- reasons a source GRN cannot be cancelled.

Lot plan/step ledgers remain planning and summary views. They are not the source
allocation authority.

## Implementation phases

### Phase 0 — prerequisite and fixture audit

- Complete the separate prerequisite requested by the user.
- Capture representative `yrp-test.site` fixtures:
  - one planned Dia received as two actual Dias;
  - multiple GRNs from multiple source Work Orders/suppliers;
  - dyeing -> washing identity propagation;
  - compacting actual input -> planned target output.
- Confirm eligible Received Type policy and warehouses/dimensions.

### Phase 1 — schema and source-pool service

- Add process-step snapshot field(s).
- Add Work Order Source Allocation child schema and indexes.
- Refactor `fabric_source.py` to return receipt-level buckets plus grouped
  summaries, scoped by exact cloth IPD/process step.
- Add concurrency-safe allocate/release APIs and cancellation guards.
- Preserve compatibility for pre-feature Work Orders without allocations.

### Phase 2 — Actual Dia GRN

- Add Actual Dia split/clone controls to Desk and `/web` GRN editors.
- Add Essdee server validation for Dia-only variance.
- Update fabric GRN consumption to use saved planned execution context while
  posting the physical output variant.
- Verify Received Type splitting and excess allowance still operate per original
  receivable across all Actual Dia rows.

### Phase 3 — transformation-aware Work Order popup

- Add the actual-input/projected-output row model to both popup clients.
- Implement server-side matrix projection.
- Persist exact execution lineage and source allocations.
- Make Apply idempotent and safe under concurrent allocation.

### Phase 4 — lifecycle and downstream integration

- Verify DC defaults carry actual variants.
- Verify every subsequent GRN becomes the next source pool.
- Add cancel/return/close guards and releases.
- Update Lot fabric tracking and planned-versus-actual audit views.

### Phase 5 — migration, tests and rollout

- Backfill only process-step snapshots that can be resolved unambiguously.
  Do not fabricate receipt-level allocations for historical Work Orders.
- Keep a legacy availability fallback for old open Work Orders, clearly marked
  and excluded once they close.
- Run unit, integration and browser tests on `yrp-test.site`.
- Roll out behind a site/setting flag if live historical data reveals unresolved
  route ambiguity.

## Required test matrix

### Unit

- predecessor step resolution and stale-chain detection;
- actual-Dia projection for identity, Colour swap, Dia swap, multi-swap and
  conversion;
- Dia-only GRN validation;
- FIFO/manual receipt allocation and UOM normalization;
- reference-allocation scaling for consolidated source receivables;
- allocation release and over-allocation rejection.

### Integration

- planned 18 -> knitting GRN 22/24 -> dyeing WO 22/24 -> dyeing GRN;
- washing reads only dyeing GRNs and carries physical Dia unchanged;
- compacting consumes actual 22/24 and receives configured target 18;
- ten GRNs across suppliers aggregate correctly while preserving exact sources;
- two concurrent Work Order calculations cannot reserve the same receipt qty;
- Received Type split plus Actual Dia split shares one receivable allowance;
- source GRN cancel/return guards and target WO cancel/close release;
- partial DC and partial GRN quantities.

### Browser

- Desk and `/web` show the same actual-input/projected-output/source quantities;
- Actual Dia add/remove/edit survives save/reload;
- stale popup gets a refresh message rather than overwriting allocations;
- source breakdown shows GRN/WO/supplier and totals reconcile.

## Acceptance criteria

1. A planned receivable can be submitted as several actual Dias without editing
   the IPD.
2. Stock Ledger entries use the actual received variants.
3. Every downstream fabric Work Order defaults to the correct predecessor step.
4. Multiple source GRNs aggregate quickly and cannot be double allocated.
5. Dyeing/washing carry actual Dia; a configured Dia-changing step applies its
   planned target.
6. DC and normal GRN entry require no repeated manual Dia entry.
7. Every calculated quantity is traceable to exact source GRN Item rows.
8. Cancellation, return and recalculation preserve balances and historical
   execution without consulting changed IPD rules.
9. Existing legacy Work Orders continue to function during rollout.
10. Cutting remains unchanged and is not accidentally coupled to this release.

## Decisions to confirm during the prerequisite phase

These do not change the architecture but must be fixed before coding:

1. Which Received Types are eligible to feed the next fabric process (default
   Accepted only is recommended).
2. Whether operators may manually choose source supplier/GRN or only inspect the
   FIFO breakdown (FIFO default with optional override is recommended).
3. Whether creating a previously unused Dia attribute value is restricted to a
   manager or operators may select only existing values (existing values only is
   recommended).
4. Whether warehouse/location must be a popup filter in addition to Lot/cloth/
   process-step (recommended when one Lot is held at multiple locations).
