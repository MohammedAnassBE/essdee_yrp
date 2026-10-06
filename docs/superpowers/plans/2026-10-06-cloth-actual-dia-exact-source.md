# Cloth Actual-Dia and Exact-Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the new-transaction Desk flow `Cloth Program -> Knitting -> Dyeing -> Washing` with Actual Dia conversion, exact GRN-row source lineage, locked DC validation, and no regression to current legacy flows.

**Architecture:** Add one server-owned Lot conversion model and one isolated execution-scope module. Port the proven actual-dia/source-bucket algorithms into the current namespaced DocTypes and ERPNext `Item`, then join them to the existing WO/DC/GRN controllers only when `cloth_execution_version == 1` and saved execution keys are present. Keep legacy documents, current Cloth Program calculations, and every `/web`, garment, cutting, finishing, packing and rework path on their existing code.

**Tech Stack:** Frappe 16, Python, MariaDB row locks, ERPNext `Item`, YRP stock dimensions/SLEs, Frappe Desk JavaScript/Vue, Node test runner, Playwright, `pilot` bench CLI.

**Spec:** `docs/superpowers/specs/2026-10-06-cloth-actual-dia-exact-source-design.md`

## Global Constraints

- Scope is Desk only; do not change `frontend/`, `/web`, portal routes or Fabric Store workspace code.
- Supported version-1 route prefix is exactly default Knitting -> Colour-changing Dyeing -> one identity Washing step; Compacting execution is excluded.
- New `SD YRP Lot Fabric Conversion` Item fields link to ERPNext `Item`; never create a new `Item Variant` link.
- Existing child fields named `item_variant` stay unchanged because they already link to ERPNext `Item`.
- Existing/migrated Work Orders remain `cloth_execution_version = 0`; no data backfill or date-based cutoff.
- A version-0 WO cannot consume keyed stock; a version-1 WO cannot mix keyed and unkeyed sources.
- Draft Work Orders do not reserve source stock. Submitted DC/stock movement is the availability authority.
- Only `YRP Stock Settings.default_received_type` is eligible for the version-1 normal-production source pool.
- Use `QTY_TOLERANCE = 0.000001` for GRN reconciliation and normalize only absolute stock residues below `1e-9`.
- Preserve current Essdee same-warehouse behaviour exactly; do not broaden or tighten it.
- For qualified DC/GRN lifecycle actions, override `submit()`/`cancel()` to lock affected Lots before calling Frappe's base lifecycle; set a transaction-only flag and reject qualified `before_submit`/`before_cancel` paths that bypass it. After the Lot, lock transaction/source parents and rows by name, then base WOD/target rows. Legacy documents call `super()` directly.
- MariaDB on `erp-migration-test.site` is `REPEATABLE-READ`. Every post-lock query that decides availability, submitted consumption, receipt membership or conversion rows must use `FOR UPDATE` current reads; never make a decision from a plain consistent-snapshot `SELECT` after waiting.
- Preserve existing hook order and controller side effects; new handlers return immediately for unqualified documents.
- Do not modify the already-dirty `essdee_yrp/hooks.py`. Use the existing `EssdeeWorkOrder`, `EssdeeDeliveryChallan`, and `EssdeeGoodsReceivedNote` overrides plus the already-registered `fabric_grn.on_submit/on_cancel` handlers.
- Preserve all unrelated dirty worktree changes and stage only files owned by the current task.
- The Essdee index already contains user-staged deletions. Every commit must name the exact owned paths with `git commit --only <owned paths> -m ...`; never use plain `git commit`. Before committing, review `git diff HEAD -- <owned paths>` and run `git commit --dry-run --only <owned paths>`. After committing, confirm the pre-existing staged paths are still staged and no unrelated path entered the commit.
- Behavioural reference: Essdee `a83d353d908aa290686fd87d80615753ac1cb3a5`; YRP `85e1a0958cc36fcd1625f7d0bc99891b22942c3c`; local YRP diff SHA-256 `c5ffd39a1d79243d08eca9e03bf5448dd2a32e65fb9ed041176e2d442807cff6`.

## Review Focus

- Version boundary: old drafts, new all-legacy downstream WOs, all-keyed WOs and mixed sources must take the exact specified path without upgrading legacy records.
- Physical identity: same ERP Item with a different GRN row, Received Type, warehouse, set combination or stock dimension must remain a separate source bucket.
- Actual Dia validation: Dia-only substitution is accepted; changed parent Item, Colour, extra/missing attribute or invalid Dia is rejected before stock effects.
- Route aggregation: hidden colour routes must never multiply one physical GRN receipt or its valuation while their reference allocations remain conserved.
- Concurrency/cancellation: two DC submits cannot overconsume one bucket, and an upstream GRN cannot cancel after downstream consumption.

