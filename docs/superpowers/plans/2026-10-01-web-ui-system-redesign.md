# Essdee YRP Web UI System Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the shared `/web` foundation and complete Cutting workspace into one polished, compact enterprise ERP interface without changing business behavior.

**Architecture:** Retain Vue 3, PrimeVue Aura, the current routes, and all existing component behavior. Establish semantic design tokens and shared ERP presentation primitives first, then migrate each active page family in dependency order while a Playwright contract verifier protects layout, readability, permissions, and interaction behavior.

**Tech Stack:** Vue 3.5, Vue Router 4.5, PrimeVue 4.3 with Aura, PrimeIcons 7, Vite 5.4, native CSS, Playwright from the existing local installation.

**Spec:** `docs/superpowers/specs/2026-10-01-web-ui-system-redesign-design.md`

## Global Constraints

- Preserve every existing route, field name, data value, permission gate, report calculation, print action, API contract, and document transition.
- Keep PrimeVue Aura as the only component system; add no runtime UI, font, or animation dependency.
- Use one light theme, one cool-neutral palette, and one emerald accent across every active route.
- Use `Segoe UI Variable`, `Segoe UI`, and system UI fallbacks; do not depend on a remote font.
- Do not render visible operational text below 11px.
- Use an 8px radius for controls, 12px for panels and dialogs, and pill radius only for statuses and counts.
- Retain the Cutting Plan 80/20 desktop split, fixed tab bar, independent content scrolling, and 50/50 sidebar sections.
- Preserve the one-second filter debounce and field-aware Frappe filter behavior.
- Do not add decorative animations, glassmorphism, gradients, redundant explanatory copy, screenshots, or screenshot generation.
- Commit only the exact frontend, verification, and plan files named by each task; leave all pre-existing backend changes untouched.

## Review Focus

- **Permission-restricted users:** hidden actions or panels must not leave empty gaps, and permitted read-only content must remain usable. Covered by Tasks 2, 4, 5, 6, and 7.
- **Long manufacturing IDs and labels:** IDs, item names, lots, marker names, and panel lists must truncate or wrap without breaking grids. Covered by Tasks 3, 4, 5, and 8.
- **Short and narrow viewports:** sticky headers, tab bars, dialog footers, and the 80/20 split must not overlap content or trap scrolling. Covered by Tasks 4, 5, 7, and 9.
- **Loading, empty, and error states:** every page family must remain intentional and readable outside the successful populated state. Covered by Tasks 2, 3, 4, 5, 6, 7, and 8.
- **Dense and wide data:** tables and matrices must keep numeric alignment and horizontal containment without shrinking visible text below 11px. Covered by Tasks 3, 6, 7, 8, and 9.

---

### Task 1: Establish the design-token contract and non-visual verifier

**Files:**
- Create: `scripts/verify_web_ui_redesign.mjs`
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `frontend/src/styles/main.css`

**Interfaces:**
- Produces: CLI `node scripts/verify_web_ui_redesign.mjs <suite>` with suites added incrementally through this plan.
- Produces: helper functions `assert(condition, message)`, `login(page)`, `findCuttingPlan(request, predicate)`, `assertNoBrowserErrors(errors)`, and `visibleTextBelowMinimum(page, minPx = 11)`.
- Produces: semantic CSS variables for font, color, spacing, radii, control heights, shadows, transitions, and layer order under `.app-shell`.

- [ ] **Step 1: Write the failing `tokens` suite**

Add assertions that source and computed styles expose these exact contracts:

```js
assert(css.includes("--erp-font-family"), "font token is missing")
assert(css.includes("--erp-control-radius: 8px"), "control radius is not locked")
assert(css.includes("--erp-panel-radius: 12px"), "panel radius is not locked")
assert(css.includes("--erp-accent: #0a7f5a"), "emerald accent is not locked")
assert(css.includes("--erp-font-size-min: 11px"), "minimum text size is not locked")
```

- [ ] **Step 2: Run the token suite and verify it fails**

Run: `node scripts/verify_web_ui_redesign.mjs tokens`  
Expected: FAIL because the new semantic tokens do not exist.

- [ ] **Step 3: Implement the semantic foundation**

In `enterprise.css`, define exact token families:

- Typography: `--erp-font-family`, `--erp-font-size-min`, `--erp-font-size-caption`, `--erp-font-size-body`, `--erp-font-size-title`, and line-height tokens.
- Color: canvas `#f4f7f5`, surface `#ffffff`, soft surface `#f7faf8`, muted surface `#eef3f0`, text `#182a22`, muted text `#5f6f67`, border `#d8e2dd`, strong border `#c5d2cc`, accent `#0a7f5a`, and accent hover `#076b4b`.
- Shape: control 8px, panel 12px, pill 999px.
- Sizing: compact control 32px and default control 36px.
- Layers: content 1, sticky 20, overlay 100, dialog 200, toast 300.

In `main.css`, replace the radial canvas background, remove the Inter-first stack, establish the stable page canvas, and apply reduced-motion behavior.

- [ ] **Step 4: Run the token suite and production build**

Run: `node scripts/verify_web_ui_redesign.mjs tokens && npm run build --prefix frontend`  
Expected: token suite PASS and Vite build succeeds.

- [ ] **Step 5: Commit the foundation**

```bash
git commit --only -m "style(frontend): establish enterprise design tokens" -- \
  frontend/src/styles/enterprise.css frontend/src/styles/main.css \
  scripts/verify_web_ui_redesign.mjs
```

### Task 2: Redesign the shared shell and workspace entry pages

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/AdministratorPage.vue`
- Modify: `frontend/src/components/DepartmentCard.vue`
- Modify: `frontend/src/components/DepartmentPage.vue`
- Modify: `frontend/src/departments/Cutting.vue`
- Modify: `frontend/src/styles/main.css`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Consumes: Task 1 token names and verifier helpers.
- Produces: shared `.erp-page-shell`, `.erp-page-nav`, `.erp-page-surface`, and `.erp-workspace-entry` presentation contracts.
- Produces: verifier suites `shell` and `cutting-entry`.

- [ ] **Step 1: Add failing shell assertions**

The `shell` suite must assert that the administrator page has ten department destinations, no `Open workspace` filler text, a stable neutral canvas, visible focus styles, and no visible text below 11px. The `cutting-entry` suite must assert exactly two permitted destination cards, no `Manufacturing workspace`, and no long introductory paragraph.

- [ ] **Step 2: Run the shell suites and verify they fail**

Run: `node scripts/verify_web_ui_redesign.mjs shell && node scripts/verify_web_ui_redesign.mjs cutting-entry`  
Expected: FAIL on filler copy and old layout/style assertions.

- [ ] **Step 3: Implement the shared shell**

Refactor the page wrapper and department cards to use the Task 1 tokens. Keep department identity colors limited to small icon marks. Remove redundant subtitles, decorative eyebrow copy, the Cutting landing description, and card-category labels while preserving accessible names and permission conditions.

- [ ] **Step 4: Verify populated, empty-permission, and narrow layouts**

Extend the suites to assert that the no-permission state occupies the workspace cleanly, 760px layouts use one column, and long department names do not overflow.

- [ ] **Step 5: Run verification and build**

Run: `node scripts/verify_web_ui_redesign.mjs shell && node scripts/verify_web_ui_redesign.mjs cutting-entry && npm run build --prefix frontend`  
Expected: all PASS.

- [ ] **Step 6: Commit the shell**

```bash
git commit --only -m "style(frontend): refine web workspace shell" -- \
  frontend/src/App.vue frontend/src/components/AdministratorPage.vue \
  frontend/src/components/DepartmentCard.vue frontend/src/components/DepartmentPage.vue \
  frontend/src/departments/Cutting.vue frontend/src/styles/main.css \
  scripts/verify_web_ui_redesign.mjs
