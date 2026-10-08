# Sewing Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the polished `/web` Sewing workspace with three cards, Supplier-scoped operational/reporting tabs, and a reusable global Attendance Strength Report.

**Architecture:** Keep `essdee_yrp.sewing` as the server-side business owner and add only permission capabilities, missing report parity, and safety guards. Build route-backed Vue 3 workspaces whose active tab alone fetches data, with a shared Sewing Unit context and focused components for each matrix/report. Reuse the existing enterprise shell, fields, dialogs, reports, tables, and error normalization.

**Tech Stack:** Frappe 16/Python, Vue 3 Composition API, PrimeVue 4, Vue Router 4, Vite 5, Playwright browser verification scripts.

**Spec:** `docs/superpowers/specs/2026-10-08-sewing-workspace-design.md`

## Global Constraints

- The `/web/sewing` launcher has exactly three cards: `Sewing Plan`, `Reports`, and `Attendance Report`.
- Sewing Plan has exactly five tabs: Dashboard, Data Entry, Entries, Consumption, Closed Work Order GRN.
- Reports has exactly five tabs: Status Summary, DPR, SCR, Monthly Summary, Item Summary.
- The selected Sewing Unit is a `Supplier` filtered by `is_company_location = 1`; every Sewing Plan and Reports endpoint must apply that Supplier server-side.
- Attendance Report is global and contains only Strength Report date/time inputs and returned results; do not add Supplier, HR department, HR location, designation, or employee-selection requirements.
- Preserve Vue 3, PrimeVue, Vite, Frappe RPC, PrimeIcons, and existing `--erp-*` tokens; add no component library or Sewing-only theme.
- Reuse Frappe 16 domain services and stronger permission/validation behavior; do not transplant Frappe 15 `ignore_permissions` or browser-trusting payloads.
- Only the active tab mounts and fetches; changing Supplier invalidates stale requests rather than allowing an older response to overwrite current context.
- All errors use the shared application popup/normalizer, preserve entered values, and never expose raw tracebacks, HTML, or status-only messages.
- Tables and matrices own horizontal overflow; the page must not horizontally scroll at 390, 900, 1280, or 1600 px widths.
- Preserve unrelated dirty-worktree changes and stage only files named by the active task.

## Review Focus

- A slow response for Supplier A arriving after the user selects Supplier B must be ignored; Task 4 browser tests pin request-generation behavior.
- A direct `/web/sewing/plans` or `/web/sewing/reports` URL without `supplier` must show the selection state and make no data call; Task 4 tests pin this.
- Concurrent Data Entry or Closed Work Order GRN requests must not exceed current remaining quantity; Tasks 2 and 7 exercise locking/current-state rejection.
- An HR timeout or invalid upstream response must leave the Sewing workspace usable and show a plain-language popup; Task 10 covers both failures.
- Wide dynamic size/colour matrices must remain usable on a 390 px viewport without page-level overflow or discarded edits; Tasks 5, 6, 8, and 11 test responsive containment and value preservation.

---

### Task 1: Sewing web capabilities and catalog registration

**Files:**
- Create: `essdee_yrp/sewing/web_workspace.py`
- Modify: `essdee_yrp/www/web.py`
- Modify: `essdee_yrp/hooks.py`
- Create: `essdee_yrp/test_sewing_web_workspace.py`

**Interfaces:**
- Consumes: Frappe `has_permission(doctype, ptype)` and the installed `SD YRP Sewing Plan`, `SD YRP Sewing Plan Entry Detail`, and `YRP Goods Received Note` permissions.
- Produces: whitelisted `essdee_yrp.sewing.web_workspace.get_capabilities() -> {sections: {plans, reports, attendance}, plan_actions, reports}` for the launcher and tab shells.

- [ ] **Step 1: Write failing capability and catalog tests**

Add `TestSewingWebWorkspace` cases asserting:

- `get_capabilities()` returns only readable sections;
- `plans` includes create/write/delete capability derived from entry/plan permissions;
- `reports` and `attendance` require Sewing Plan read/report access;
- `SD YRP Sewing Plan` and `SD YRP Sewing Plan Entry Detail` appear in both `/web` permission catalogs;
- the endpoint is authenticated and never guest-whitelisted.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_web_workspace`

Expected: FAIL because `web_workspace` and catalog entries do not exist.

- [ ] **Step 3: Implement the capability contract**

Create `get_capabilities()` with independent `can_read`, `can_create`, `can_write`, `can_delete`, `can_submit`, and `can_report` flags. Keep labels and section keys server-owned. Add the two Sewing doctypes to `WEB_DOCTYPES` and `yrp_web_doctype_catalog`.

- [ ] **Step 4: Run focused tests and verify pass**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add essdee_yrp/sewing/web_workspace.py essdee_yrp/www/web.py essdee_yrp/hooks.py essdee_yrp/test_sewing_web_workspace.py
git commit -m "feat: expose sewing web capabilities"
```

### Task 2: Mutation safety and Supplier isolation

**Files:**
- Modify: `essdee_yrp/sewing/entry.py`
- Modify: `essdee_yrp/sewing/read_models.py`
- Modify: `essdee_yrp/test_sewing_business_logic.py`

**Interfaces:**
- Consumes: `SD YRP MRP Settings.previous_day_entries`, the existing locked Data Entry sequence validation, and `get_consumption_mapping_data(lot, supplier)`.
- Produces: `_assert_entry_cancellable(entry) -> None`; `get_sewing_consumption_print_data(ipd, lot, supplier)` with explicit Supplier preservation; existing public methods remain backward compatible where safe.

- [ ] **Step 1: Write failing server-guard tests**

Add cases asserting:

- `cancel_sewing_plan_entry(doc_id)` rejects an entry outside the latest configured distinct entry dates even when delete permission exists;
- the same endpoint permits and deletes an eligible entry;
- consumption read/save rejects a Supplier that has no plan for the selected Lot;
- consumption print data uses the explicitly supplied Supplier and does not select an arbitrary plan;
- two current-state Data Entry validations cannot together exceed the predecessor balance.

- [ ] **Step 2: Run the focused mutation tests and verify failure**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_business_logic --test test_entry_cancellation_honours_previous_entry_days --test test_consumption_print_preserves_supplier`

Expected: FAIL on missing date guard and explicit print Supplier contract.

- [ ] **Step 3: Implement cancellation eligibility and consumption scoping**

Compute cancellable dates from the latest `previous_day_entries` distinct dates for the entry's Supplier plans, recheck delete permission, and throw a titled business validation before delete. Require the selected Supplier to own at least one plan for the Lot on consumption reads/saves, and accept/pass Supplier explicitly in the print endpoint.

- [ ] **Step 4: Run all Sewing business-logic tests**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_business_logic`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add essdee_yrp/sewing/entry.py essdee_yrp/sewing/read_models.py essdee_yrp/test_sewing_business_logic.py
git commit -m "fix: enforce sewing mutation scope"
```

### Task 3: Status Summary and DPR report parity

**Files:**
- Create: `essdee_yrp/sewing/reporting.py`
- Modify: `essdee_yrp/sewing/read_models.py`
- Modify: `essdee_yrp/essdee_yrp/doctype/sd_yrp_sewing_plan/sd_yrp_sewing_plan.py`
- Create: `essdee_yrp/test_sewing_reports.py`

**Interfaces:**
- Consumes: `_plans(supplier)`, configured input types/status rows from `SD YRP MRP Settings`, persisted Sewing entries, Work Order deliverable/receivable quantities, and FI dates.
- Produces: `get_sp_status_summary(supplier) -> {header1, header2, header3, data}` with operational derived fields; `get_sewing_plan_dpr_summary(supplier, from_date, to_date, work_station=None, input_type=None) -> {reports, pending_fi}`.

- [ ] **Step 1: Write failing report-contract tests**

Create fixtures and assertions for:

- Status Summary limits data to open Work Orders owned by the selected Supplier;
- totals include order, delivered, GRN, configured stages, pre-final, and final values;
- rows include FI/input/last-output dates, readiness state, running days, line stock, checking stock, and GRN pending;
- another Supplier's rows never appear;
- DPR summary rejects `from_date > to_date`;
- a date range returns one report per date with data and a deduplicated `pending_fi` list;
- pending FI blocks only through an explicit response contract and never looks like an unexplained empty success.

- [ ] **Step 2: Run report tests and verify failure**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_reports`