---

### Task 1: Freeze the baseline and add the execution-version boundary

**Files:**
- Create: `essdee_yrp/cloth_execution.py`
- Create: `essdee_yrp/test_cloth_execution.py`
- Modify: `essdee_yrp/fixtures/custom_field.json`
- Modify: `essdee_yrp/work_order_hooks.py`
- Modify: `essdee_yrp/overrides/work_order.py`
- Test: `essdee_yrp/api/test_cloth_program.py`
- Test: `essdee_yrp/api/test_work_order.py`
- Test: `essdee_yrp/test_work_order_customization.py`

**Interfaces:**
- Produces: `CLOTH_EXECUTION_VERSION = 1`.
- Produces: `get_supported_execution_route(ipd_doc) -> dict | None` with keys `knitting`, `dyeing`, `washing` and their normalized step positions.
- Produces: `stamp_cloth_execution_version(doc, method=None) -> None`, called by `EssdeeWorkOrder.before_insert`.
- Produces: `get_row_execution_parameters(row) -> dict` and `has_fabric_execution_key(row) -> bool`.
- Produces: `resolve_downstream_execution_version(work_order, source_rows, *, first_calculation: bool) -> int`.
- Produces: `is_versioned_cloth_work_order(doc_or_name) -> bool` and `qualifies_cloth_transaction(doc) -> bool` for later tasks.

- [ ] **Step 1: Record the pre-change regression baseline**

Run from the bench root:

```bash
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.api.test_cloth_program
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.api.test_work_order
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_source
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_valuation_contract
```

Expected: record every existing failure before editing; later tasks may not add failures. Do not fix unrelated failures.

- [ ] **Step 2: Write failing route/version tests**

Add tests named:

```python
def test_supported_route_is_exact_knitting_dyeing_identity_washing(): ...
def test_compacting_or_intervening_step_is_not_versioned(): ...
def test_existing_zero_version_never_upgrades_on_recalculate(): ...
def test_new_downstream_all_legacy_sources_downgrades_only_on_first_calculation(): ...
def test_new_downstream_all_keyed_sources_keeps_version_one(): ...
def test_mixed_keyed_and_legacy_sources_are_rejected(): ...
def test_version_zero_work_order_rejects_keyed_source(): ...
def test_later_version_one_recalculation_rejects_all_unkeyed_sources(): ...
```

Assert process roles come from `SD YRP IPD Settings`, normalized `get_fabric_steps()` shapes and the exact immediate ordering—not Process name strings.

- [ ] **Step 3: Run the new module and verify red**

Run:

```bash
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_cloth_execution
```

Expected: FAIL because the helper module and version field do not exist.

- [ ] **Step 4: Add the schema field and minimal scope helpers**

Add hidden, read-only, `no_copy` Int custom field `YRP Work Order-cloth_execution_version`, default `0`. Implement the interfaces above. `EssdeeWorkOrder.before_insert` uses only the route-candidate check to stamp new documents; all runtime helpers require version 1 and saved execution metadata. Do not add or reorder a `doc_events` hook.

- [ ] **Step 5: Run focused and baseline tests**

Run the Task 1 test module plus the four baseline modules from Step 1.

Expected: all new tests PASS; baseline results are no worse than recorded.

- [ ] **Step 6: Commit only Task 1 files**

```bash
git add essdee_yrp/cloth_execution.py essdee_yrp/test_cloth_execution.py
git diff --check HEAD -- essdee_yrp/cloth_execution.py essdee_yrp/test_cloth_execution.py essdee_yrp/fixtures/custom_field.json essdee_yrp/work_order_hooks.py essdee_yrp/overrides/work_order.py
git commit --dry-run --only essdee_yrp/cloth_execution.py essdee_yrp/test_cloth_execution.py essdee_yrp/fixtures/custom_field.json essdee_yrp/work_order_hooks.py essdee_yrp/overrides/work_order.py
git commit --only essdee_yrp/cloth_execution.py essdee_yrp/test_cloth_execution.py essdee_yrp/fixtures/custom_field.json essdee_yrp/work_order_hooks.py essdee_yrp/overrides/work_order.py -m "feat: isolate versioned cloth execution flow"
```

---

### Task 2: Add the Lot conversion model and pure Actual Dia engine

