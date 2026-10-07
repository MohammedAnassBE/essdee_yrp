# Cloth Post-P0 Corrections Implementation Plan

> **For the implementer:** Use the `executing-plans`, `test-driven-development`,
> and `verification-before-completion` skills. Complete tasks in order, keep the
> red/green cycle visible, and do not edit unrelated dirty files.

**Goal:** Make inspection conversions update exact cloth-source availability,
preserve row-level Received Type in cross-bench GRN transfers, and add a
Desk-only Work Order movement/debit/valuation summary without changing existing
production flows.

**Architecture:** Active YRP Stock Ledger Entries remain authoritative for both
inspection classification and posted valuation. Exact-source availability and
Lot projections consume one shared per-GRN-child Accepted adjustment. The
transfer receiver normalizes and validates Received Type before creating its
single Stock Entry. The Work Order summary is a new read-only endpoint and Vue
component; the existing legacy summary endpoint remains untouched.

**Tech stack:** Frappe 16, ERPNext 16, YRP DocTypes, MariaDB locking reads,
Python, Vue 3, Frappe Desk JavaScript, Playwright smoke checks.

**Approved design:**
`docs/superpowers/specs/2026-10-07-cloth-post-p0-corrections-design.md`

## Fixed Scope and Safety Rules

- Target site: `erp-migration-test.site`.
- Supported persisted test route: Knitting -> Dyeing -> Washing.
- No Compacting.
- No migration/backfill.
- No `/web` or Fabric Store UI changes.
- Do not replace `fetch_summary_details`.
- Use the current `YRP ...` / `SD YRP ...` DocTypes and ERPNext `Item` model.
- Preserve all pre-existing uncommitted user files; stage commits by explicit
  path only.
- Do not commit generated assets unless they are already repository-owned and
  the build genuinely changes them.

## Task 0: Record a Clean Baseline Around the Dirty Worktree

**Files:** none

1. Record the current branch, HEAD and complete `git status --short` for both
   `apps/essdee_yrp` and `apps/yrp`.
2. Confirm the files in this plan are either clean or new before editing them.
3. Run the existing focused baseline:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_inspection_entry_customization
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_source
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_substitution
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.api.test_stock_transfer
```

4. If a baseline test already fails, diagnose and record it before feature work;
   do not silently absorb an unrelated failure into this implementation.

## Task 1: Derive the Exact Accepted Quantity from Converted Inspections

**Files:**

- Modify: `essdee_yrp/test_fabric_source.py`
- Modify: `essdee_yrp/test_fabric_substitution.py`
- Modify: `essdee_yrp/fabric_source.py`
- Modify: `essdee_yrp/fabric_substitution.py`

### Step 1: Write failing exact-source tests

Add focused tests covering:

- converted active Inspection SLEs aggregate by exact
  `YRP Goods Received Note Item.name`;
- Accepted -> Rejected subtracts only from its referenced GRN child;
- Rejected -> Accepted introduces an Accepted source bucket for a versioned,
  keyed GRN child whose original Received Type was Rejected;
- cancelled SLEs, draft/unconverted Inspection Entries and unrelated source
  children are ignored;
- two GRN children with the same Item remain independent;
- preview reads do not force `FOR UPDATE`, while submit/rebuild reads do.

Use small row fixtures for the pure quantity normalization tests and mock the DB
only at the query boundary. Assert exact names and quantities, not only totals.

### Step 2: Run the new tests and confirm RED

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_source
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_substitution
```

Expected failure: the adjustment/normalization helpers do not yet exist and
current code discards originally Rejected receipt rows.

### Step 3: Implement one authoritative adjustment helper

In `essdee_yrp/fabric_source.py`:

1. Add `_accepted_inspection_adjustments(received_rows, *, for_update=False)`.
2. Query `tabYRP Stock Ledger Entry`, joined to
   `tabYRP Inspection Entry Item` and `tabYRP Inspection Entry`.
3. Filter to:
   - `voucher_type = 'YRP Inspection Entry'`;
   - active/non-cancelled SLEs;
   - submitted and converted Inspection Entries;
   - `ref_doctype = 'YRP Goods Received Note Item'`;
   - only source child names present in `received_rows`;
   - the configured `YRP Stock Settings.default_received_type`.
4. Group the signed SLE quantity by exact `ref_docname`.
5. Add a small pure normalizer that computes:

```text
original Accepted qty (or zero) + converted Inspection Accepted delta
```