Expected: FAIL on omitted summary values and missing DPR summary.

- [ ] **Step 3: Implement focused reporting services**

Move new derived-report assembly into `reporting.py`, keep existing import paths as delegating wrappers, batch related rows by plan/Work Order, and export `get_sewing_plan_dpr_summary` through the Sewing Plan DocType module. Do not import Frappe 15 code or trust client-calculated totals.

- [ ] **Step 4: Run report and existing Sewing tests**

Run:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_reports
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_business_logic
```

Expected: PASS with no changed legacy endpoint names.

- [ ] **Step 5: Commit**

```bash
git add essdee_yrp/sewing/reporting.py essdee_yrp/sewing/read_models.py essdee_yrp/essdee_yrp/doctype/sd_yrp_sewing_plan/sd_yrp_sewing_plan.py essdee_yrp/test_sewing_reports.py
git commit -m "feat: complete sewing report read models"
```

### Task 4: Route-backed Sewing shell and three-card launcher

**Files:**
- Create: `frontend/src/api/sewing.js`
- Create: `frontend/src/departments/sewing/useSewingContext.js`
- Create: `frontend/src/departments/sewing/SewingUnitPicker.vue`
- Create: `frontend/src/departments/sewing/SewingWorkspaceShell.vue`
- Create: `frontend/src/departments/sewing/SewingLauncher.vue`
- Modify: `frontend/src/departments/Sewing.vue`
- Modify: `frontend/src/router/index.js`
- Create: `scripts/verify_sewing_workspace.mjs`

**Interfaces:**
- Consumes: Task 1 `get_capabilities()` and `searchLink("Supplier", ..., {is_company_location: 1})`.
- Produces: routes `/sewing/plans`, `/sewing/reports`, `/sewing/attendance`; `useSewingContext()` returning `{supplier, setSupplier, requestGeneration, beginRequest, isCurrent}`; `SewingWorkspaceShell` slots for active content.

- [ ] **Step 1: Write failing launcher/context browser checks**

Add `launcher` suite assertions for:

- exactly three card labels and hrefs;
- permission-hidden cards and capability retry state;
- Supplier search request contains `is_company_location: 1`;
- choosing a unit writes `?supplier=<name>` and both scoped cards preserve it;
- direct plan/report routes without Supplier show selection guidance and issue no Sewing data request;
- rapid A→B selection ignores A's delayed response;
- no page-level overflow at 390/900/1280/1600 px.

- [ ] **Step 2: Run the launcher suite and verify failure**

Run: `node scripts/verify_sewing_workspace.mjs launcher`

Expected: FAIL because the launcher/routes/context are absent.

- [ ] **Step 3: Implement API constants, context, launcher, and routes**

Keep dotted Frappe method names only in `api/sewing.js`. Make `Sewing.vue` render `SewingLauncher`. Persist Supplier in `route.query.supplier`, expose a monotonically increasing request generation, and add lazy route components for the three destination pages.

- [ ] **Step 4: Run launcher suite and production build**

Run:

```bash
node scripts/verify_sewing_workspace.mjs launcher
yarn --cwd frontend build
```

Expected: PASS; Vite build exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sewing.js frontend/src/departments/Sewing.vue frontend/src/departments/sewing frontend/src/router/index.js scripts/verify_sewing_workspace.mjs
git commit -m "feat: add sewing web workspace shell"
```

### Task 5: Dashboard and Data Entry tabs