```

### Task 3: Standardize shared controls, forms, filters, and list views

**Files:**
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `frontend/src/components/common/FormField.vue`
- Modify: `frontend/src/components/common/LinkField.vue`
- Modify: `frontend/src/components/common/MultiSelectField.vue`
- Modify: `frontend/src/components/common/FormView.vue`
- Modify: `frontend/src/components/common/ListView.vue`
- Modify: `frontend/src/components/common/ListviewFilters.vue`
- Modify: `frontend/src/components/common/ListviewQuickFilters.vue`
- Modify: `frontend/src/components/common/UserListviewColumns.vue`
- Modify: `frontend/src/departments/CuttingPlans.vue`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Consumes: Task 1 typography, control, state, and table tokens.
- Produces: shared PrimeVue normalization for buttons, inputs, select controls, autocomplete, tabs, dialog chrome, messages, tags, skeletons, and paginator controls.
- Produces: verifier suite `list` while preserving `scripts/verify_list_filter_component.mjs` behavior.

- [ ] **Step 1: Add failing list and control assertions**

Assert one compact command row, no header record-count prose, no `Quick filters` explanation, 36px default controls, sticky table headers, numeric alignment, visible filter focus, drag handles in the column dialog, and zero visible text below 11px.

- [ ] **Step 2: Run the new and existing filter suites**

Run: `node scripts/verify_web_ui_redesign.mjs list`  
Expected: FAIL on current typography and layout contract.

Run: `node scripts/verify_list_filter_component.mjs`  
Expected: PASS before visual refactoring; save its JSON output as the behavior baseline.

- [ ] **Step 3: Implement common control and state styling**

Move repeated control, table, status, empty-state, and dialog rules into `enterprise.css`. Keep component-specific grid and overflow rules scoped. Do not change filter payloads, debounce timers, link queries, operators, selection state, column persistence, or row navigation.

- [ ] **Step 4: Refine the Cutting Plans list composition**

Align title, search, Filters, Columns, Refresh, and Clear Filters in the same command area. Preserve bulk actions when rows are selected. Keep applied-filter chips compact and removable.

- [ ] **Step 5: Test long values, empty results, loading, and horizontal containment**

The `list` suite must assert truncation or wrapping of long values, an intentional empty result, skeleton geometry during load, and a table scroll container at 900px viewport width.

- [ ] **Step 6: Run behavior and visual verification**

Run: `node scripts/verify_list_filter_component.mjs && node scripts/verify_web_ui_redesign.mjs list && npm run build --prefix frontend`  
Expected: all PASS with unchanged filter payload assertions.

- [ ] **Step 7: Commit shared forms and lists**

```bash
git commit --only -m "style(frontend): unify forms filters and list views" -- \
  frontend/src/styles/enterprise.css frontend/src/components/common/FormField.vue \
  frontend/src/components/common/LinkField.vue frontend/src/components/common/MultiSelectField.vue \
  frontend/src/components/common/FormView.vue frontend/src/components/common/ListView.vue \
  frontend/src/components/common/ListviewFilters.vue frontend/src/components/common/ListviewQuickFilters.vue \
  frontend/src/components/common/UserListviewColumns.vue frontend/src/departments/CuttingPlans.vue \
  scripts/verify_web_ui_redesign.mjs
```

### Task 4: Refine the Cutting Plan frame, action bar, and primary tabs

**Files:**
- Modify: `frontend/src/departments/CuttingPlan.vue`
- Modify: `frontend/src/departments/cutting/CuttingPlanActions.vue`
- Modify: `frontend/src/departments/cutting/CuttingPlanTabs.vue`
- Modify: `frontend/src/components/common/FormView.vue`
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Consumes: Task 3 form, table, status, command bar, and scroll-region contracts.
- Produces: fixed `.cutting-plan-frame` with an 80/20 grid, fixed header/actions/tabs, and one scrollable active content region.
- Produces: verifier suites `plan-frame` and `plan-primary-tabs`.

- [ ] **Step 1: Add failing frame assertions**

At 1600x1000, assert main/sidebar width ratio between 3.7 and 4.3, status beside the record ID, Edit separate from process commands, five visible tabs, tab-list position unchanged while active content scrolls, and no page-level horizontal overflow.

- [ ] **Step 2: Add failing primary-tab assertions**

Assert Details uses two balanced columns in Desk order, Summary contains completed/excess/recut/print sections, Planned Detail distinguishes Planned and Completed rows, totals use tabular numbers, and long IDs remain contained.

- [ ] **Step 3: Run the plan suites and verify they fail**

Run: `node scripts/verify_web_ui_redesign.mjs plan-frame && node scripts/verify_web_ui_redesign.mjs plan-primary-tabs`  
Expected: FAIL on the new frame and typography contracts.

- [ ] **Step 4: Implement frame and action hierarchy**

Keep current action visibility logic and API calls. Restyle the identity group, status, print action, Edit control, and plan process commands. Allow lower-priority commands to wrap or use the existing compact overflow behavior only when width requires it.

- [ ] **Step 5: Implement Details, Summary, and Planned Detail presentation**

Use borders, section spacing, light surface tint, and table hierarchy instead of nested elevation. Keep every existing field, value, table, and slot.

- [ ] **Step 6: Verify loading, API error, read-only permission, and 1050px collapse**

Add assertions that read-only mode hides Edit without leaving a gap, loading and error messages remain visible, and the sidebar moves below the main surface when the desktop split collapses.

- [ ] **Step 7: Run verification and build**

Run: `node scripts/verify_web_ui_redesign.mjs plan-frame && node scripts/verify_web_ui_redesign.mjs plan-primary-tabs && npm run build --prefix frontend`  
Expected: all PASS.

- [ ] **Step 8: Commit the Cutting Plan core**

```bash
git commit --only -m "style(cutting): refine plan workspace and primary tabs" -- \
  frontend/src/departments/CuttingPlan.vue frontend/src/departments/cutting/CuttingPlanActions.vue \
  frontend/src/departments/cutting/CuttingPlanTabs.vue frontend/src/components/common/FormView.vue \
  frontend/src/styles/enterprise.css scripts/verify_web_ui_redesign.mjs