6. Preserve execution identity and lineage, normalize the effective
   `received_type` to the configured default, clamp numerical dust to zero, and
   retain only positive effective Accepted rows.
7. Keep versioned/keyed qualification separate from original Received Type so a
   Rejected receipt promoted to Accepted can enter the exact pool.

### Step 4: Feed normalized rows into exact-source buckets

Update `prepare_source_pool` so:

- all versioned/keyed candidate receipt rows are considered;
- accepted adjustments use the caller's `for_update` mode;
- classification and bucket construction use effective Accepted quantity;
- consumption still reserves by the exact source bucket key;
- legacy/unkeyed behavior is unchanged.

Do not change Item/UOM/source hashing or the Delivery Challan allocation rules.

### Step 5: Feed the same normalized quantity into Lot rebuilds

Update `_fetch_default_knitting_receipts` in
`essdee_yrp/fabric_substitution.py` to:

- fetch versioned/keyed default-Knitting rows regardless of their original
  Received Type;
- call the shared adjustment helper with a locking read;
- include only positive effective Accepted quantity;
- emit the configured default Received Type on the normalized receipt;
- preserve execution key, actual Item, planned Item, route Item and UOM.

The existing complete/idempotent `_rebuild_lot_fabric_conversions` remains the
only writer of conversion rows.

### Step 6: Run focused tests and confirm GREEN

Run both modules from Step 2 and verify the pre-existing exact-source and Lot
projection tests still pass.

### Step 7: Commit the coherent quantity layer

Stage only the four files listed in this task and commit:

```bash
git commit -m "fix: derive cloth sources from inspection classifications"
```

## Task 2: Convert Inspection Stock Under the Cloth Lock Order

**Files:**

- Modify: `essdee_yrp/test_inspection_entry_customization.py`
- Modify: `essdee_yrp/test_fabric_substitution.py`
- Modify: `essdee_yrp/overrides/inspection_entry.py`
- Modify: `essdee_yrp/fabric_substitution.py`
- Modify: `essdee_yrp/hooks.py`

### Step 1: Write failing conversion and locking tests

Add tests that prove:

- source GRN parents are resolved from exact Inspection child references;
- eligible default-Knitting Lots lock in sorted order before source GRNs;
- source GRNs lock before the Inspection Entry locking reload;
- conversion writes SLEs once, marks the Inspection Entry converted, and rebuilds
  every affected locked Lot once;
- an already-converted, cancelled or non-submitted Inspection Entry is rejected;
- unrelated GRN and Stock Entry inspections still convert but do not rebuild a
  Lot;
- an exception during any rebuild leaves the conversion transaction able to
  roll back as one unit;
- the hook maps the base YRP `convert_stock` route to the Essdee override.

Use an ordered call log in the unit test so the lock order is explicit rather
than inferred from individual mock assertions.

### Step 2: Run and confirm RED

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_inspection_entry_customization
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_substitution
```

Expected failure: only `get_initial_payload` is overridden today; no Lot-lock
helper or transactional conversion override exists.

### Step 3: Add the affected-Lot locking helper

In `essdee_yrp/fabric_substitution.py`, add
`lock_lots_for_default_knitting_grns(grn_names)` adapted to current names:

- `YRP Goods Received Note`;
- `YRP Work Order`;
- `SD YRP Lot`;
- `SD YRP IPD Settings.default_knitting_process`;
- `cloth_execution_version = 1`;
- current standard-GRN exclusion flags.

Discover eligible Lot names first, then lock them in stable sorted order. Return
the locked names. Do not rebuild at this point.

### Step 4: Implement the conversion override

Extend `essdee_yrp/overrides/inspection_entry.py` with:

- `_source_grn_names(doc)` resolving exact YRP GRN child references;
- `_lock_source_grns(doc)` using stable `FOR UPDATE` ordering;
- `convert_stock(name)` preserving base approver-role and document-state checks.

The method sequence must be:

1. check the configured approver role;
2. plain-read the submitted source references;
3. lock affected Lots;
4. lock referenced GRN parents;
5. reload `YRP Inspection Entry` with `for_update=True`;
6. repeat submitted/converted/cancelled checks on the current row;
7. build and post the base document's paired SLE entries;
8. enqueue valuation repost;
9. mark status and `is_converted`;
10. rebuild every already-locked affected Lot.

No explicit commit belongs inside this method. Frappe owns the request
transaction; any error must roll back SLEs, status and conversion rows together.

### Step 5: Register the whitelisted override

Add this mapping beside `get_initial_payload` in `essdee_yrp/hooks.py`:

```text
yrp.yrp.doctype.yrp_inspection_entry.yrp_inspection_entry.convert_stock
    -> essdee_yrp.overrides.inspection_entry.convert_stock