**Files:**
- Create: `essdee_yrp/essdee_yrp/doctype/sd_yrp_lot_fabric_conversion/__init__.py`
- Create: `essdee_yrp/essdee_yrp/doctype/sd_yrp_lot_fabric_conversion/sd_yrp_lot_fabric_conversion.json`
- Create: `essdee_yrp/essdee_yrp/doctype/sd_yrp_lot_fabric_conversion/sd_yrp_lot_fabric_conversion.py`
- Create: `essdee_yrp/fabric_substitution.py`
- Create: `essdee_yrp/test_fabric_substitution.py`
- Modify: `essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.json`
- Modify: `essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.py`
- Test: `essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/test_sd_yrp_lot.py`

**Interfaces:**
- Consumes: `get_supported_execution_route()` and `has_fabric_execution_key()` from Task 1.
- Produces: `allocate_route_quantity(route_qty: float, factors: list[dict]) -> list[dict]`.
- Produces: `build_actual_dia_factors(rows: list[dict], planned_qty: float) -> list[dict]`.
- Produces: `get_default_knitting_grn_context(grn) -> dict | None`.
- Produces: `lock_lot_for_default_knitting_grn(grn) -> dict | None`, called by the qualified GRN `submit()`/`cancel()` override before `super()`.
- Produces: `rebuild_lot_fabric_conversions_for_grn(grn) -> None` and `_rebuild_lot_fabric_conversions(lot, *, already_locked=False) -> None`.
- Produces: `get_actual_dia_factors(lot, production_detail, planned_item) -> list[dict]`.
- Produces: `get_process_conversion_index(lot, process_name=None, production_detail=None) -> dict` and `resolve_process_conversion(...) -> str` returning an ERP Item code.

- [ ] **Step 1: Write failing schema and pure-allocation tests**

Add tests for:

```python
def test_lot_conversion_schema_uses_item_links_and_read_only_fields(): ...
def test_conversion_table_is_server_owned_and_no_copy(): ...
def test_route_allocation_preserves_fractional_total(): ...
def test_actual_dia_factors_preserve_short_exact_and_excess_receipts(): ...
def test_split_actual_dias_group_under_one_planned_item(): ...
def test_multiple_grn_rebuild_is_idempotent(): ...
def test_unkeyed_historical_grn_is_ignored(): ...
def test_rebuild_stops_projection_after_washing(): ...
```

Schema assertions must require `planned_item`, `actual_item`, `route_item`, `knitting_planned_item`, and `knitting_actual_item` to link `Item`, and `received_type` to link `YRP Received Type`.

- [ ] **Step 2: Run the new tests and verify red**

Run:

```bash
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_substitution
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.test_sd_yrp_lot
```

Expected: FAIL on missing DocType, Lot fields and engine.

- [ ] **Step 3: Add the DocType and Lot fields**

Create the child schema exactly as the spec table. Add `actual_dia_conversion_tab`, `actual_dia_conversion_html` and hidden/read-only `lot_fabric_conversions` to `SD YRP Lot`. Make stale client saves preserve the current server-owned conversion rows.

- [ ] **Step 4: Port the pure conversion engine**

Adapt the proven functions from the reference `fabric_substitution.py`. Replace old DocType names and every `Item Variant` document/query with ERPNext `Item` and current attribute-link helpers. Restrict projection to the supported three-step prefix and ignore unkeyed GRNs. During a qualified GRN lifecycle, require the pre-`super()` Lot-lock flag, then rebuild from submitted GRN parents/rows and current conversion rows read with ordered `FOR UPDATE` queries.

- [ ] **Step 5: Run focused tests**

Expected: both Task 2 modules PASS, including idempotent rebuild and unkeyed-history isolation.

- [ ] **Step 6: Commit only Task 2 files**

```bash
git add essdee_yrp/essdee_yrp/doctype/sd_yrp_lot_fabric_conversion essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.json essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.py essdee_yrp/fabric_substitution.py essdee_yrp/test_fabric_substitution.py essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/test_sd_yrp_lot.py
git commit --dry-run --only essdee_yrp/essdee_yrp/doctype/sd_yrp_lot_fabric_conversion essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.json essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.py essdee_yrp/fabric_substitution.py essdee_yrp/test_fabric_substitution.py essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/test_sd_yrp_lot.py
git commit --only essdee_yrp/essdee_yrp/doctype/sd_yrp_lot_fabric_conversion essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.json essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.py essdee_yrp/fabric_substitution.py essdee_yrp/test_fabric_substitution.py essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/test_sd_yrp_lot.py -m "feat: add lot actual-dia conversion model"
```

---

### Task 3: Replace Item-level fabric availability with exact source buckets