```

### Task 5: Redesign the marker and Lay Sheet rail and dialogs

**Files:**
- Modify: `frontend/src/departments/cutting/CuttingPlanSidebar.vue`
- Modify: `frontend/src/departments/cutting/CuttingMarkerDialog.vue`
- Modify: `frontend/src/departments/cutting/CuttingLaySheetDialog.vue`
- Modify: `frontend/src/departments/cutting/DocumentPrintButton.vue`
- Modify: `frontend/src/components/common/ChildTableField.vue`
- Modify: `frontend/src/components/common/DocumentSidePanel.vue`
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Consumes: Task 3 dialog, field, status, and table contracts; Task 4 fixed workspace frame.
- Produces: equal-height `.marker-section` and `.laysheet-section` regions with fixed headers and independent scrolling.
- Produces: verifier suites `sidebar` and `entity-dialogs`.

- [ ] **Step 1: Add failing sidebar assertions**

Assert each permitted section receives half the available rail height, each has Create New and filter actions only when permitted, marker cards expose name/ID/dimensions/weight/panels/status, Lay Sheet cards expose lay number/marker/panels/date/time/print/status, and displayed dates use `DD-MM-YYYY`.

- [ ] **Step 2: Add failing dialog assertions**

Assert modal opening does not navigate, outside click closes a clean dialog, start/end date-time fields are absent from Lay Sheet creation, child-table Add buttons appear when permitted, footer actions stay visible while the body scrolls, and delete success removes the row from the rendered table.

- [ ] **Step 3: Run sidebar and dialog suites and verify they fail**

Run: `node scripts/verify_web_ui_redesign.mjs sidebar && node scripts/verify_web_ui_redesign.mjs entity-dialogs`  
Expected: FAIL on sizing, typography, and shared dialog contract.

- [ ] **Step 4: Implement the rail visual hierarchy**

Increase operational text to at least 11px, simplify card borders, keep panel/status chips semantic, constrain long names, and preserve newest-first ordering and filters.

- [ ] **Step 5: Implement the shared marker and Lay Sheet dialog hierarchy**

Keep every current field and action. Apply a fixed header, scrollable content body, sticky footer, consistent context strips, compact tables, and permission-aware action styling.

- [ ] **Step 6: Verify permission, empty, filtered-empty, long-name, and narrow-height states**

Extend the suites so one missing read permission removes only that rail section, zero results show a deliberate state, active filters remain visible, long names do not expand the rail, and 700px viewport height retains both section headers.

- [ ] **Step 7: Run verification and build**

Run: `node scripts/verify_web_ui_redesign.mjs sidebar && node scripts/verify_web_ui_redesign.mjs entity-dialogs && npm run build --prefix frontend`  
Expected: all PASS.

- [ ] **Step 8: Commit the sidebar and entity dialogs**

```bash
git commit --only -m "style(cutting): refine marker and lay sheet workflows" -- \
  frontend/src/departments/cutting/CuttingPlanSidebar.vue \
  frontend/src/departments/cutting/CuttingMarkerDialog.vue \
  frontend/src/departments/cutting/CuttingLaySheetDialog.vue \
  frontend/src/departments/cutting/DocumentPrintButton.vue \
  frontend/src/components/common/ChildTableField.vue \
  frontend/src/components/common/DocumentSidePanel.vue \
  frontend/src/styles/enterprise.css scripts/verify_web_ui_redesign.mjs
