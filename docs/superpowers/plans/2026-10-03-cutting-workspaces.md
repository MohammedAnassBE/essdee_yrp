# Cutting Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Cutting Plan creation and ship full Cutting Order, Bulk LaySheets, and LaySheet Planner workflows inside the existing `/web` UI without Desk redirects.

**Architecture:** Add small controller-backed web service modules per workflow, retain the installed DocType controllers as the business authority, and compose each routed Vue workspace from focused list, editor, tab, rail, and action components. Shared list, lifecycle, print, Marker, LaySheet, temporal, and enterprise-theme components remain single implementations parameterized by context.

**Tech Stack:** Frappe 16/Python, Vue 3 Composition API, PrimeVue 4, Vite, Playwright verification scripts, existing Essdee/YRP controllers.

**Spec:** `docs/superpowers/specs/2026-10-03-cutting-workspaces-design.md`

## Global Constraints

- Keep every normal workflow inside `/web`; no Desk redirects or iframe reuse.
- Keep Frappe/YRP/Essdee controllers authoritative; browser payloads never own calculated quantities, statuses, stock, or optimizer results.
- Recheck record-level permission and document state on every server read or mutation.
- Preserve Vue 3, PrimeVue, PrimeIcons, the established enterprise CSS tokens, and the existing emerald Cutting theme.
- Keep files focused and readable; do not extend an already-large routed component into a workflow monolith.
- Preserve current dirty-worktree changes.
- Do not stage or commit. Each task ends with an uncommitted verification checkpoint because the user explicitly requested no commits.

## Review Focus

- A Draft modified after the browser loaded it must reject the stale save instead of overwriting the newer record; Tasks 2, 3, 5, and 7 add expected-`modified` conflict tests.
- A user who can read a parent but lacks child create/action permission must not create Marker, LaySheet, Detail, transfer, DC, or optimizer mutations through direct RPC; Tasks 1, 3, 4, 5, and 7 add direct permission-denial tests.
- Child-table rows must retain stable identities, and unknown/removed/duplicate browser rows must be rejected; Tasks 2, 3, 5, and 7 add row-integrity tests.
- Optimizer retry, polling, and selection must not let an old run or duplicate request overwrite a newer input snapshot; Task 7 adds job-deduplication and input-fingerprint tests.
- A partially completed Bulk LaySheets workflow must resume the correct split lot without unlocking or recreating downstream records; Tasks 5 and 6 add partial-state server and browser tests.

---

### Task 1: Cutting capabilities, navigation, routes, and lists

**Files:**
- Create: `essdee_yrp/cutting/web_capabilities.py`
- Create: `essdee_yrp/test_cutting_web_capabilities.py`
- Create: `frontend/src/api/cuttingWorkspaces.js`
- Modify: `frontend/src/departments/Cutting.vue`
- Modify: `frontend/src/departments/CuttingPlans.vue`
- Create: `frontend/src/departments/CuttingOrders.vue`
- Create: `frontend/src/departments/CuttingBulkLaySheets.vue`
- Create: `frontend/src/departments/CuttingLaySheetPlanners.vue`
- Modify: `frontend/src/router/index.js`
- Create: `scripts/verify_cutting_workspace_lists.mjs`
- Modify: `scripts/verify_cutting_permissions.mjs`

**Interfaces:**
- Produces: `get_capabilities() -> {"cutting-plans": Capability, "cutting-orders": Capability, "bulk-lay-sheets": Capability, "lay-sheet-planner": Capability, "reports": Capability}` where `Capability` includes `can_read` and `can_create`.
- Produces: frontend API `getCuttingCapabilities()`.
- Produces: named list routes `cutting-orders`, `cutting-bulk-lay-sheets`, and `cutting-lay-sheet-planners`. Each later workspace task adds its own record/new routes together with the real route components so no broken placeholder route is introduced.
- Consumes: existing `ListView`, `get_report_permissions`, and Frappe DocType permissions.

- [ ] **Step 1: Write failing capability tests**

Add tests proving all five destinations reflect their own read/create permission, unreadable destinations are omitted, and direct capability results do not grant one child DocType from a readable parent.

- [ ] **Step 2: Run the focused server test and verify RED**

Run:

```bash
cd /home/anas/pilot/benches/frappe-16/sites
../env/bin/python -m frappe.utils.bench_helper frappe --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_cutting_web_capabilities
```

Expected: FAIL because `web_capabilities.get_capabilities` does not exist.