**Files:**
- Modify: `essdee_yrp/fabric_source.py`
- Modify: `essdee_yrp/test_fabric_source.py`

**Interfaces:**
- Consumes: conversion lookup functions from Task 2.
- Produces: `project_output_attributes(actual_attrs, planned_input_attrs, planned_output_attrs) -> dict`.
- Produces: `prepare_source_pool(lot, production_detail, source_process, *, for_update=False) -> dict` with `buckets`, ordered source rows and eligible default Received Type. With `for_update=True`, lock the Lot first unless the lifecycle entry point already holds it, then source GRN parents and child rows by name using `FOR UPDATE` current reads.
- Produces: `validate_work_order_source_allocations(work_order) -> None`.
- Produces: `consume_source_bucket(pool, bucket_key, required_stock_qty) -> dict`.
- Preserves: current `get_source_process_options()`, `validate_source_demands()` and public availability response shape for unversioned WOs.

- [ ] **Step 1: Write failing bucket and availability tests**

Add/adapt tests named:

```python
def test_exact_bucket_separates_source_grn_item_received_type_and_dimensions(): ...
def test_factor_targets_do_not_reuse_one_grn_row_across_routes(): ...
def test_fully_exhausted_historical_rows_are_hidden(): ...
def test_draft_work_orders_do_not_reserve_but_submitted_dispatch_is_deducted(): ...
def test_default_received_type_is_the_only_normal_source(): ...
def test_actual_dia_carries_through_dyeing_and_identity_washing(): ...
def test_source_pool_rejects_changed_item_or_dimension(): ...
def test_legacy_availability_response_is_unchanged(): ...
```

- [ ] **Step 2: Run focused tests and verify red**

Run the `essdee_yrp.test_fabric_source` module. Expected: new tests FAIL against Item-level aggregation/draft reservation.

- [ ] **Step 3: Port the source-pool implementation**

Adapt `_project_receipt_buckets`, `prepare_source_pool`, `consume_source_bucket`, projection and validation from the reference branch. Use current `YRP Goods Received Note Item`, ERP `Item`, dynamic `get_dimension_fieldnames()`, `SD YRP Lot`, and Task 1 qualification. Preserve one shared order: Lot -> sorted source GRN parents -> sorted source child rows. Every source/consumption query after the Lot lock uses `FOR UPDATE`, so it sees commits made while this transaction waited under `REPEATABLE-READ`. Do not query old `Item Variant` or unprefixed tables.

- [ ] **Step 4: Run Task 3 plus Task 1/2 tests**

Expected: exact source tests PASS; legacy tests and conversion tests remain green.

- [ ] **Step 5: Commit Task 3**

```bash
git add essdee_yrp/fabric_source.py essdee_yrp/test_fabric_source.py
git commit --dry-run --only essdee_yrp/fabric_source.py essdee_yrp/test_fabric_source.py
git commit --only essdee_yrp/fabric_source.py essdee_yrp/test_fabric_source.py -m "feat: allocate fabric from exact grn sources"
```

---

### Task 4: Persist and protect the Work Order execution contract

**Files:**
- Modify: `essdee_yrp/api/work_order.py`
- Modify: `essdee_yrp/api/test_work_order.py`
- Modify: `essdee_yrp/work_order_hooks.py`
- Modify: `essdee_yrp/overrides/work_order.py`
- Modify: `essdee_yrp/public/js/work_order.js`
- Test: `essdee_yrp/test_cloth_execution.py`

**Interfaces:**
- Consumes: Task 1 version resolver and Task 3 source pools.
- Produces: `_fabric_execution_key(*parts) -> str` with stable `fabric-<24 hex>` output.
- Produces: `_execution_parameters(execution_key, matrix_key, source_bucket_key=None) -> str`, compact enough for inherited `additional_parameters` Data length.
- Produces: `_consolidate_default_knitting_rows(rows) -> list[dict]`.
- Produces: `_guard_untransacted_fabric_calculation(work_order) -> None`.
- Produces: `validate_fabric_execution_immutable(doc) -> None`, called by `EssdeeWorkOrder.before_update_after_submit`.
- Preserves: current `calculate_fabric_deliverables()` return keys and Cloth Program quantities when no substitution exists.

- [ ] **Step 1: Write failing WO contract tests**

Cover:

```python
def test_existing_cloth_program_items_quantities_and_allocations_are_unchanged(): ...
def test_new_knitting_rows_receive_stable_execution_keys(): ...
def test_default_knitting_consolidates_physical_output_but_keeps_route_allocations(): ...
def test_saved_manual_yarn_quantities_survive_reopen_and_partial_grn_scaling(): ...
def test_dyeing_uses_exact_actual_knitting_item_and_source_row(): ...
def test_washing_uses_exact_dyeing_grn_row(): ...
def test_recalculation_is_blocked_after_submitted_dc_or_grn(): ...
def test_update_after_submit_rejects_execution_contract_change(): ...
def test_garment_rework_finishing_and_packing_work_orders_are_unchanged(): ...
```

- [ ] **Step 2: Run `essdee_yrp.api.test_work_order` and verify red**

Expected: new exact-source/immutability tests FAIL; existing tests retain baseline results.

- [ ] **Step 3: Integrate source pools and execution metadata**

Port only the required reference functions: default-Knitting consolidation, manual-input validation, source-context merge, execution-key generation and transaction guard. Reuse current `fabric_reference_allocations`; do not add a second allocation table.

- [ ] **Step 4: Add update-after-submit protection and guarded Desk source context**

Add `EssdeeWorkOrder.before_update_after_submit` without changing `doc_events`; it validates the immutable contract and calls the base method if one exists. In `work_order.js`, show exact source labels only when the saved WO has version 1; do not add `/web` code or alter unversioned Calculate behaviour.

- [ ] **Step 5: Run Task 4 and all earlier modules**

Expected: tests PASS; no Item/quantity/allocation delta for the no-substitution fixture.

- [ ] **Step 6: Commit Task 4**

```bash
git add essdee_yrp/api/work_order.py essdee_yrp/api/test_work_order.py essdee_yrp/work_order_hooks.py essdee_yrp/overrides/work_order.py essdee_yrp/public/js/work_order.js essdee_yrp/test_cloth_execution.py
git commit --dry-run --only essdee_yrp/api/work_order.py essdee_yrp/api/test_work_order.py essdee_yrp/work_order_hooks.py essdee_yrp/overrides/work_order.py essdee_yrp/public/js/work_order.js essdee_yrp/test_cloth_execution.py
git commit --only essdee_yrp/api/work_order.py essdee_yrp/api/test_work_order.py essdee_yrp/work_order_hooks.py essdee_yrp/overrides/work_order.py essdee_yrp/public/js/work_order.js essdee_yrp/test_cloth_execution.py -m "feat: persist cloth work order execution contract"
```

---

### Task 5: Enforce exact source quantities on Delivery Challan submit

**Files:**
- Modify: `essdee_yrp/delivery_challan_hooks.py`
- Modify: `essdee_yrp/overrides/delivery_challan.py`
- Modify: `essdee_yrp/test_valuation_contract.py`
- Test: `essdee_yrp/test_delivery_challan_customization.py`

**Interfaces:**
- Consumes: `prepare_source_pool()`, `consume_source_bucket()` and `qualifies_cloth_transaction()`.
- Produces: `validate_exact_source_limits(doc, method=None) -> None`.
- Produces internal `_prepare_dispatch_source_pool(doc) -> dict` and `_consume_dispatch_source(pool, row) -> None`.
- Preserves: current `EssdeeDeliveryChallan` CPM, cutting, finishing, zero-placeholder and same-warehouse behaviour.

- [ ] **Step 1: Write failing exact-source DC tests**

Add tests for exact partial dispatch, aggregate exact dispatch, over-dispatch, wrong Item, wrong `source_grn_item`, wrong default Received Type, changed dimension, DC cancellation release, and correction-row rejection on versioned WOs.

- [ ] **Step 2: Add the concurrency tests before implementation**

Create uniquely named fixtures and explicitly commit them so independent DB connections can see them. In each worker thread call `frappe.init(site)`, `frappe.connect()`, and `frappe.set_user(test_user)`, wait on a `threading.Barrier` immediately before `dc.submit()`, then commit success or roll back failure and destroy the connection. Assert the successful total is at most the bucket and exactly one submit fails with the exact-source over-allocation error. Add an ordered overlapping-bucket test with a finite join timeout and assert both threads terminate without deadlock. Add a DC-submit versus source-GRN-cancel race test: both paths must finish within the timeout, and the valid serial outcome is either committed DC plus blocked cancel, or committed cancel plus rejected DC—never both. Add a stale-snapshot test where thread B performs a plain read first, waits behind thread A's Lot lock, and after A commits must see A's consumption through the post-lock `FOR UPDATE` query. Cancel and delete every committed fixture in `finally`/`tearDown`, then commit cleanup.

- [ ] **Step 3: Run focused tests and verify red**

Run:

```bash
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_valuation_contract
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_delivery_challan_customization
```

