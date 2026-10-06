# Fabric Store Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the common Fabric Store Work Order, Purchase Order, Stock Transfer, and Stock Balance workflows inside the existing `/web` application.

**Architecture:** A dedicated `essdee_yrp.fabric_store.web_workspace` service exposes permission-safe document projections and mutations while existing YRP controllers remain authoritative. The Vue workspace reuses `ListView`, shared stock matrices, enterprise tokens, and one extracted Stock Balance component; Work Orders receive a full routed 80/20 workspace while other records remain in dialogs.

**Tech Stack:** Frappe 16, Python, Vue 3 Composition API, PrimeVue, Vite, Playwright browser verification.

**Spec:** `docs/superpowers/specs/2026-10-03-fabric-store-workspace-design.md`

## Global Constraints

- Do not commit; the user explicitly requested an uncommitted implementation.
- Do not add implicit fabric, warehouse, item, process, or department filters.
- Use Frappe permissions and document state on both server and client.
- Keep YRP/Essdee controllers authoritative for validation, calculations, and lifecycle effects.
- Keep the existing Cutting workspace behavior and regression suite green.
- Use existing PrimeVue and enterprise CSS; add no frontend dependency.
- Preserve the common field-aware Frappe-style filter component.

## Review Focus

- A user with partial DocType permissions sees only permitted tabs/actions and cannot call hidden actions directly.
- A readable non-fabric Work Order or Purchase Order remains visible because Fabric Store has no implicit scope filter.
- Pending Work Order and PO quantities are reloaded and revalidated when DC/GRN documents are saved.
- Draft, Submitted, and Cancelled records expose only valid lifecycle actions, including Amend where supported.
- Wide item matrices and nested dialogs remain usable at 900px and 390px without page-level overflow.

---

### Task 1: Fabric Store server contract and permission capabilities

**Files:**
- Create: `essdee_yrp/fabric_store/__init__.py`
- Create: `essdee_yrp/fabric_store/web_workspace.py`
- Create: `essdee_yrp/test_fabric_store_web_workspace.py`

**Interfaces:**
- Produces: `get_capabilities() -> dict`, `_permission_flags(doctype, doc=None) -> dict`, whitelisted operation/DocType maps, shared serializers, and lifecycle guards used by later tasks.

- [ ] **Step 1: Write failing server tests**