- [ ] **Step 3: Implement the capability service and frontend API**

Use `frappe.has_permission` for `SD YRP Cutting Plan`, `SD YRP Cutting Order`, `SD YRP Cutting Bulk Lay Sheets`, `SD YRP Cutting Laysheet Planner`, LaySheet reports, and stock reports. Keep the old reports permission endpoint backwards compatible.

- [ ] **Step 4: Extend Cutting landing, routes, and list pages**

Render five permission-aware cards. Configure the three new `ListView` pages with the spec's default columns, status fields/options, newest-first order, Create toolbar actions, and row navigation. Add Create Cutting Plan to the existing list.

- [ ] **Step 5: Write and run the list/navigation browser test**

The test must assert five visible destinations when permitted, correct omission when denied, all four list contracts, Create visibility, row navigation, responsive containment, and no Desk URL.

Run:

```bash
cd /home/anas/pilot/benches/frappe-16/apps/essdee_yrp
node scripts/verify_cutting_workspace_lists.mjs
```

Expected before implementation: FAIL on missing destinations/routes. Expected after implementation: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run focused server/browser tests and `git diff --check`. Record results in `.superpowers/sdd/2026-10-03-cutting-workspaces/progress.md`.

---

### Task 2: Cutting Plan creation and Draft editor

**Files:**
- Create: `essdee_yrp/cutting/plan_editor.py`
- Create: `essdee_yrp/test_cutting_plan_web_editor.py`
- Create: `frontend/src/api/cuttingPlanEditor.js`
- Create: `frontend/src/departments/CuttingPlanEditorPage.vue`
- Create: `frontend/src/departments/cutting/plan/CuttingPlanEditor.vue`
- Create: `frontend/src/departments/cutting/shared/CuttingQuantityMatrix.vue`
- Modify: `frontend/src/departments/CuttingPlan.vue`
- Modify: `frontend/src/router/index.js`
- Create: `scripts/verify_cutting_plan_creation.mjs`

**Interfaces:**
- Produces: `get_editor(cutting_plan: str | None = None, lot: str | None = None) -> EditorPayload`.
- Produces: `load_lot_items(lot: str) -> QuantityMatrixPayload` using the existing `get_items` controller service.
- Produces: `save(values: dict, name: str | None = None, submit: bool = False, expected_modified: str | None = None) -> EditorPayload`.
- Produces: `change_status(name: str, action: Literal["submit", "cancel", "amend"], expected_modified: str | None = None) -> EditorPayload`.
- Produces: Vue editor emits `saved({name, docstatus, modified})` and `cancel`.
- Consumes: Task 1 routes/API conventions, existing `SDYRPCuttingPlan` validation and `FormView` visual shell.

- [ ] **Step 1: Write failing server editor tests**

Test authoritative defaults, Lot matrix loading, create permission, allowed-field mapping, derived-field rejection, child-row identity, unknown/duplicate row rejection, Draft save, Submit, existing Draft edit, stale conflict, and direct permission denial.

- [ ] **Step 2: Verify RED**

Run the new module and confirm failures are missing endpoint/contract failures, not fixture errors.

- [ ] **Step 3: Implement the thin Cutting Plan editor service**

Reload the Lot and source data, normalize only allowlisted values, pass `item_details` in the format consumed by the existing controller, call standard insert/save/submit, and serialize user-safe field errors plus effective lifecycle permissions.

- [ ] **Step 4: Re-run server tests to GREEN**

Run the focused module until all tests pass, then run existing `essdee_yrp.test_cutting_web_workspace` to protect the current record view.

- [ ] **Step 5: Write the failing browser creation flow**

Assert Create Cutting Plan opens `/web/cutting/plans/new`, no native temporal controls appear, Lot selection loads the colour/size matrix, Draft save replaces the route, Draft reopens editable, Save & Submit is permission-controlled, dirty close is confirmed, and no Desk redirect occurs.

- [ ] **Step 6: Implement the routed editor and matrix**

Use focused components rather than generic child-table rendering. On first save replace the route with the saved ID; on successful submit reload the normal workspace. Expose Edit for permitted Draft plans using the same editor.

- [ ] **Step 7: Verify browser GREEN and checkpoint**

Run:

```bash
node scripts/verify_cutting_plan_creation.mjs
node scripts/verify_web_ui_redesign.mjs plan-frame
git diff --check
```

Record results without committing.