- [ ] **Step 4: Implement locked validation**

Call non-locking exact-source validation from `EssdeeDeliveryChallan.validate` after `super().validate()`. For a qualified document, `EssdeeDeliveryChallan.submit()`/`cancel()` locks the Lot and sets an in-memory lifecycle flag before calling `super()`; `before_submit`/`before_cancel` rejects a qualified bypass. During `before_submit`, lock sorted source GRN parents/rows with `FOR UPDATE`, repeat exact-source validation with current reads, and only then call `super().before_submit()` so base WOD locks are acquired last. Aggregate rows by exact bucket before consuming. The locks remain held through commit. Early-return for every unversioned/non-cloth DC. Do not change current same-warehouse behaviour or `doc_events`.

- [ ] **Step 5: Run focused, concurrency and existing DC tests**

Expected: all exact-source tests PASS; current customization tests remain green.

- [ ] **Step 6: Commit Task 5**

```bash
git add essdee_yrp/delivery_challan_hooks.py essdee_yrp/overrides/delivery_challan.py essdee_yrp/test_valuation_contract.py essdee_yrp/test_delivery_challan_customization.py
git commit --dry-run --only essdee_yrp/delivery_challan_hooks.py essdee_yrp/overrides/delivery_challan.py essdee_yrp/test_valuation_contract.py essdee_yrp/test_delivery_challan_customization.py
git commit --only essdee_yrp/delivery_challan_hooks.py essdee_yrp/overrides/delivery_challan.py essdee_yrp/test_valuation_contract.py essdee_yrp/test_delivery_challan_customization.py -m "feat: validate delivery challan exact fabric sources"
```

---

### Task 6: Add Actual Dia GRN execution and Lot lifecycle

**Files:**
- Modify: `essdee_yrp/fabric_grn.py`
- Modify: `essdee_yrp/overrides/goods_received_note.py`
- Modify: `essdee_yrp/test_valuation_contract.py`
- Modify: `essdee_yrp/api/test_work_order.py`
- Modify: `yrp/yrp/doctype/yrp_goods_received_note/yrp_goods_received_note.py`
- Modify: `yrp/stock/stock_ledger.py`
- Modify: `yrp/stock/test_reservation_enforcement.py`
- Test: `yrp/yrp/doctype/yrp_goods_received_note/test_purchase_order_grn.py`

**Interfaces:**
- Consumes: Task 1 qualification, Task 2 Lot lifecycle and Task 4 saved execution keys.
- Produces: `get_actual_dia_context(work_order) -> dict | None`.
- Produces: `get_saved_actual_dia_rows(grn, work_order) -> list[dict]`.
- Produces: `validate_actual_dia_rows(grn) -> None`.
- Produces: `_normalize_actual_dia_row_indexes(grn, receivables) -> None`.
- Produces: saved-execution input scaling for `populate_grn_deliverables()`.
- Adds a generic base controller flag `grn.flags.aggregate_physical_receipts`; base grouping changes shape only when that flag is true.

- [ ] **Step 1: Write failing Actual Dia validation tests**

Cover planned Dia, one changed Dia, split Dias, short/exact/excess quantities, and rejection of changed parent Item, Colour, other declared attribute, extra attribute, missing attribute and invalid Dia value.

- [ ] **Step 2: Write failing physical-stock and valuation tests**

Assert one positive SLE per physical Item/warehouse/UOM/dimension combination, hidden route allocations do not multiply stock, material value is conserved with the final remainder, exact WO inputs remain separate, and cancel reverses the saved shape without recalculation.

- [ ] **Step 3: Write failing lifecycle tests**

Assert Lot rows rebuild on versioned default-Knitting GRN submit/cancel, downstream Dyeing/Washing keep Knitting lineage, upstream cancellation is blocked after downstream consumption, and non-fabric/unversioned GRNs skip all new behaviour. Reuse the Task 5 DC-submit versus source-GRN-cancel race to prove both paths acquire the Lot before source/target rows. Add two concurrent Knitting GRN submits where the waiting transaction established an older snapshot; its `FOR UPDATE` rebuild must still include the first committed receipt.

- [ ] **Step 4: Run focused tests and verify red**

Run `essdee_yrp.test_valuation_contract`, `essdee_yrp.api.test_work_order`, and the two focused YRP modules listed under Files.

- [ ] **Step 5: Port GRN Actual Dia and saved execution handling**