```

### Task 6: Refine CPM movement selection and transaction presentation

**Files:**
- Modify: `frontend/src/departments/cutting/CuttingPlanCpm.vue`
- Modify: `frontend/src/departments/cutting/CpmMovementDialog.vue`
- Modify: `frontend/src/departments/cutting/CpmMovementTransactionDialog.vue`
- Modify: `frontend/src/departments/cutting/CpmTransactionDialog.vue`
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Consumes: Task 3 table/dialog contracts and Task 4 fixed tabs.
- Produces: verifier suite `cpm`.

- [ ] **Step 1: Add failing CPM assertions**

Assert the tab contains only its functional heading and controls, movement cards expose identity/status/date/time/quantities without origin filler copy, newest records appear first, and Create Movement opens the existing dialog.

- [ ] **Step 2: Add failing matrix assertions**

Assert bundle selection retains production-style grouping, row and panel selection remain independent, totals update after selection, collapsed and accessory sections remain available, and wide matrices scroll without shrinking text.

- [ ] **Step 3: Run the CPM suite and verify it fails**

Run: `node scripts/verify_web_ui_redesign.mjs cpm`  
Expected: FAIL on the new presentation contract while current selection behavior remains intact.

- [ ] **Step 4: Implement CPM cards, context strips, matrices, and footers**

Remove redundant labels, normalize time/status hierarchy, use shared selection and table states, and preserve Generate, Save Draft, Save & Submit, reopen, Submit, Cancel, print, and permission logic.

- [ ] **Step 5: Verify no-data, generated, selected, submitted, cancelled, and read-only states**

Extend the suite to cover each state and assert no browser console errors.

- [ ] **Step 6: Run verification and build**

Run: `node scripts/verify_web_ui_redesign.mjs cpm && npm run build --prefix frontend`  
Expected: all PASS.

- [ ] **Step 7: Commit CPM presentation**

```bash
git commit --only -m "style(cutting): refine cut panel movement workspace" -- \
  frontend/src/departments/cutting/CuttingPlanCpm.vue \
  frontend/src/departments/cutting/CpmMovementDialog.vue \
  frontend/src/departments/cutting/CpmMovementTransactionDialog.vue \
  frontend/src/departments/cutting/CpmTransactionDialog.vue \
  frontend/src/styles/enterprise.css scripts/verify_web_ui_redesign.mjs