---

### Task 3: Cutting Order and nested Cutting Order Detail server contracts

**Files:**
- Create: `essdee_yrp/cutting/order_workspace.py`
- Create: `essdee_yrp/cutting/order_detail_editor.py`
- Create: `essdee_yrp/test_cutting_order_web_workspace.py`
- Create: `essdee_yrp/test_cutting_order_detail_web_editor.py`
- Extend: `essdee_yrp/print_registry.py`

**Interfaces:**
- Produces: `get_order_editor(cutting_order: str | None = None, cutting_order_detail: str | None = None) -> OrderEditorPayload`.
- Produces: `save_order(values, name=None, submit=False, expected_modified=None) -> OrderEditorPayload`.
- Produces: `change_order_status(name: str, action: Literal["submit", "cancel", "amend"], expected_modified: str | None = None) -> OrderEditorPayload`.
- Produces: `get_order_workspace(cutting_order: str) -> OrderWorkspacePayload` containing details, completion data, planned data, actions, print formats, Markers, LaySheets, and permissions.
- Produces: `get_detail_editor(name: str | None = None, item: str | None = None) -> DetailEditorPayload`.
- Produces: `save_detail(values, name=None, expected_modified=None) -> DetailEditorPayload`.
- Consumes: existing Cutting Order controllers, Cutting Order Detail generation methods, `parent_adapter`, Marker/LaySheet parent fields, and print registry.

- [ ] **Step 1: Write failing Cutting Order Detail tests**

Test create/read/write permission, item defaults, colour/size/panel/set-item projections, authoritative derived combinations, stable child identities, unknown/duplicate row rejection, and stale edits.

- [ ] **Step 2: Write failing Cutting Order workspace tests**

Test Detail-derived matrix loading, Draft save/submit/edit/cancel/amend permissions, calculated-field protection, `get_cutting_order_planned_vs_actual`, completion projection, action eligibility, modified-desc Marker/LaySheet ordering, independent child permissions, and registered print formats.

- [ ] **Step 3: Verify both modules RED**

Run each test module separately and confirm missing web contracts are the failure reason.

- [ ] **Step 4: Implement Detail and Order service modules**

Keep generation/calculation inside the existing DocType methods. Serialize frontend shapes in the web modules, enforce expected `modified`, and parameterize related Marker/LaySheet queries by `cutting_order`.

- [ ] **Step 5: Run focused and parent-adapter tests to GREEN**

Run both new modules plus existing Cutting lifecycle/parent-adapter tests. Check permission failures are server-enforced, not only capability flags.

- [ ] **Step 6: Checkpoint without committing**

Run `git diff --check` and update the progress ledger.

---

### Task 4: Cutting Order `/web` workspace

**Files:**
- Create: `frontend/src/api/cuttingOrder.js`
- Create: `frontend/src/departments/CuttingOrder.vue`
- Create: `frontend/src/departments/CuttingOrderEditorPage.vue`
- Create: `frontend/src/departments/cutting/order/CuttingOrderEditor.vue`
- Create: `frontend/src/departments/cutting/order/CuttingOrderDetailDialog.vue`
- Create: `frontend/src/departments/cutting/order/CuttingOrderActions.vue`
- Create: `frontend/src/departments/cutting/order/CuttingOrderTabs.vue`
- Create: `frontend/src/departments/cutting/shared/CuttingParentSidebar.vue`
- Modify: `frontend/src/departments/cutting/CuttingPlanSidebar.vue`
- Modify: `frontend/src/departments/cutting/CuttingMarkerDialog.vue`
- Modify: `frontend/src/departments/cutting/CuttingLaySheetDialog.vue`
- Create: `scripts/verify_cutting_order_workspace.mjs`

**Interfaces:**
- Consumes: Task 3 payloads and Task 2 `CuttingQuantityMatrix`.
- Produces: `CuttingParentSidebar` props `{parentDoctype, parentName, parentField, data, loading, error}`.
- Produces: Marker and LaySheet dialogs accepting `{parentDoctype, parentName}` while preserving current `cuttingPlan` compatibility during migration.
- Produces: nested Detail dialog emitting `saved(detail)` so the Order editor selects it and reloads its matrix.

- [ ] **Step 1: Write a failing end-to-end browser test**

Cover list-to-workspace navigation, Create, nested Detail Create/Edit, quantity entry, Draft save/reopen, Submit, 80/20 ratio, fixed Details/Summary/Planned tabs, action buttons, Copy Completed, Marker/LaySheet filters and dialogs, print, permissions, and no Desk URL.

