# Cloth Post-P0 Corrections Design

**Date:** 2026-10-07  
**Status:** Conversation design and written specification approved
**Target bench:** `frappe-16`  
**Target site:** `erp-migration-test.site`  
**Reference bench:** `frappe-16-yrp`, `essdee_yrp` develop branch

## Purpose

Complete the three post-P0 cloth-production corrections without changing the
P0 execution contract or broadening the supported production route:

1. make Inspection Entry Accepted/Rejected conversions update exact GRN-source
   availability and rebuild affected Lot conversions safely;
2. preserve each row's Received Type when a `production_api` GRN is received as
   a YRP Stock Entry; and
3. add a clear, read-only Work Order movement, source, debit and valuation
   summary to ERPNext Desk.

The supported verification route remains:

`Cloth Program -> Knitting -> Dyeing -> Washing`

Compacting is not part of this phase.

## Success Criteria

1. A converted Inspection Entry changes the Accepted balance of the exact
   referenced `YRP Goods Received Note Item`, not an Item-level aggregate.
2. Lot fabric conversions are rebuilt in the same transaction after an
   inspection conversion and reflect only the remaining Accepted quantity.
3. Concurrent inspection conversions cannot double-convert an Inspection Entry
   or rebuild a Lot from a stale snapshot.
4. A cross-bench GRN transfer preserves explicit Accepted and Rejected values
   row by row, including mixed payloads.
5. A transfer row without Received Type uses the configured YRP default for
   backward compatibility; an unknown type rejects the entire request before a
   Stock Entry is created.
6. The Work Order Desk form shows planned, actual and pending movements, exact
   sources, debits, planned process cost, and posted input/output valuation.
7. Existing APIs used by Cutting Plan, Fabric Store and `/web` remain unchanged.
8. Existing Cloth Program, WO, DC, GRN, generic stock and non-cloth flows retain
   their current behaviour.

## Scope

### Included

- `YRP Inspection Entry` stock conversion for P0 exact-source cloth receipts.
- Exact Accepted-balance calculation per source GRN child row.
- Safe affected-Lot conversion rebuild after inspection conversion.
- `production_api` GRN-to-YRP Stock Entry transfer Received Type handling.
- A new read-only Work Order summary API and ERPNext Desk component.
- Focused automated tests and persisted Knitting, Dyeing and Washing tests on
  `erp-migration-test.site`.

### Excluded

- Historical migration or backfill.
- Fabric Store UI changes.
- `/web` UI changes.
- Compacting.
- Stock Entry to Delivery Challan convenience actions.
- Replacing the existing `fetch_summary_details` API.
- Any Purchase Order or unrelated production-flow change.

## Current Architecture to Preserve

- `cloth_execution_version == 1` and the saved fabric execution key identify
  the P0 exact-source flow.
- ERPNext `Item` is the item master even where inherited child fields are named
  `item_variant`.
- A submitted Delivery Challan is the allocation authority.
- Active `YRP Stock Ledger Entry` rows are the stock and valuation authority.
- Lot fabric conversions are server-owned projections rebuilt from eligible
  submitted default-Knitting GRNs.
- Existing Work Order `fetch_summary_details` consumers keep their current
  response and behaviour.

The reference branch is a behavioural source only. Its unprefixed DocTypes must
be adapted to the current `YRP ...` and `SD YRP ...` contracts.

## 1. Inspection Conversion

### Entry point

Add a whitelisted Essdee override for the base YRP `convert_stock` method used
by `YRP Inspection Entry`. Permission, submitted-state, cancelled-state and
already-converted checks remain equivalent to the base controller.

The override applies the standard paired Stock Ledger movements:

- negative quantity from the row's current `received_type`;
- positive quantity into its `target_received_type`;
- same Item, warehouse, exact source reference and other stock dimensions.

No new stock movement model is introduced.

### Exact Accepted adjustment

Add one reusable Accepted-adjustment query keyed by exact source child row:

`YRP Goods Received Note Item.name -> net Accepted stock-ledger delta`

Only active ledger rows from successfully converted `YRP Inspection Entry`
documents are included. Cancelled ledger rows and unconverted/draft Inspection
Entries are ignored.