```

### Task 7: Refine Stock Transfers and item-entry matrices

**Files:**
- Modify: `frontend/src/departments/cutting/CuttingPlanStockTransfers.vue`
- Modify: `frontend/src/departments/cutting/CpmStockOperationDialog.vue`
- Modify: `frontend/src/departments/cutting/StockItemComposer.vue`
- Modify: `frontend/src/departments/cutting/StockItemMatrix.vue`
- Modify: `frontend/src/departments/cutting/StockSelectionMatrix.vue`
- Modify: `frontend/src/departments/cutting/WorkOrderDeliveryDialog.vue`
- Modify: `frontend/src/departments/cutting/WorkOrderDeliveryMatrix.vue`
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Consumes: Task 3 form/table/dialog contracts and Task 4 fixed tabs.
- Produces: verifier suite `stock-transfers`.

- [ ] **Step 1: Add failing Stock Transfers workspace assertions**

Assert the five operation cards are the only operation selector, selecting one reveals its list directly without a duplicate heading, Create actions remain permission-aware, and transaction cards expose identity/status/date without repeated instructional copy.

- [ ] **Step 2: Add failing item composer and matrix assertions**

Assert Purpose is a Select for Stock Entry, Update Type supports Add and Reduce, Item precedes Get Item, attributes and primary values render in separate columns, staged items remain readable, zero-quantity reconciliation remains valid, and long variant names stay contained.

- [ ] **Step 3: Run the Stock Transfers suite and verify it fails**

Run: `node scripts/verify_web_ui_redesign.mjs stock-transfers`  
Expected: FAIL on the new hierarchy and minimum typography contracts.

- [ ] **Step 4: Implement operation cards, lists, composers, matrices, and dialogs**

Consolidate repeated local styling into shared patterns. Preserve all existing stock payloads, derived warehouses, lot ownership, selection logic, Work Order delivery behavior, save/submit/cancel transitions, and print formats.

- [ ] **Step 5: Verify each operation and short-height dialog behavior**

Open Stock Entry, Stock Update, Stock Reconciliation, Lot Transfer, and Delivery Challan. Assert the correct input structure, sticky footer, independent body scroll, permission-driven buttons, and no console errors.

- [ ] **Step 6: Run verification and build**

Run: `node scripts/verify_web_ui_redesign.mjs stock-transfers && npm run build --prefix frontend`  
Expected: all PASS.

- [ ] **Step 7: Commit Stock Transfers presentation**

```bash
git commit --only -m "style(cutting): refine stock transfer workflows" -- \
  frontend/src/departments/cutting/CuttingPlanStockTransfers.vue \
  frontend/src/departments/cutting/CpmStockOperationDialog.vue \
  frontend/src/departments/cutting/StockItemComposer.vue \
  frontend/src/departments/cutting/StockItemMatrix.vue \
  frontend/src/departments/cutting/StockSelectionMatrix.vue \
  frontend/src/departments/cutting/WorkOrderDeliveryDialog.vue \
  frontend/src/departments/cutting/WorkOrderDeliveryMatrix.vue \
  frontend/src/styles/enterprise.css scripts/verify_web_ui_redesign.mjs
```

### Task 8: Redesign all Cutting report surfaces

**Files:**
- Modify: `frontend/src/departments/CuttingReports.vue`
- Modify: `frontend/src/departments/cutting/reports/ReportShell.vue`
- Modify: `frontend/src/departments/cutting/reports/DailyProductionReport.vue`
- Modify: `frontend/src/departments/cutting/reports/DailyCutSheetReport.vue`
- Modify: `frontend/src/departments/cutting/reports/MultiCCRReport.vue`
- Modify: `frontend/src/departments/cutting/reports/CuttingDetailReport.vue`
- Modify: `frontend/src/departments/cutting/reports/StockBalanceReport.vue`
- Modify: `frontend/src/departments/cutting/reports/ProductionMatrix.vue`
- Modify: `frontend/src/departments/cutting/reports/CompletionMatrix.vue`
- Modify: `frontend/src/departments/cutting/reports/ClothTable.vue`
- Modify: `frontend/src/departments/cutting/reports/AsyncLinkMultiSelect.vue`
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Consumes: Task 3 fields, tabs, tables, summaries, and empty-state contracts.
- Produces: verifier suite `reports`.

- [ ] **Step 1: Add failing report-shell assertions**

Assert exactly five permitted tabs, a fixed tab bar, no duplicate inner report title, no `Manufacturing intelligence` copy, compact filters, explicit Generate, no automatic API request on tab activation, and zero visible text below 11px.

- [ ] **Step 2: Add failing result assertions**

For each report, assert intentional initial and empty states, a compact result-summary strip, sticky table headers, numeric alignment, total-row emphasis, horizontal containment, `DD-MM-YYYY` display dates, and long style/lot names contained. Assert Copy Report remains present only where currently supported.

- [ ] **Step 3: Run the reports suite and verify it fails**

Run: `node scripts/verify_web_ui_redesign.mjs reports`  
Expected: FAIL on typography and shared report presentation.

- [ ] **Step 4: Implement the shared report shell and five report layouts**

Use one filter bar, summary strip, table system, empty state, and scroll contract. Preserve every current filter, result value, grouping, panel rule, copy action, and server request.

- [ ] **Step 5: Verify manual generation and all result modes**

Visit every report tab, assert zero report requests before Generate, generate with valid fixture filters, and assert populated results plus no browser errors.

- [ ] **Step 6: Run verification and build**

Run: `node scripts/verify_web_ui_redesign.mjs reports && npm run build --prefix frontend`  
Expected: all PASS.

- [ ] **Step 7: Commit reports presentation**

```bash
git commit --only -m "style(cutting): unify production reports" -- \
  frontend/src/departments/CuttingReports.vue frontend/src/departments/cutting/reports \
  frontend/src/styles/enterprise.css scripts/verify_web_ui_redesign.mjs