**Files:**
- Create: `frontend/src/departments/sewing/SewingPlanWorkspace.vue`
- Create: `frontend/src/departments/sewing/plan/SewingDashboard.vue`
- Create: `frontend/src/departments/sewing/plan/SewingDataEntry.vue`
- Create: `frontend/src/departments/sewing/components/SewingQuantityMatrix.vue`
- Modify: `frontend/src/api/sewing.js`
- Modify: `scripts/verify_sewing_workspace.mjs`

**Interfaces:**
- Consumes: `get_dashboard_data(supplier)`, `get_data_entry_data(supplier, lot)`, `submit_data_entry_log(payload)`, `update_sewing_plan_data(payload)`, shared Link/Date/Time/error components, and Task 4 context.
- Produces: five-tab lazy `SewingPlanWorkspace`; reusable `SewingQuantityMatrix` keyed by authoritative `order_detail`; Data Entry payload matching Frappe 16 trusted-row contract.

- [ ] **Step 1: Add failing dashboard/data-entry browser checks**

Mock the four endpoints and assert:

- the plan workspace exposes exactly five approved tabs and mounts only the active tab;
- Dashboard groups configured input quantities and handles empty/error/refresh states;
- Data Entry Lot choices are Supplier-scoped;
- selecting plan/input/work station/received type/date/time and quantities sends `order_detail` identities, not browser-authored variants;
- missing controls, negative quantities, and excessive server-rejected quantities preserve edits and show the shared popup;
- inspection update/revert uses only `pre_final` or `final_inspection`;
- wide size matrices contain their scroll at 390 px and retain edited quantities after resize.

- [ ] **Step 2: Run the plan-entry suite and verify failure**

Run: `node scripts/verify_sewing_workspace.mjs plan-entry`

Expected: FAIL because the plan tabs do not exist.

- [ ] **Step 3: Implement Dashboard and Data Entry**

Use compact metric/table presentation for Dashboard. Build Data Entry from returned Lot→plan→colour→size structures, keep business calculations display-only, disable double submission, and reload only the saved plan matrix after success.

- [ ] **Step 4: Run browser suite and build**

Run:

```bash
node scripts/verify_sewing_workspace.mjs plan-entry
yarn --cwd frontend build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sewing.js frontend/src/departments/sewing scripts/verify_sewing_workspace.mjs
git commit -m "feat: add sewing dashboard and data entry"
```

### Task 6: Entries and Consumption tabs

**Files:**
- Create: `frontend/src/departments/sewing/plan/SewingEntries.vue`
- Create: `frontend/src/departments/sewing/plan/SewingConsumption.vue`
- Create: `frontend/src/departments/sewing/components/SewingConsumptionTable.vue`
- Modify: `frontend/src/departments/sewing/SewingPlanWorkspace.vue`
- Modify: `frontend/src/api/sewing.js`
- Modify: `scripts/verify_sewing_workspace.mjs`

**Interfaces:**
- Consumes: `get_sewing_plan_entries`, `cancel_sewing_plan_entry`, `get_supplier_lots`, `get_consumption_mapping_data`, `save_consumption_data`, Task 2 eligibility/scoping, and `SewingQuantityMatrix`.
- Produces: filterable entry groups with permission/date-gated cancellation; consumption editor that round-trips `sections` and `cloth_acc_data` for the selected Supplier+Lot.

- [ ] **Step 1: Add failing Entries/Consumption checks**

Assert:

- Entries sends Supplier, Work Station, Input Type, and Lot filters and groups by entry date;
- cancel appears only for `is_cancellable`, requires shared confirmation, refreshes on success, and surfaces server eligibility rejection;
- Consumption cannot fetch before Supplier+Lot selection;
- Lot link calls the Supplier-scoped query;
- section and cloth-accessory edits serialize without losing unknown server metadata;
- save retains values on error and refreshes authoritative values on success;
- wide mappings remain page-overflow-free at 390 px.

- [ ] **Step 2: Run the operations suite and verify failure**

Run: `node scripts/verify_sewing_workspace.mjs entries-consumption`

Expected: FAIL because both tabs are absent.