The signed adjustment is applied to the original eligible receipt quantity:

`accepted_available_basis = receipt_stock_qty + accepted_inspection_delta`

Therefore:

- Accepted -> Rejected produces a negative delta;
- Rejected -> Accepted produces a positive delta;
- Accepted -> Accepted and Rejected -> Rejected have no net effect.

Small floating-point residues are normalized using the existing stock precision
rules. A materially negative result is never exposed as available stock.

Both exact-source discovery and Lot conversion rebuild use the same helper so
their interpretation cannot diverge.

### Qualification

Only an inspection row referencing an eligible P0 source is allowed to affect a
Lot conversion. The source must resolve through:

- `ref_doctype = YRP Goods Received Note Item`;
- a submitted `YRP Goods Received Note`;
- a versioned/keyed default-Knitting receipt; and
- an `SD YRP Lot` participating in the current cloth execution flow.

Inspection conversions for unrelated stock still use the same stock movement
but do not trigger a Lot rebuild.

### Locking and transaction order

The conversion uses the established cloth lock order:

1. affected Lots in stable name order;
2. referenced GRN parents and source child rows in stable order;
3. the Inspection Entry itself with a current locking read.

After locks are acquired, the Inspection Entry state and affected sources are
re-read. The stock conversion, converted-state update and all affected Lot
rebuilds happen in one database transaction. An error rolls back all of them.

This prevents:

- two requests converting the same Inspection Entry;
- a Lot rebuild seeing a pre-conversion snapshot; and
- source availability and Lot conversion quantities disagreeing after commit.

Normal stock-ledger negative-stock validation remains authoritative when an
Accepted quantity has already moved or is otherwise unavailable.

### Lot rebuild behaviour

After ledger entries and converted state are written, rebuild each locked Lot
from all current eligible submitted default-Knitting receipts. The rebuild uses
the adjusted Accepted basis for every exact GRN child row.

The rebuild remains complete and idempotent; it does not incrementally mutate a
single conversion row.

## 2. Cross-Bench Stock Transfer

### Incoming contract

`receive_grn_transfer(payload)` continues to accept the current payload and
idempotency reference. Each item row may additionally supply:

```json
{
  "received_type": "Accepted"
}
```

Explicit values are copied to the corresponding YRP Stock Entry item. Rows in
one payload may use different Received Types.

### Backward-compatible fallback

When an old `production_api` payload omits or sends a blank Received Type, the
receiver uses `YRP Stock Settings.default_received_type`. The receiver does not
silently invent a literal when no default is configured; it returns a validation
error instead.

The deployment configuration is expected to keep `Accepted` as the default, so
old payloads retain their current behaviour.

### Validation and atomicity

Before inserting the YRP Stock Entry, resolve every row's effective Received
Type and verify that its `YRP Received Type` master exists. Any missing or
unknown value rejects the complete payload and creates no partial Stock Entry.

The existing lot, warehouse, item, row-index, cancellation and idempotency rules
remain unchanged. This feature does not change UOM conversion behaviour.

Although Received Type is a stock dimension, the cross-bench receiver must copy
the row value onto the Stock Entry child; the stock ledger can only preserve the
dimension it receives from that child row.

## 3. Work Order Desk Summary

### Isolation from existing consumers

Add a new read-only endpoint, `get_work_order_summary(work_order)`. Do not alter
or replace `fetch_summary_details`, because it is used by existing Cutting,
Fabric Store and `/web` flows.

The new endpoint requires read permission for the requested `YRP Work Order`.
It makes no writes.

### Response model

The endpoint returns four sections:

1. **Issued / deliverables**
   - Item and UOM;
   - planned quantity;
   - actual issued quantity;
   - pending quantity;
   - Received Type;
   - exact `source_grn` and `source_grn_item` when present.

2. **Received / receivables**
   - Item and UOM;
   - planned quantity;
   - actual received quantity;
   - pending quantity;
   - planned process cost from the saved receivable contract.

3. **Debits**
   - submitted/current `YRP Debit` records linked to the Work Order;
   - debit number, type, value, status and reason.