Adapt the reference GRN functions to `YRP Goods Received Note`, `YRP Work Order`, ERP `Item`, current `SD YRP GRN Deliverable`, and current override ordering. For qualified documents, `EssdeeGoodsReceivedNote.submit()`/`cancel()` locks the Lot and sets an in-memory lifecycle flag before calling `super()`; qualified `before_submit`/`before_cancel` rejects a bypass. Set `aggregate_physical_receipts` in `before_submit` before base stock/valuation methods run. Rebuild/check using ordered `FOR UPDATE` queries for submitted GRN parents/rows, downstream consumption and current Lot conversion rows. Keep Lot submit/cancel rebuilding inside the already-registered `fabric_grn.on_submit/on_cancel` handlers; do not modify `doc_events`.

- [ ] **Step 6: Add guarded base receipt grouping and float normalization**

In base YRP, retain the current per-row positive-SLE path unless `grn.flags.aggregate_physical_receipts` is true. Preserve every physical GRN item -> output SLE link. Normalize only `abs(new_qty) < 1e-9` in outgoing stock handling.

- [ ] **Step 7: Run focused plus PO/garment regression tests**

Expected: versioned cloth tests PASS; unflagged Purchase Order and garment GRN receipt/SLE shapes are unchanged; reservation float test passes.

- [ ] **Step 8: Commit Essdee and YRP changes separately**

In `apps/yrp`:

```bash
git add yrp/yrp/doctype/yrp_goods_received_note/yrp_goods_received_note.py yrp/stock/stock_ledger.py yrp/stock/test_reservation_enforcement.py yrp/yrp/doctype/yrp_goods_received_note/test_purchase_order_grn.py
git commit --dry-run --only yrp/yrp/doctype/yrp_goods_received_note/yrp_goods_received_note.py yrp/stock/stock_ledger.py yrp/stock/test_reservation_enforcement.py yrp/yrp/doctype/yrp_goods_received_note/test_purchase_order_grn.py
git commit --only yrp/yrp/doctype/yrp_goods_received_note/yrp_goods_received_note.py yrp/stock/stock_ledger.py yrp/stock/test_reservation_enforcement.py yrp/yrp/doctype/yrp_goods_received_note/test_purchase_order_grn.py -m "feat: support guarded physical production receipts"
```

In `apps/essdee_yrp`:

```bash
git add essdee_yrp/fabric_grn.py essdee_yrp/overrides/goods_received_note.py essdee_yrp/test_valuation_contract.py essdee_yrp/api/test_work_order.py
git commit --dry-run --only essdee_yrp/fabric_grn.py essdee_yrp/overrides/goods_received_note.py essdee_yrp/test_valuation_contract.py essdee_yrp/api/test_work_order.py
git commit --only essdee_yrp/fabric_grn.py essdee_yrp/overrides/goods_received_note.py essdee_yrp/test_valuation_contract.py essdee_yrp/api/test_work_order.py -m "feat: execute cloth grn actual-dia contracts"
```

---

### Task 7: Add the guarded Desk experience

**Files:**
- Create: `essdee_yrp/public/js/Lot/ActualDiaConversions.vue`
- Create: `essdee_yrp/public/js/test_cloth_actual_dia.js`
- Modify: `essdee_yrp/public/js/vue_plugins.js`
- Modify: `essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.js`
- Modify: `essdee_yrp/public/js/goods_received_note.js`
- Modify: `essdee_yrp/public/js/work_order.js`
- Modify: `yrp/public/js/WorkOrder/GoodsReceivedNoteEditor.vue`
- Modify: `yrp/public/js/WorkOrder/WorkOrderItemEditor.vue`

**Interfaces:**
- Consumes: `cloth_execution_version`, Lot conversion rows, `get_actual_dia_context()` and saved physical GRN rows.
- Produces: read-only `frappe.production.ui.ActualDiaConversions` Vue registration.
- Adds `allowExcess` and `aggregatePhysicalRows` props to the base editor; default `false` preserves every current caller.
- Produces pure exported/helper functions for physical row grouping that can run under `node --test`.

- [ ] **Step 1: Write failing Node tests**

Test identical physical route aggregation, Actual Dia split creation/removal, Received Type split aggregation, quantity not capped when `allowExcess=true`, and unchanged behaviour when both props are false.

Run:

```bash
node --test apps/essdee_yrp/essdee_yrp/public/js/test_cloth_actual_dia.js
```

Expected: FAIL before helpers/components are added.

- [ ] **Step 2: Implement Lot read-only conversion rendering**

Port the reference component with current field names (`planned_item`, `actual_item`, `actual_quantity`) and mount only when the Lot has rows. Do not alter Cloth Program buttons or `/web` components.

- [ ] **Step 3: Add guarded Work Order/GRN UI**