```

Do not reorder or remove other hook mappings.

### Step 6: Run focused and base-YRP tests

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_inspection_entry_customization
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_source
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_substitution
bench --site erp-migration-test.site run-tests --app yrp \
  --module yrp.yrp.doctype.yrp_inspection_entry.test_yrp_inspection_entry
```

### Step 7: Commit the transactional conversion

Stage only Task 2 files and commit:

```bash
git commit -m "fix: rebuild exact cloth conversions after inspection"
```

## Task 3: Preserve Received Type in Cross-Bench GRN Transfers

**Files:**

- Modify: `essdee_yrp/api/test_stock_transfer.py`
- Modify: `essdee_yrp/api/stock_transfer.py`

### Step 1: Write failing transfer tests

Add integration tests for:

- explicit Accepted is preserved;
- explicit Rejected is preserved;
- one payload can contain Accepted and Rejected rows without merging or
  rewriting either classification;
- missing and blank values use
  `YRP Stock Settings.default_received_type`;
- an unknown Received Type returns `ok: false` and creates no Stock Entry;
- an absent configured default rejects a blank old payload cleanly;
- row-index, idempotency, cancellation and existing Accepted behavior remain
  unchanged.

Create/restore any test Received Type/default within the test transaction; do
not depend on manually prepared test-site state beyond the existing stock
fixtures.

### Step 2: Run and confirm RED

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.api.test_stock_transfer
```

Expected failure: the receiver currently validates and writes literal
`Accepted` for every row.

### Step 3: Normalize and validate before document creation

In `essdee_yrp/api/stock_transfer.py`:

1. Read the configured default once.
2. Build normalized row copies so the caller's payload is not mutated.
3. Use explicit row `received_type` when present, otherwise the default.
4. Validate every distinct effective value against `YRP Received Type` before
   constructing `YRP Stock Entry`.
5. Return one clear all-or-nothing error listing invalid values/rows.
6. Set the normalized value on each appended Stock Entry child instead of the
   literal `Accepted`.

Do not broaden the accepted payload keys, change conversion factor/UOM rules,
or alter the file-lock/idempotency boundary.

### Step 4: Run and confirm GREEN

Run the module from Step 2 and inspect the submitted Stock Entry children and
their SLE dimensions in the explicit/mixed tests.

### Step 5: Commit the transfer correction

```bash
git commit -m "fix: preserve received type in grn transfers"
```

## Task 4: Add the Work Order Summary Read Model

**Files:**

- Create: `essdee_yrp/test_work_order_summary.py`
- Modify: `essdee_yrp/api/work_order.py`

### Step 1: Write failing backend tests

Create tests for:

- read permission is checked on `YRP Work Order`;
- deliverable and receivable planned/actual/pending math clamps corrupt negative
  results safely;
- totals are kept separate by UOM;
- deliverables with different `source_grn_item` or Received Type remain separate;
- legacy rows without source fields still serialize safely;
- planned process cost uses saved receivable `total_cost` and is labelled as
  planned;
- YRP Debit rows expose document lifecycle, value and reason only when the user
  can read them;
- posted valuation includes only active YRP SLE rows for submitted GRNs against
  the requested Work Order;
- cancelled SLEs, cancelled GRNs and other Work Orders do not contribute;
- posted process value equals output value minus input value;
- `fetch_summary_details` remains present and retains its existing signature.

### Step 2: Run and confirm RED

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_work_order_summary
```

Expected failure: `get_work_order_summary` and its helper read models do not yet
exist in the current branch.

### Step 3: Implement movement summaries

In `essdee_yrp/api/work_order.py`, add helpers that:

- calculate `planned = qty`;
- calculate `pending = max(pending_quantity, 0)`;
- calculate `actual = max(planned - pending, 0)`;
- group receivables by Item + UOM;
- group deliverables by Item + UOM + exact source GRN child + Received Type;
- preserve `source_grn`, `source_grn_item` and `received_type` in rows;
- attach Item template/name and ordered Item attributes;
- produce UOM-specific totals;
- sum planned receivable `total_cost` separately from movement quantities.

Use ERPNext `Item`, even though inherited row fields are named `item_variant`.

### Step 4: Implement debit and valuation summaries

Add:

- `_get_work_order_debit_summary(work_order)` querying `YRP Debit`, returning an
  empty list when the doctype/permission is unavailable;
- `_get_work_order_valuation_summary(work_order)` joining active
  `YRP Stock Ledger Entry` rows to submitted `YRP Goods Received Note` rows
  whose `against = 'YRP Work Order'` and `against_id` is the requested WO.

Valuation fields:

```text
input_value   = absolute sum of negative stock_value_difference
output_value  = sum of positive stock_value_difference
process_value = output_value - input_value
```

Return zeros when no posted rows exist. Do not estimate posted values from the
planned process cost.

### Step 5: Add the whitelisted endpoint

Add `get_work_order_summary(work_order)` that:

1. loads `YRP Work Order`;
2. checks read permission;
3. returns `work_order`, `deliverables`, `receivables`, `debits`,
   `planned_process_cost`, and `valuation`;
4. performs no writes and no commits.

Leave `fetch_summary_details` byte-for-byte functionally compatible.

### Step 6: Run and confirm GREEN

Run the new module, then run the existing Work Order API and Fabric Store
summary consumers:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_work_order_summary
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.api.test_work_order
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_store_web_workspace
```

### Step 7: Commit the read model

```bash
git commit -m "feat: add work order movement and valuation summary"
```

## Task 5: Render the New Summary Only in ERPNext Desk

**Files:**

- Create: `essdee_yrp/public/js/WorkOrder/components/WorkOrderSummary.vue`
- Modify: `essdee_yrp/public/js/vue_plugins.js`
- Modify: `essdee_yrp/public/js/work_order.js`
- Modify: `essdee_yrp/test_work_order_summary.py`
- Create: `scripts/verify_work_order_summary_desk.mjs`

### Step 1: Add a failing wiring contract test

Extend `test_work_order_summary.py` with a static contract that requires:

- the new Vue component import and `EssdeeWorkOrderSummary` registration;
- `work_order.js` to call `get_work_order_summary`;
- the old `WOSummary` registration to remain available for other consumers;
- no Fabric Store or `/web` source file to be involved.

Run the module and confirm the contract fails before frontend changes.

### Step 2: Build the Vue component

Create `WorkOrderSummary.vue` with:

- Delivered and Received overview cards, split by UOM;
- deliverable table columns for Item, source GRN/child, Received Type, planned,
  issued and pending;
- receivable table columns for Item, planned, received, pending and planned
  process cost;
- debit table with safe Desk links to `YRP Debit`;
- valuation cards for posted input, posted process and posted output values;
- a clear note distinguishing planned process cost from posted valuation;
- compact empty/loading-safe states;
- responsive overflow inside the existing `wo_summary_html` field.

Use Frappe CSS variables and standard Desk styling. Do not introduce a separate
frontend dependency or modify `/web` components.

### Step 3: Register and mount the component

In `vue_plugins.js`, import and register
`frappe.production.ui.EssdeeWorkOrderSummary` without removing
`frappe.production.ui.WOSummary`.

In `work_order.js`, change only `mount_work_order_summary(frm)` so it:

- unmounts the prior instance safely;
- skips only unsaved documents;
- calls the new endpoint with the Work Order name;
- rejects stale responses using the existing request counter;
- mounts the new component;
- shows a contained Desk error state without breaking form refresh.

### Step 4: Add a Desk browser smoke script

Create `scripts/verify_work_order_summary_desk.mjs`, following the existing
Playwright/e2e helper conventions. It must open a supplied Work Order and assert:

- the summary component is visible;
- issued/received/pending sections render;
- source and Received Type appear when present;
- debit and valuation sections render;
- there are no page errors or failed summary requests.

The script must not access `/web`.

### Step 5: Build and run frontend checks

```bash
bench build --app essdee_yrp
bench --site erp-migration-test.site clear-cache
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_work_order_summary
```

Run the browser script later against the fresh persisted flow from Task 7.

### Step 6: Commit the Desk component

```bash
git commit -m "feat: show cloth movement summary on work orders"
```

## Task 6: Run Automated Non-Regression Verification

**Files:** none unless a genuine feature defect is found

### Step 1: Lint touched Python files

```bash
ruff check \
  essdee_yrp/fabric_source.py \
  essdee_yrp/fabric_substitution.py \
  essdee_yrp/overrides/inspection_entry.py \
  essdee_yrp/api/stock_transfer.py \
  essdee_yrp/api/work_order.py \
  essdee_yrp/test_inspection_entry_customization.py \
  essdee_yrp/test_fabric_source.py \
  essdee_yrp/test_fabric_substitution.py \
  essdee_yrp/api/test_stock_transfer.py \
  essdee_yrp/test_work_order_summary.py