- [ ] **Step 3: Implement Entries and Consumption**

Use the shared confirmation/error flow. Keep filters local while tabs switch, show UOM/BOM context read-only, and edit only returned `quantity`/`Consumption Weight` fields.

- [ ] **Step 4: Run browser suite and build**

Run:

```bash
node scripts/verify_sewing_workspace.mjs entries-consumption
yarn --cwd frontend build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sewing.js frontend/src/departments/sewing scripts/verify_sewing_workspace.mjs
git commit -m "feat: add sewing entries and consumption"
```

### Task 7: Closed Work Order GRN tab

**Files:**
- Create: `frontend/src/departments/sewing/plan/SewingClosedWorkOrderGrn.vue`
- Create: `frontend/src/departments/sewing/components/ClosedWorkOrderGrnEditor.vue`
- Modify: `frontend/src/departments/sewing/SewingPlanWorkspace.vue`
- Modify: `frontend/src/api/sewing.js`
- Modify: `essdee_yrp/test_sewing_business_logic.py`
- Modify: `scripts/verify_sewing_workspace.mjs`

**Interfaces:**
- Consumes: `get_closed_sewing_work_orders`, `get_closed_work_order_grn_details`, `create_closed_work_order_grn`, current grouped-item form primitives, and Task 1 create/submit capabilities.
- Produces: a Supplier-scoped Work Order picker and one-step Create & Submit GRN editor carrying `naming_series`, posting/delivery/reference fields, and grouped authoritative quantities.

- [ ] **Step 1: Add failing backend and browser checks**

Cover:

- Work Order search never returns another Supplier or non-closed/unsubmitted Work Order;
- concurrent creates cannot consume the same pending quantity twice;
- browser-tampered item/rate/UOM/Lot values are discarded;
- UI displays required naming series, posting date/time, delivery date, supplier document number/date, vehicle, DC number, comments, received type, and quantities;
- action is unavailable without both create and submit permission;
- server validation errors preserve the entered form in the popup;
- success shows the GRN ID and resets/reloads Work Order eligibility.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_business_logic --test test_closed_work_order_grn_rejects_concurrent_duplicate
node scripts/verify_sewing_workspace.mjs closed-grn
```

Expected: backend concurrency fixture or frontend tab fails before implementation.

- [ ] **Step 3: Implement the Closed Work Order GRN UI**

Reuse grouped rows and field components, but call only the closed-WO service. Never route through the ordinary Work Order GRN defaults path. Lock submission against double click and trust the returned server document ID/status.

- [ ] **Step 4: Run Closed WO and build verification**

Run:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_business_logic
node scripts/verify_sewing_workspace.mjs closed-grn
yarn --cwd frontend build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sewing.js frontend/src/departments/sewing essdee_yrp/test_sewing_business_logic.py scripts/verify_sewing_workspace.mjs
git commit -m "feat: add sewing closed work order receipts"
```

### Task 8: Reports shell, Status Summary, DPR, and SCR

**Files:**
- Create: `frontend/src/departments/sewing/SewingReportsWorkspace.vue`
- Create: `frontend/src/departments/sewing/reports/SewingStatusSummary.vue`
- Create: `frontend/src/departments/sewing/reports/SewingDpr.vue`
- Create: `frontend/src/departments/sewing/reports/SewingScr.vue`
- Create: `frontend/src/departments/sewing/components/SewingReportMatrix.vue`
- Modify: `frontend/src/api/sewing.js`
- Modify: `scripts/verify_sewing_workspace.mjs`

**Interfaces:**
- Consumes: Task 3 report contracts, Task 4 context, shared `ReportShell`, dates, links, multiselects, table and copy/export utilities.
- Produces: five-tab lazy Reports shell; daily/range DPR mode; reusable dynamic report matrix with contained overflow.

- [ ] **Step 1: Add failing report-shell browser checks**

Assert:

- exactly five approved report tabs and no Strength/FI/Input Pending tab;
- only the active report endpoint is requested;
- Status Summary filters Lot, Item, Colour, Part, input dates and recomputes visible totals;
- daily DPR sends one date and range mode sends From/To with optional Work Station/Input Type;
- `pending_fi` displays blocking Lot/Colour/Part details rather than a blank report;
- SCR requires a Supplier-scoped Lot and filters returned colours;
- dynamic matrices remain contained and sticky headers remain visible at narrow widths.

- [ ] **Step 2: Run primary reports suite and verify failure**

Run: `node scripts/verify_sewing_workspace.mjs primary-reports`

Expected: FAIL because the Reports workspace is absent.

- [ ] **Step 3: Implement the Reports shell and three reports**

Use responsive desktop tabs/mobile Select, explicit Generate where inputs are required, local filter preservation, and server-returned header order. Do not calculate stage balances in Vue.

- [ ] **Step 4: Run browser suite and build**

Run:

```bash
node scripts/verify_sewing_workspace.mjs primary-reports
yarn --cwd frontend build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sewing.js frontend/src/departments/sewing scripts/verify_sewing_workspace.mjs
git commit -m "feat: add sewing status dpr and scr reports"
```

### Task 9: Monthly Summary and Item Summary reports

**Files:**
- Create: `frontend/src/departments/sewing/reports/SewingMonthlySummary.vue`
- Create: `frontend/src/departments/sewing/reports/SewingItemSummary.vue`
- Modify: `frontend/src/departments/sewing/SewingReportsWorkspace.vue`
- Modify: `frontend/src/api/sewing.js`
- Modify: `scripts/verify_sewing_workspace.mjs`

**Interfaces:**
- Consumes: `get_monthly_summary_data`, `get_item_summary_options`, `get_item_summary_data`, Task 8 shell/matrix, shared async multiselect/date/report primitives.
- Produces: date/Input Type/GRN-mode monthly pivot and Lot/Item-intersection item summary.

- [ ] **Step 1: Add failing summary-report browser checks**

Assert:

- Monthly Summary rejects From Date after To Date before request;
- non-GRN mode requires Input Type while GRN mode does not;
- returned `styles`, rows, and grand total render in server order;
- Item Summary options reload on Supplier change and clear invalid selections;
- no request runs until at least one Lot or Item is selected;
- combined Lot+Item filters are sent together and grouped result matrices render totals;
- errors preserve filters and retry only the active report.

- [ ] **Step 2: Run summary reports suite and verify failure**

Run: `node scripts/verify_sewing_workspace.mjs summary-reports`

Expected: FAIL because the two report components are absent.

- [ ] **Step 3: Implement Monthly and Item Summary**

Use the shared report shell/matrix, explicit Generate/Reset actions, query-safe arrays, and request-generation checks on Supplier/options changes.

- [ ] **Step 4: Run browser suite and build**

Run:

```bash
node scripts/verify_sewing_workspace.mjs summary-reports
yarn --cwd frontend build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sewing.js frontend/src/departments/sewing scripts/verify_sewing_workspace.mjs
git commit -m "feat: add sewing summary reports"
```

### Task 10: Reusable Attendance Strength Report

**Files:**
- Create: `frontend/src/components/reports/AttendanceStrengthReport.vue`
- Create: `frontend/src/departments/sewing/SewingAttendance.vue`
- Modify: `frontend/src/api/sewing.js`
- Modify: `essdee_yrp/sewing/strength.py`
- Modify: `essdee_yrp/sewing/test_strength.py`
- Modify: `scripts/verify_sewing_workspace.mjs`

**Interfaces:**
- Consumes: `get_worker_strength_report(report_date, from_time, to_time)`, shared `ReportShell`, Date/Time fields, error normalizer, and export utilities.
- Produces: route-independent `AttendanceStrengthReport` accepting no Supplier prop and emitting no Sewing-specific state.

- [ ] **Step 1: Add failing backend and browser checks**

Assert:

- missing date/from/to errors have clear titles/messages;
- connection timeout, authentication/request failure, invalid report payload, and invalid punch payload are distinguishable;
- UI exposes only Date, From Time, To Time, Generate, Reset, results, totals, and export;
- no Supplier, HR department, HR location, designation, or employee selector exists;
- one endpoint failure produces one popup and the page remains interactive;
- an empty valid report shows the shared empty state.

- [ ] **Step 2: Run Strength tests and verify failure**

Run:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.sewing.test_strength
node scripts/verify_sewing_workspace.mjs attendance
```

Expected: frontend suite fails; backend error-classification tests fail until normalized.

- [ ] **Step 3: Implement error normalization and reusable report UI**

Keep both external calls server-side with existing credentials/timeouts. Convert only known upstream failure classes into specific business errors, log diagnostics server-side, render dynamic returned columns safely, and export the current returned dataset.

- [ ] **Step 4: Run Strength suite and build**

Run:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.sewing.test_strength
node scripts/verify_sewing_workspace.mjs attendance
yarn --cwd frontend build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sewing.js frontend/src/components/reports/AttendanceStrengthReport.vue frontend/src/departments/sewing/SewingAttendance.vue essdee_yrp/sewing/strength.py essdee_yrp/sewing/test_strength.py scripts/verify_sewing_workspace.mjs
git commit -m "feat: add attendance strength report"
```

### Task 11: Integrated UX, regression, and release verification

**Files:**
- Modify: `frontend/src/styles/enterprise.css` only for shared tokens/utilities proven missing by the completed views
- Modify: `frontend/src/departments/sewing/**/*.vue` only for verified integration defects
- Modify: `scripts/verify_sewing_workspace.mjs`
- Modify: `docs/superpowers/plans/2026-10-08-sewing-workspace.md` to mark completed checkboxes during execution

**Interfaces:**
- Consumes: all prior tasks.
- Produces: one passing `all` browser suite, a production bundle, and recorded verification evidence.

- [ ] **Step 1: Extend the integrated browser suite**

Add an `all` flow that:

- selects a Sewing Unit and visits all three cards;
- exercises all ten Supplier-scoped tabs plus Attendance Report;
- verifies lazy fetching, refresh/back/direct URLs, error popup recovery, and filter preservation;
- runs 1600/1280/900/390 px geometry checks on launcher, shells, matrices, dialogs, and reports;
- edits an unsaved quantity, resizes, switches a non-destructive view state, and proves the value remains;
- confirms no excluded tab/control text appears.

- [ ] **Step 2: Run the complete backend regression set**

Run:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_web_workspace
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_reports
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_sewing_business_logic
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.sewing.test_strength
```

Expected: all PASS with no skips caused by code errors; migrated-data skips, if any, are explicitly reported.

- [ ] **Step 3: Run complete frontend verification**

Run:

```bash
node scripts/verify_sewing_workspace.mjs all
yarn --cwd frontend build
node scripts/verify_premium_ui_polish.mjs
node scripts/audit_web_ui_contract.mjs
```

Expected: all commands exit 0; no page-level overflow or raw error presentation.

- [ ] **Step 4: Inspect the built routes manually**

Verify representative real data at:

- `/web/sewing`
- `/web/sewing/plans?supplier=<known-unit>`
- `/web/sewing/reports?supplier=<known-unit>`
- `/web/sewing/attendance`

Check permissions with one restricted user, a stale/concurrent Data Entry rejection, a Closed WO GRN eligible record, and HR unavailable behavior. Capture screenshots only as test evidence; do not modify unrelated design-reference files.

- [ ] **Step 5: Request final code review and address findings**

Use the requesting-code-review workflow against the design, this plan, and the complete branch diff. Re-run the smallest affected suite after each fix, then repeat Steps 2–3.

- [ ] **Step 6: Commit final integration fixes**

```bash
git add frontend/src essdee_yrp/sewing essdee_yrp/test_sewing_*.py scripts/verify_sewing_workspace.mjs docs/superpowers/plans/2026-10-08-sewing-workspace.md
git commit -m "feat: complete sewing web workspace"
```