Expose source detail in the existing calculated Work Order dialog only for version 1. For versioned default-Knitting GRNs, show Actual Dia splits and pass `allowExcess`/`aggregatePhysicalRows`; unversioned forms pass neither prop and render identically.

- [ ] **Step 4: Run Node tests and build assets**

```bash
node --test apps/essdee_yrp/essdee_yrp/public/js/test_cloth_actual_dia.js
pilot --bench frappe-16 frappe build --app yrp
pilot --bench frappe-16 frappe build --app essdee_yrp
```

Expected: Node PASS; both builds exit 0.

- [ ] **Step 5: Commit YRP and Essdee UI changes separately**

Commit base editor props in `apps/yrp`, then commit the guarded Essdee consumers/components in `apps/essdee_yrp`. Do not stage any `frontend/` file.

---

### Task 8: Migrate, run the complete regression matrix, and exercise Desk end to end

**Files:**
- Create: `scripts/verify_cloth_actual_dia_desk.mjs`
- Modify only if a failing owned test requires it: files from Tasks 1-7
- Test: all modules named below

**Interfaces:**
- Consumes: complete Tasks 1-7.
- Produces: repeatable Playwright Desk smoke script using `scripts/e2e-lib.mjs` and `/home/anas/.claude/playwright`.
- Produces: final verification evidence for schema, Python, JS, build and browser flow.

- [ ] **Step 1: Migrate the target test site**

```bash
pilot --bench frappe-16 frappe --site erp-migration-test.site migrate
pilot --bench frappe-16 frappe --site erp-migration-test.site clear-cache
```

Expected: schema sync and fixture import succeed; no historical conversion rows are created.

- [ ] **Step 2: Verify the schema cutoff on real site metadata**

Use `frappe.execute`/console assertions to confirm:

- `SD YRP Lot Fabric Conversion` Item fields link `Item`;
- `cloth_execution_version` exists and old WOs are still 0/unset;
- no existing Lot has server-created `lot_fabric_conversions` solely from migration.

- [ ] **Step 3: Run all focused Python suites**

```bash
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_cloth_execution
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_substitution
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_source
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.api.test_work_order
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_valuation_contract
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_delivery_challan_customization
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app yrp --module yrp.stock.test_reservation_enforcement
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app yrp --module yrp.yrp.doctype.yrp_goods_received_note.test_purchase_order_grn
```

Expected: all PASS, or only pre-recorded unrelated baseline failures remain.

- [ ] **Step 4: Run full app regressions**

```bash
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app yrp
pilot --bench frappe-16 frappe --site erp-migration-test.site run-tests --app essdee_yrp
```

Expected: no new failures compared with Task 1 baseline. Pay special attention to Cloth Program, Work Order, cutting, finishing, packing, rework, PO GRN and same-warehouse tests.

- [ ] **Step 5: Run JS tests and production builds again**

Run Task 7 Node tests and both app builds. Expected: all exit 0.

- [ ] **Step 6: Write and run the Playwright Desk smoke flow**

The script must create uniquely named test records and verify through Desk:

1. build/recalculate a Cloth Program;
2. create/calculate a version-1 Knitting WO;
3. create/submit its DC;
4. create a Knitting GRN and split one planned output into two Actual Dias;
5. submit and verify the Lot read-only conversion table and stock totals;
6. create a Dyeing WO from one exact bucket;
7. submit a partial DC and verify an over-dispatch attempt is blocked;
8. submit Dyeing GRN and verify exact lineage;
9. create Washing WO from that Dyeing GRN;
10. submit Washing DC/GRN and verify final stock, pending quantity and lineage;
11. verify an unconsumed cancel/rebuild branch;
12. open one legacy/unversioned WO/GRN and assert no new controls appear.

Run:

```bash
node apps/essdee_yrp/scripts/verify_cloth_actual_dia_desk.mjs
```

Expected: script exits 0 and prints each stage's document names and verified quantities.

- [ ] **Step 7: Reconcile final changes and commit verification assets**

Check `git status` separately in `apps/yrp` and `apps/essdee_yrp`. Ensure only owned files were committed, `essdee_yrp/hooks.py` is byte-for-byte unchanged by this implementation, and all pre-existing dirty/staged files remain preserved. Commit the Playwright script and any owned test-only corrections with the same exact-path `git commit --only` procedure.

- [ ] **Step 8: Request final code review before completion**

Use the `requesting-code-review` skill against the complete implementation diff. Fix only in-scope findings, rerun the affected focused suites, then use `verification-before-completion` before claiming success.