- [ ] **Step 2: Verify browser RED**

Run `node scripts/verify_cutting_order_workspace.mjs` and confirm it fails on the missing routed workspace.

- [ ] **Step 3: Implement editor and nested Detail workflow**

Keep the Detail dialog maximizable and dirty-safe. After save, select the returned detail, request authoritative matrix data, and preserve user-entered order quantities only where identities still match.

- [ ] **Step 4: Implement record workspace tabs and actions**

Compose the fixed header/tabs and 80% main pane from focused components. Use existing completion/copy and analytical components. Do not add repeated headings or technical helper copy.

- [ ] **Step 5: Generalize the parent rail and dialogs**

Move duplicated rail logic into `CuttingParentSidebar`; keep a thin Cutting Plan adapter to protect existing imports. Pass `cutting_order` filters and payload fields for Order records. Child Create/Submit/Cancel/Print buttons must derive from child permissions.

- [ ] **Step 6: Verify GREEN and Cutting Plan regression**

Run:

```bash
node scripts/verify_cutting_order_workspace.mjs
node scripts/verify_web_ui_redesign.mjs all
node scripts/verify_cutting_permissions.mjs
```

Expected: all pass. Run `git diff --check` and update the ledger without committing.

---

### Task 5: Bulk LaySheets server workspace

**Files:**
- Create: `essdee_yrp/cutting/bulk_laysheets_workspace.py`
- Create: `essdee_yrp/test_cutting_bulk_laysheets_web_workspace.py`
- Reuse: `essdee_yrp/essdee_yrp/doctype/sd_yrp_cutting_bulk_lay_sheets/sd_yrp_cutting_bulk_lay_sheets.py`

**Interfaces:**
- Produces: `get_editor(name: str | None = None) -> BulkEditorPayload`.
- Produces: `save(values, name=None, expected_modified=None) -> BulkWorkspacePayload`.
- Produces: `get_workspace(name: str) -> BulkWorkspacePayload` containing setup, rows, active LaySheet editor, bundles, row actions, bulk actions, related records, and permissions.
- Produces explicit web action endpoints that wrap existing controller methods: `create_laysheets`, `set_active_laysheet`, `generate_bundles`, per-lot/shared transfer actions, per-lot/bulk DC actions, grammage approval, print context, and label completion.
- Consumes: existing Bulk LaySheets controller validation and LaySheet services; it does not reimplement stock or workflow rules.

- [ ] **Step 1: Write failing payload and permission tests**

Test setup defaults, readable fields, active-lot payload, row/bulk action flags, child permission independence, and direct RPC denial.

- [ ] **Step 2: Write failing mutation and resume tests**

Test new save, stale edit, stable row identity, removed/retargeted locked-row rejection, source relationship validation, partial workflow resume, active-lot switching, and each wrapper invoking the existing controller with authoritative identifiers.

- [ ] **Step 3: Verify RED**

Run the focused module and confirm failures are missing web endpoints.

- [ ] **Step 4: Implement the thin web projection and wrappers**

Compute action visibility from current row status plus effective permission, reload the bulk document for every operation, accept no browser-provided calculated state, and return a refreshed workspace after mutation.

- [ ] **Step 5: Run GREEN plus native Bulk tests**

Run the new module and `essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.test_sd_yrp_cutting_bulk_lay_sheets`. Ensure the native suite still passes unchanged.

- [ ] **Step 6: Checkpoint without committing**

Run `git diff --check` and update the ledger.

---

### Task 6: Bulk LaySheets `/web` workspace

**Files:**
- Create: `frontend/src/api/cuttingBulkLaySheets.js`
- Create: `frontend/src/departments/CuttingBulkLaySheet.vue`
- Create: `frontend/src/departments/CuttingBulkLaySheetEditorPage.vue`
- Create: `frontend/src/departments/cutting/bulk/BulkSetupEditor.vue`
- Create: `frontend/src/departments/cutting/bulk/BulkWorkflowRail.vue`
- Create: `frontend/src/departments/cutting/bulk/BulkActiveLaySheet.vue`
- Create: `frontend/src/departments/cutting/bulk/BulkBundleTable.vue`
- Create: `frontend/src/departments/cutting/bulk/BulkActions.vue`
- Create: `frontend/src/departments/cutting/bulk/BulkDeliveryDialog.vue`
- Create: `frontend/src/departments/cutting/bulk/BulkPrintDialog.vue`
- Create: `scripts/verify_cutting_bulk_laysheets_workspace.mjs`