Cover capability omission for unreadable DocTypes, create/write/submit/cancel/amend/print flags, supported-operation whitelist rejection, and the absence of implicit business filters.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_web_workspace`

- [ ] **Step 3: Implement the permission and serialization foundation**

Supported documents are `YRP Work Order`, `Purchase Order`, `YRP Stock Entry`, `YRP Stock Reconciliation`, `YRP Stock Update`, `SD YRP Lot Transfer`, `YRP Delivery Challan`, and `YRP Goods Received Note`. Every public endpoint performs its own permission check.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Task 1 test command and require zero failures.

### Task 2: Extract the reusable Stock Balance report

**Files:**
- Create: `frontend/src/api/stockReports.js`
- Create: `frontend/src/components/reports/ReportShell.vue`
- Create: `frontend/src/components/reports/StockBalanceReport.vue`
- Create: `frontend/src/components/reports/reportUtils.js`
- Modify: `frontend/src/departments/CuttingReports.vue`
- Modify: `frontend/src/departments/cutting/reports/*.vue`
- Modify: `frontend/src/api/cuttingReports.js`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Produces: one common `StockBalanceReport` component and `getStockBalanceReport(filters)` API used by Cutting and Fabric Store.

- [ ] **Step 1: Extend browser verification to require one shared report implementation**

Assert Cutting still loads Stock Balance, uses custom Date fields, generates only on command, and preserves API filter names.

- [ ] **Step 2: Run the report suite and verify RED before extraction**

Run: `node scripts/verify_web_ui_redesign.mjs reports`

- [ ] **Step 3: Move report shell/utilities to common components and update imports**

Do not duplicate markup, query code, or scoped report CSS. Keep all five Cutting reports working.

- [ ] **Step 4: Run the report suite and frontend build**

Run: `node scripts/verify_web_ui_redesign.mjs reports`

Run: `npm run build --prefix frontend`

### Task 3: Fabric Store shell and common lists

**Files:**
- Create: `frontend/src/api/fabricStore.js`
- Modify: `frontend/src/departments/FabricStore.vue`
- Create: `frontend/src/departments/fabric-store/FabricWorkOrders.vue`
- Create: `frontend/src/departments/fabric-store/FabricPurchaseOrders.vue`
- Create: `frontend/src/departments/fabric-store/FabricStockTransfers.vue`
- Create: `frontend/src/departments/fabric-store/FabricReports.vue`
- Modify: `frontend/src/router/index.js`
- Create: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Consumes: `get_capabilities()` and the existing common `ListView`.
- Produces: four permission-aware tabs at `/fabric-store`, Work Order route navigation, Purchase Order row events, four stock-operation selectors with one active list, and the shared Stock Balance report.

- [ ] **Step 1: Write failing browser assertions for the shell**

Assert four tabs, fixed tab strip, no duplicated operation tab row, common list controls, no hidden Fabric Store filter, Work Order navigation, PO popup trigger, and Stock Balance reuse.

- [ ] **Step 2: Run the Fabric Store suite and verify RED**

Run: `node scripts/verify_fabric_store_workspace.mjs shell`

- [ ] **Step 3: Implement the tab shell and lists**

Use `ListView` directly with DocType-specific columns and slots. Keep the page full width and compact.

- [ ] **Step 4: Run the shell suite and verify GREEN**

Run the Task 3 suite command and require zero failures.

### Task 4: Full Work Order workspace and matrices

**Files:**
- Modify: `essdee_yrp/fabric_store/web_workspace.py`
- Modify: `essdee_yrp/test_fabric_store_web_workspace.py`
- Create: `frontend/src/departments/FabricWorkOrder.vue`
- Create: `frontend/src/departments/fabric-store/WorkOrderDetails.vue`
- Create: `frontend/src/departments/fabric-store/WorkOrderSummary.vue`
- Create: `frontend/src/departments/fabric-store/WorkOrderItemMatrix.vue`
- Create: `frontend/src/departments/fabric-store/WorkOrderActivityRail.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `frontend/src/router/index.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Produces: `get_work_order_workspace(work_order) -> {record, details, deliverables, receivables, summary, delivery_challans, goods_received_notes, permissions}` and the `/fabric-store/work-orders/:workOrderId` UI.

- [ ] **Step 1: Write failing server tests for the Work Order projection**

Assert production summary parity, grouped matrices, related-document relationship, modified-desc ordering, record-level read checks, and no process filter.

- [ ] **Step 2: Run the focused server tests and verify RED**

- [ ] **Step 3: Implement the Work Order projection using existing summary services**

Reuse `essdee_yrp.api.work_order.fetch_summary_details` and YRP grouping helpers rather than recalculating quantities in the browser.

- [ ] **Step 4: Write failing browser assertions for the Work Order route**

Assert 80/20 layout, title/ID/status, fixed Details/Summary tabs, matrix totals, equal-height DC/GRN rail, independent rail scroll, filters, and responsive collapse.

- [ ] **Step 5: Implement the routed Work Order workspace**

Reuse enterprise tokens and avoid duplicate headings/helper copy.

- [ ] **Step 6: Run server and browser tests and verify GREEN**

Run the focused Python module and `node scripts/verify_fabric_store_workspace.mjs work-order`.

### Task 5: Reusable document detail and lifecycle dialog

**Files:**
- Modify: `essdee_yrp/fabric_store/web_workspace.py`
- Modify: `essdee_yrp/test_fabric_store_web_workspace.py`
- Create: `frontend/src/components/documents/DocumentTransactionDialog.vue`
- Create: `frontend/src/components/stock/StockItemMatrix.vue`
- Create: `frontend/src/components/documents/DocumentPrintButton.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Produces: `get_document(doctype, name)`, `change_document_status(doctype, name, action, expected_modified=None)`, common read dialog with Submit/Cancel/Amend/Print actions.

- [ ] **Step 1: Write failing permission and lifecycle tests**

Cover Draft Submit, Submitted Cancel, Cancelled Amend, stale modified value, unsupported DocType, and direct unauthorized calls.

- [ ] **Step 2: Run server tests and verify RED**

- [ ] **Step 3: Implement server lifecycle endpoints through document APIs**

- [ ] **Step 4: Implement and verify the common dialog**

Use inline errors, dismissable mask, maximizable layout, contained scrolling, and explicit dirty-close confirmation where editing is enabled.

### Task 6: Work Order DC and GRN workflows

**Files:**
- Modify: `essdee_yrp/fabric_store/web_workspace.py`
- Modify: `essdee_yrp/test_fabric_store_web_workspace.py`
- Create: `frontend/src/departments/fabric-store/WorkOrderTransactionEditor.vue`
- Modify: `frontend/src/departments/fabric-store/WorkOrderActivityRail.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Produces: `get_work_order_transaction_editor(work_order, operation, delivery_challan=None)` and `save_work_order_transaction(work_order, operation, values, name=None, submit=False, expected_modified=None)`.

- [ ] **Step 1: Write failing tests for authoritative defaults and saving**

Use existing `work_order_actions` default services. Assert source Work Order reload, row-reference preservation, pending-quantity revalidation, Draft/Submit behavior, and permission denial.

- [ ] **Step 2: Run server tests and verify RED**

- [ ] **Step 3: Implement the DC/GRN endpoints**

Whitelisted editable fields only; insert and submit through the existing controllers.

- [ ] **Step 4: Implement the rail filters and nested editors**

- [ ] **Step 5: Run browser tests for create, view, submit, cancel, amend, refresh, and print visibility**

### Task 7: Purchase Order dialog and Create GRN

**Files:**
- Modify: `essdee_yrp/fabric_store/web_workspace.py`
- Modify: `essdee_yrp/test_fabric_store_web_workspace.py`
- Create: `frontend/src/departments/fabric-store/PurchaseOrderDialog.vue`
- Create: `frontend/src/departments/fabric-store/PurchaseOrderGrnEditor.vue`
- Modify: `frontend/src/departments/fabric-store/FabricPurchaseOrders.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Produces: `get_purchase_order_workspace(purchase_order)`, `get_purchase_order_grn_editor(purchase_order)`, and `save_purchase_order_grn(purchase_order, values, submit=False)`.

- [ ] **Step 1: Write failing server tests**

Assert all readable POs can open, Create GRN eligibility follows current controller requirements and permissions, defaults come from `get_purchase_order_defaults`, and save revalidates the PO.

- [ ] **Step 2: Run server tests and verify RED**

- [ ] **Step 3: Implement endpoints and grouped PO matrix projection**

- [ ] **Step 4: Implement the parent PO dialog and nested GRN editor**

- [ ] **Step 5: Verify dialog containment, mask close, refresh, lifecycle buttons, and print**

### Task 8: Context-free common stock-transfer editor

**Files:**
- Modify: `essdee_yrp/fabric_store/web_workspace.py`
- Modify: `essdee_yrp/test_fabric_store_web_workspace.py`
- Create: `frontend/src/components/stock/StockItemComposer.vue`
- Create: `frontend/src/components/stock/StockSelectionMatrix.vue`
- Create: `frontend/src/departments/fabric-store/FabricStockOperationDialog.vue`
- Modify: `frontend/src/departments/cutting/StockItemComposer.vue`
- Modify: `frontend/src/departments/cutting/CpmStockOperationDialog.vue`
- Modify: `frontend/src/departments/fabric-store/FabricStockTransfers.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Produces: `get_stock_operation_editor(operation)`, `get_stock_item_schema(operation, item)`, `save_stock_operation(operation, values, name=None, submit=False)`, and reusable stock composer callbacks that do not assume a Cutting Plan.

- [ ] **Step 1: Write failing server tests for all four operations**

Assert dynamic dimensions, no locked Cutting Plan values, correct purpose/update options, item schema parity, accepted payload fields, controller validation, Draft/Submit behavior, and permissions.

- [ ] **Step 2: Run server tests and verify RED**

- [ ] **Step 3: Extract the stock composer behind callback/API props**

Keep the Cutting adapter behavior identical while allowing Fabric Store to supply a context-free schema loader.

- [ ] **Step 4: Implement the four operation-specific field sets and save endpoints**

- [ ] **Step 5: Implement the Fabric Store creation dialog and list refresh**

- [ ] **Step 6: Run Cutting stock regressions and Fabric Store stock tests**

Run: `node scripts/verify_web_ui_redesign.mjs stock-transfers`

Run: `node scripts/verify_fabric_store_workspace.mjs stock-transfers`

### Task 9: Responsive, permission, and complete regression verification

**Files:**
- Modify: `frontend/src/styles/enterprise.css` only for genuinely shared tokens/patterns
- Modify: `scripts/verify_fabric_store_workspace.mjs`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Produces: verified Fabric Store behavior across live records and viewport sizes without Cutting regressions.

- [ ] **Step 1: Add final browser coverage**

Cover 1600x1000, 1280x800, 900x760, and 390x844; permission-restricted fixtures; loading/error/empty states; keyboard focus; 11px minimum text; no page overflow; no native date/time inputs.

- [ ] **Step 2: Run focused Python and browser suites**

Run Fabric Store Python tests, `node scripts/verify_fabric_store_workspace.mjs all`, and the existing Cutting suites.

- [ ] **Step 3: Build and migrate**

Run: `npm run build --prefix frontend`

Run: `bench --site erp-migration-test.site migrate` only if schema, fixtures, hooks, or installed metadata changed.

- [ ] **Step 4: Run final repository checks**

Run `git diff --check` on touched files and inspect `git status --short`. Confirm no commit was created.