```

### Step 2: Run the complete affected-flow suite

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_cloth_execution
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_inspection_entry_customization
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_source
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_fabric_substitution
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_delivery_challan_customization
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_goods_received_note_customization
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.api.test_work_order
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.api.test_stock_transfer
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_work_order_summary
bench --site erp-migration-test.site run-tests --app essdee_yrp \
  --module essdee_yrp.test_valuation_contract
```

### Step 3: Run the full Essdee test application

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp
```

If the full app suite exposes a pre-existing environmental failure, preserve the
complete command/output and separately prove that every affected-flow module is
green. Do not describe an unrun or failing full suite as passing.

### Step 4: Rebuild assets once more after final code

```bash
bench build --app essdee_yrp
bench --site erp-migration-test.site clear-cache
```

## Task 7: Verify with Fresh Persisted Entries

**Files:** none, except fixes justified by a reproduced defect

Use fresh, clearly prefixed documents on `erp-migration-test.site`; do not rely
only on mocked or existing P0 records.

### Step 1: Create and submit a fresh Knitting flow

Create a new versioned cloth execution set and submit:

- Cloth Program/Lot;
- Knitting Work Order;
- Knitting Delivery Challan;
- Knitting Goods Received Note with an Actual Dia physical Item.

Record names, exact GRN child name, Accepted stock balance, Lot conversion rows
and valuation before inspection.

### Step 2: Convert Accepted -> Rejected

Create and submit a `YRP Inspection Entry` against the exact Knitting GRN row,
then use the whitelisted Convert Stock action.

Verify from persisted documents/SQL:

- paired active SLE quantities and dimensions;
- converted status is written once;
- exact source availability decreases only for that GRN child;
- affected Lot conversion quantity decreases by the same amount;
- a repeated conversion attempt is rejected.

### Step 3: Convert Rejected -> Accepted

Create a second valid Inspection Entry sourcing the Rejected bin and convert a
partial quantity back to Accepted.

Verify exact source availability and Lot conversion increase by that partial
quantity, with the original GRN child lineage retained.

### Step 4: Continue Dyeing and Washing

Using the remaining effective Accepted source, create and submit:

- Dyeing WO/DC/GRN;
- Washing WO/DC/GRN.

Verify exact lineage, Received Type, quantities, Lot projection and active SLE
valuation at both stages. Do not create a Compacting transaction.

### Step 5: Exercise cross-bench transfer payloads

Call the receiver with a unique test source GRN containing mixed Accepted and
Rejected rows. Confirm the one submitted YRP Stock Entry and its SLEs preserve
the two row classifications. Also call an old payload with no Received Type and
confirm it uses the configured default.

### Step 6: Verify the Work Order Desk summary

For Knitting, Dyeing and Washing Work Orders:

- compare displayed planned/actual/pending values with saved child rows;
- compare source labels with exact GRN child lineage;
- compare debit values with `YRP Debit`;
- compare posted input/output/process values with active SLE sums;
- run `scripts/verify_work_order_summary_desk.mjs`;
- check the browser console/network log for errors.

### Step 7: Check unrelated controls

Open or exercise at least one legacy/non-versioned Work Order and one normal
Accepted transfer. Confirm they retain their existing behavior and the Desk form
does not fail when source lineage/valuation is absent.

## Task 8: Final Review and Delivery Commit

**Files:** all feature files from Tasks 1-5 only

1. Inspect `git diff` against the design and this plan.
2. Confirm no `/web`, Fabric Store, Compacting, migration/backfill, Purchase
   Order or unrelated dirty file entered any commit.
3. Run `git diff --check` and review all commits/status.
4. Perform a final code review focused on:
   - lock order and current reads;
   - exact GRN-child lineage;
   - configured Received Type instead of literals;
   - query permission/cancellation filters;
   - summary source grouping and valuation signs;
   - retained legacy API/component registration.
5. Fix review findings test-first and rerun the affected verification.
6. If a final integration commit is needed, stage only reviewed feature files
   and use:

```bash
git commit -m "test: verify post-P0 cloth corrections"
```

7. Report:
   - commit hashes;
   - automated test commands and counts;
   - fresh persisted document names;
   - inspection before/after availability and Lot quantities;
   - transfer row classifications;
   - summary versus ledger valuation figures;
   - any unrelated baseline failures separately.