**Interfaces:**
- Consumes: Task 5 payloads, shared date field, Link field, lifecycle dialog, QZ printer API, and existing cloth/accessory editing vocabulary.
- Produces: active-row selection that persists current permitted editor values before switching and reloads the returned authoritative workspace.

- [ ] **Step 1: Write the failing full workflow browser test**

Cover Create setup, split rows, source Link filtering, save, Create Lay Sheets, 80/20 layout, equal workflow-card behavior, active-row switching, cloth/accessory changes, bundles, shared/per-lot transfer, DC, approval, printer selection, partial-state resume, permission-disabled actions, and no Desk navigation.

- [ ] **Step 2: Verify browser RED**

Run the new script and confirm the first failure is the missing workspace route/component.

- [ ] **Step 3: Implement setup and 80/20 workspace composition**

Keep the main header and action bar fixed, allow internal panel scrolling, and collapse to one column at narrow widths. Lock fields exactly when the server payload says they are locked.

- [ ] **Step 4: Implement active LaySheet and workflow actions**

Use in-page dialogs for generated transfers/DCs and printing. Every successful action consumes the returned refreshed workspace; failures remain inline and retain active-row context.

- [ ] **Step 5: Verify GREEN and shared regressions**

Run:

```bash
node scripts/verify_cutting_bulk_laysheets_workspace.mjs
node scripts/verify_cutting_stock_workflows.mjs
node scripts/verify_web_ui_redesign.mjs plan-frame
```

Run `git diff --check` and update the ledger without committing.

---

### Task 7: LaySheet Planner server workspace

**Files:**
- Create: `essdee_yrp/cutting/planner_workspace.py`
- Create: `essdee_yrp/test_cutting_laysheet_planner_web_workspace.py`
- Reuse: `essdee_yrp/essdee_yrp/doctype/sd_yrp_cutting_laysheet_planner/sd_yrp_cutting_laysheet_planner.py`

**Interfaces:**
- Produces: `get_editor(name: str | None = None) -> PlannerPayload`.
- Produces: `save(values, name=None, expected_modified=None) -> PlannerPayload`.
- Produces: `start_optimization(name: str, expected_modified: str) -> PlannerStatusPayload`.
- Produces: `get_status(name: str) -> PlannerStatusPayload`.
- Produces: `select_result(name: str, strategy: str, expected_modified: str | None = None) -> PlannerPayload`.
- Consumes: native `optimize`, `get_optimization_status`, `select_strategy`, input fingerprinting, validation, and long-worker lifecycle.

- [ ] **Step 1: Write failing editor tests**

Test defaults, Draft create/edit, unique size rows, zero handling, at least one positive quantity, tubular and limit validation, stale conflicts, result invalidation after input change, and direct permission denial.

- [ ] **Step 2: Write failing job/result tests**

Test queued/running input lock, duplicate Optimize suppression, old input fingerprint protection, completed/failed status projection, safe error text, retry eligibility, valid strategy selection, invalid/failed strategy rejection, and unknown result rows.

- [ ] **Step 3: Verify RED**

Run the focused module and verify missing web contracts are the cause.

- [ ] **Step 4: Implement the planner web module**

Wrap the existing controller functions, return normalized successful and failed outcome sections, include effective action flags, and never expose raw tracebacks.

- [ ] **Step 5: Run GREEN plus optimizer hardening tests**

Run the new module, the DocType planner tests if present, and `essdee_yrp.cutting.lay_optimizer.test_optimizer_hardening` plus direct integer-search tests.

- [ ] **Step 6: Checkpoint without committing**

Run `git diff --check` and update the ledger.

---

### Task 8: LaySheet Planner `/web` workspace

**Files:**
- Create: `frontend/src/api/cuttingLaySheetPlanner.js`
- Create: `frontend/src/departments/CuttingLaySheetPlanner.vue`
- Create: `frontend/src/departments/CuttingLaySheetPlannerEditorPage.vue`
- Create: `frontend/src/departments/cutting/planner/PlannerInputs.vue`
- Create: `frontend/src/departments/cutting/planner/PlannerOrderMatrix.vue`
- Create: `frontend/src/departments/cutting/planner/PlannerStatus.vue`
- Create: `frontend/src/departments/cutting/planner/PlannerStrategies.vue`
- Create: `frontend/src/departments/cutting/planner/PlannerLayPlan.vue`
- Create: `frontend/src/departments/cutting/planner/PlannerDeviationTable.vue`
- Create: `scripts/verify_cutting_laysheet_planner_workspace.mjs`