4. **Posted valuation**
   - input stock value: absolute total of active negative SLE value changes;
   - output stock value: total of active positive SLE value changes;
   - posted process value: output value minus input value.

Posted valuation is read from active `YRP Stock Ledger Entry` rows belonging to
submitted GRNs against the Work Order. Cancelled SLEs and cancelled GRNs are
excluded.

Planned process cost and posted process value are labelled separately. The UI
must not present the planned value as an accounting posting.

### Quantity semantics

For each movement child:

- planned = saved child `qty`;
- pending = non-negative saved `pending_quantity`;
- actual = non-negative `planned - pending`.

Rows are grouped only when their business identity is the same. Issued rows
with different exact source child, Received Type or UOM stay distinct even when
their Items match. Totals are separated by UOM; quantities with unlike UOMs are
never added together.

### Desk component

Replace only the current Work Order form's mounted summary component with a new
Essdee Desk component backed by `get_work_order_summary`.

The component shows:

- Issued, Received and Pending quantities;
- exact source lineage in a compact source column;
- Received Type;
- debit rows and total;
- planned process cost;
- posted input, process and output values; and
- a short explanation that output value is derived from input stock value plus
  the posted process-value uplift.

Empty sections display a clear empty state. Loading/API failures use standard
Frappe messaging and do not break the Work Order form.

No `/web` component or Fabric Store component is changed.

## Error Handling

- Inspection conversion failures use Frappe validation errors and roll back
  stock, converted status and Lot rebuild together.
- Unknown transfer Received Types identify the invalid value and row.
- Summary permission failures use the normal Frappe permission exception.
- Missing optional source lineage in legacy Work Orders is displayed as
  unavailable; it does not make the summary endpoint fail.
- Missing valuation rows produce zero posted values rather than fabricated
  estimates.

## Testing Strategy

### Automated inspection tests

- Accepted -> Rejected reduces exact source availability.
- Rejected -> Accepted increases exact source availability.
- The affected Lot conversion quantity is rebuilt in the same transaction.
- A different GRN child with the same Item is not modified.
- Converted/cancelled/draft-state guards remain enforced.
- A second conversion request cannot convert the same document twice.
- Unrelated inspection stock does not rebuild a Lot.

### Automated transfer tests

- Explicit Accepted is preserved.
- Explicit Rejected is preserved.
- Mixed Accepted/Rejected rows remain distinct.
- Blank/missing Received Type uses the configured default.
- Unknown Received Type rejects without creating a Stock Entry.
- Existing idempotency and cancellation tests continue to pass.

### Automated summary tests

- planned, actual and pending quantities are calculated correctly;
- distinct sources and Received Types remain separate;
- totals are separated by UOM;
- only the Work Order's active GRN ledger movements affect valuation;
- cancelled SLEs/GRNs are ignored;
- `YRP Debit` rows and totals are returned correctly;
- read permission is enforced;
- the existing `fetch_summary_details` contract is unchanged.

### Persisted flow verification

On `erp-migration-test.site`, create and submit fresh entries through:

1. Knitting WO/DC/GRN;
2. inspection conversion against an exact Knitting GRN row;
3. Dyeing WO/DC/GRN;
4. Washing WO/DC/GRN;
5. cross-bench transfer payloads with explicit and fallback Received Types; and
6. the Work Order Desk summary for each production stage.

Verify submit, cancel, partial quantities, source availability, Lot conversion,
stock ledger dimensions, valuation and existing regression suites. Compacting
is not created or tested in this phase.

## Deployment and Data Compatibility

- Schema/API additions are backward compatible.
- No historical data backfill is required.
- Existing submitted GRNs, Work Orders and Lots are not rewritten.
- Existing transfer payloads without Received Type continue through the
  configured default.
- Legacy Work Orders may show less source detail, but their transactions are not
  modified.
- Rollback consists of reverting code/assets; no irreversible data migration is
  introduced.

## Final Non-Regression Boundary

The implementation may change only:

- the result of a converted Inspection Entry on exact P0 cloth sources;
- the Received Type copied by cross-bench GRN transfer rows; and
- the read-only summary rendered on the `YRP Work Order` Desk form.

All other transaction controllers and UIs must retain their current behaviour.