```

### Task 9: Complete responsive, accessibility, performance, and regression verification

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/styles/enterprise.css`
- Modify: `frontend/src/styles/main.css`
- Modify: `scripts/verify_web_ui_redesign.mjs`
- Modify only if a verified defect requires it: files changed in Tasks 2-8

**Interfaces:**
- Consumes: every previous verifier suite and presentation contract.
- Produces: verifier suite `all` and lazy route components for Cutting Plan and Reports.

- [ ] **Step 1: Add failing accessibility and viewport audit assertions**

The `all` suite must visit every active route at 1600x1000, 1280x800, 900x760, and 390x844 and assert:

```js
assert(await page.locator("body").evaluate((el) => el.scrollWidth === el.clientWidth), "page overflow")
assert((await visibleTextBelowMinimum(page, 11)).length === 0, "text below 11px")
await page.keyboard.press("Tab")
assert(await page.evaluate(() => {
	const active = document.activeElement
	if (!active || active === document.body) return false
	const style = getComputedStyle(active)
	return style.outlineStyle !== "none" || style.boxShadow !== "none"
}), "keyboard focus is not visibly indicated")
assert(errors.length === 0, "browser errors detected")
```

Also assert sticky elements do not overlap their scroll regions, dialog actions remain reachable at 700px height, and status meaning is present as text.

- [ ] **Step 2: Run the all-suite and record failures**

Run: `node scripts/verify_web_ui_redesign.mjs all`  
Expected: FAIL until remaining responsive and accessibility defects are corrected.

- [ ] **Step 3: Add route-level lazy loading**

Convert static imports in `router/index.js` to dynamic imports for `CuttingPlan`, `CuttingReports`, and other route-level department components. Preserve route names, paths, redirect behavior, and `/web/` history base.

- [ ] **Step 4: Fix only failures demonstrated by the all-suite**

Use the shared tokens and component-local layout rules. Do not introduce new visual patterns during this pass.

- [ ] **Step 5: Run every focused verifier**

Run:

```bash
node scripts/verify_list_filter_component.mjs
node scripts/verify_web_ui_redesign.mjs tokens
node scripts/verify_web_ui_redesign.mjs shell
node scripts/verify_web_ui_redesign.mjs cutting-entry
node scripts/verify_web_ui_redesign.mjs list
node scripts/verify_web_ui_redesign.mjs plan-frame
node scripts/verify_web_ui_redesign.mjs plan-primary-tabs
node scripts/verify_web_ui_redesign.mjs sidebar
node scripts/verify_web_ui_redesign.mjs entity-dialogs
node scripts/verify_web_ui_redesign.mjs cpm
node scripts/verify_web_ui_redesign.mjs stock-transfers
node scripts/verify_web_ui_redesign.mjs reports
node scripts/verify_web_ui_redesign.mjs all
```

Expected: every command exits 0 and reports zero browser errors.

- [ ] **Step 6: Run the production build twice**

Run: `npm run build --prefix frontend && npm run build --prefix frontend`  
Expected: both builds succeed; compare emitted chunk sizes with the 1.33 MB baseline and confirm route splitting reduces the main entry chunk.

- [ ] **Step 7: Inspect the final diff against the UI checkpoint**

Run: `git diff --check 90b0b48 -- frontend scripts/verify_web_ui_redesign.mjs`  
Expected: no whitespace errors. Review the diff to confirm no API payload, permission, route path, or business-value changes.

- [ ] **Step 8: Commit final responsive and performance work**

```bash
git commit --only -m "perf(frontend): finish responsive web UI redesign" -- \
  frontend/src \
  scripts/verify_web_ui_redesign.mjs
```

- [ ] **Step 9: Request final code review**

Use `superpowers:requesting-code-review` against commits after `90b0b48`, then address only verified High or Medium findings and rerun the affected suites plus the production build.