**Interfaces:**
- Consumes: Task 7 payloads and shared Link, numeric, temporal, table, Message, Tabs, lifecycle, and print components.
- Produces: active-only polling composable local to the planner workspace, stopped on terminal status, unmount, or route change.

- [ ] **Step 1: Write the failing browser lifecycle test**

Cover Create, validation, Draft save/reopen, three fixed tabs, Optimize, Queued/Running polling, input lock, Completed strategies, selected result, Lay Plan totals/deviation, Failed safe message, Retry, permissions, responsive matrices, and no Desk URL.

- [ ] **Step 2: Verify browser RED**

Run the script and confirm failure on the missing planner workspace.

- [ ] **Step 3: Implement Inputs and status lifecycle**

Use explicit table rows for size quantities, stop timers reliably, and avoid duplicate Optimize requests. Keep action/status information visible while tab contents scroll.

- [ ] **Step 4: Implement Strategies and Lay Plan views**

Render successful strategies as a comparable selector and unsuccessful outcomes separately. Use tabular numbers and contained horizontal scrolling for wide matrices.

- [ ] **Step 5: Verify GREEN and checkpoint**

Run the browser script, focused server module, `git diff --check`, and update the ledger without committing.

---

### Task 9: Whole-system permission, accessibility, regression, build, and migration pass

**Files:**
- Modify: `frontend/src/styles/enterprise.css` only for shared tokens/rules proven necessary by the four workspaces
- Modify: `scripts/verify_cutting_permissions.mjs`
- Create or modify: `.superpowers/sdd/2026-10-03-cutting-workspaces/progress.md`
- Modify only failing focused files discovered by verification

**Interfaces:**
- Consumes: all prior task contracts.
- Produces: one verified, migrated, uncommitted Cutting workspace implementation.

- [ ] **Step 1: Run all new focused server suites**

Run Tasks 1, 2, 3, 5, and 7 modules separately, then together. Report exact counts and any warnings.

- [ ] **Step 2: Run native/controller regressions**

Run existing Cutting workspace, Cutting reports, Cutting permissions, Bulk LaySheets, parent-adapter/lifecycle, Fabric Store, and print-registry tests. Fix only regressions caused by this feature.

- [ ] **Step 3: Run all new browser suites**

Run the four list/create/workspace scripts independently so failures have one owner. Then run them in the documented aggregate order.

- [ ] **Step 4: Run existing browser regressions**

Run:

```bash
node scripts/verify_web_ui_redesign.mjs all
node scripts/verify_cutting_permissions.mjs
node scripts/verify_cutting_stock_workflows.mjs
node scripts/verify_fabric_store_workspace.mjs all
```

- [ ] **Step 5: Perform the UI preflight audit**

At 1600px, 1280px, 900px, and 390px verify: one theme/accent/radius system, no text below 11px, readable contrast, no wrapped desktop action labels, visible focus, fixed tabs/actions where specified, internal table scrolling, no page-level overflow, clean loading/empty/error/permission states, and zero Desk navigation.

- [ ] **Step 6: Build production assets**

Run:

```bash
cd /home/anas/pilot/benches/frappe-16/apps/essdee_yrp
npm --prefix frontend run build
```

Expected: Vite build succeeds without missing imports or Vue compiler errors.

- [ ] **Step 7: Migrate the test site**

Run:

```bash
cd /home/anas/pilot/benches/frappe-16/sites
../env/bin/python -m frappe.utils.bench_helper frappe --site erp-migration-test.site migrate
```

Expected: migration and the `essdee_yrp` `/web` after-migrate build complete successfully.

- [ ] **Step 8: Fresh post-migration smoke verification**

Run the new Cutting list, Plan creation, Order, Bulk, and Planner browser suites once more against the migrated site.

- [ ] **Step 9: Final diff and status audit**

Run:

```bash
cd /home/anas/pilot/benches/frappe-16/apps/essdee_yrp
git diff --check
git status --short --branch
```

Confirm all changes remain uncommitted and distinguish task files from the user's unrelated dirty-worktree changes in the handoff.
