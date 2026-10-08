# Web Navigation and Related Lists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace wasteful standalone back rows with inline navigation, add safe filter-aware Previous/Next movement, and provide server-paginated expanded related lists for Cutting and Work Order records.

**Architecture:** `DepartmentPage` opts selected pages into a provided inline-navigation context. `ListView` persists the exact applied query state, while a shared document navigation component validates adjacent records through deterministic server queries before routing. A reusable `RelatedRecordsDialog` embeds the server-backed `ListView` for Marker, Lay Sheet, Work Order DC, and Work Order GRN expansion.

**Tech Stack:** Vue 3 Composition API, Vue Router 4, PrimeVue, Frappe REST list API, Node/Playwright verification scripts.

**Spec:** `docs/superpowers/specs/2026-10-08-web-navigation-related-lists-design.md`

## Global Constraints

- Do not redesign or alter creation/editor UI.
- Do not modify Sewing source or behavior.
- Do not modify any Cutting LaySheet Planner source file or behavior.
- Purchase Order related GRNs do not receive an expanded list.
- Existing document permissions, actions, validation, and related-record dialogs remain authoritative.
- Every behavior change starts with a failing automated test.
- Preserve unrelated and pre-existing working-tree changes.
- Final screenshots must be sent to Telegram topic `yrp_po` after verification.

## Review Focus

- A record modified after leaving the list must produce `List changed`, never a guessed neighbor; Task 4 tests this.
- Mobile and desktop row activation must capture identical applied—not merely typed—filters; Task 2 tests both paths.
- Embedded DC/GRN dialogs must never show page navigation; Task 4 tests embedded and full-page presentations.
- Expanded related lists must query beyond the 500-row parent payload cap with exact parent filters; Tasks 5–7 test pagination and filters.
- Inline navigation must not leak into creation, Sewing, or LaySheet Planner; Tasks 3 and 8 verify source and browser boundaries.

---

### Task 1: Deterministic List Navigation State

**Files:**
- Create: `frontend/src/utils/listNavigation.js`
- Create: `scripts/test_list_navigation.mjs`

**Interfaces:**
- Produces: `deterministicOrder(sortField, sortOrder) -> string`
- Produces: `createListNavigationState(input) -> object`
- Produces: `navigationStorageKey(sourceRouteName, doctype) -> string`
- Produces: `writeNavigationState(storage, state) -> string`
- Produces: `readNavigationState(storage, key) -> object|null`
- Produces: `createNavigationReference(state, index, currentName) -> object`
- Produces: `resolveAdjacentNames({ state, reference, rows }) -> { previousName, nextName, changed, reason }`

- [ ] **Step 1: Write failing utility tests**

Cover deterministic secondary-name sorting, versioned storage round trips, invalid/corrupt storage fallback, start/middle/end adjacent windows, and a missing/moved current record returning `changed: true`.

- [ ] **Step 2: Verify the tests fail because the module does not exist**

Run: `node scripts/test_list_navigation.mjs`

Expected: FAIL resolving `frontend/src/utils/listNavigation.js`.

- [ ] **Step 3: Implement the pure state utilities**

Keep browser globals out of the pure functions. Accept a Storage-compatible object for persistence so tests use a real in-memory implementation without mocking production behavior.

- [ ] **Step 4: Verify the utility tests pass**

Run: `node scripts/test_list_navigation.mjs`

Expected: `List navigation state verified.`

- [ ] **Step 5: Commit the isolated utility and test**

Commit message: `feat: add deterministic list navigation state`

### Task 2: Capture and Restore Applied List State

**Files:**
- Modify: `frontend/src/components/common/ListView.vue`
- Create: `frontend/src/router/listDocumentNavigation.js`
- Modify: `frontend/src/departments/CuttingPlans.vue`
- Modify: `frontend/src/departments/CuttingOrders.vue`
- Modify: `frontend/src/departments/CuttingBulkLaySheets.vue`
- Modify: `frontend/src/departments/fabric-store/FabricWorkOrders.vue`
- Modify: `frontend/src/departments/fabric-store/FabricPurchaseOrders.vue`
- Modify: `scripts/verify_web_ui_redesign.mjs`
- Modify: `scripts/verify_fabric_store_workspace.mjs`
- Modify: `scripts/verify_cutting_bulk_laysheets_workspace.mjs`

**Interfaces:**
- `ListView` emits `row-click(row, navigationSnapshot)` on desktop and mobile.
- `ListView` accepts `navigation-enabled`, defaulting to `true`.
- `openListDocument(router, row, snapshot, { routeName, paramName })` persists the full snapshot and pushes a small history-state reference.
- `ListView` restores its saved applied query when mounted on the recorded source route.

- [ ] **Step 1: Add failing browser assertions for applied state**

Assert desktop and mobile activation capture normalized base filters, applied advanced/quick/status/search filters, deterministic order, page offset/size, global index, total, and source route. Type—but do not apply—a search/filter and assert it is absent from the snapshot. Navigate back and assert the applied controls and page are restored.

- [ ] **Step 2: Run focused suites and verify the new assertions fail**

Run:

```bash
node scripts/verify_web_ui_redesign.mjs list-navigation
node scripts/verify_fabric_store_workspace.mjs list-navigation
```

Expected: FAIL because row-click has no navigation snapshot and list state is not restored.

- [ ] **Step 3: Extend `ListView` with state capture/restore**

Use `allFilters()`, `appliedSearch`, and `appliedQuickFilters`. Compute mobile row indices with `rows.indexOf(row)`. Save state only for navigation-enabled lists. Add `name` as the deterministic secondary sort to the actual server query and emitted snapshot.

- [ ] **Step 4: Add the shared route helper and migrate routed list pages**

Use route names and parameter names:

- `cutting-plan` / `cuttingPlanId`
- `cutting-order` / `cuttingOrderId`
- `cutting-bulk-lay-sheet` / `bulkLaySheetsId`
- configured Work Order route / `workOrderId`
- configured Purchase Order route / `purchaseOrderId`

- [ ] **Step 5: Re-run focused suites**

Expected: PASS with identical desktop/mobile snapshots and restored list UI.

- [ ] **Step 6: Commit list-state integration**

Commit message: `feat: preserve filtered list navigation context`

### Task 3: Inline Back Navigation Across Non-Creation Pages

**Files:**
- Create: `frontend/src/components/navigation/pageNavigationContext.js`
- Create: `frontend/src/components/navigation/InlinePageNavigation.vue`
- Modify: `frontend/src/components/DepartmentPage.vue`
- Modify: `frontend/src/components/common/WorkspaceLauncher.vue`
- Modify: `frontend/src/components/common/ListView.vue`
- Modify: `frontend/src/components/reports/ReportShell.vue`
- Modify: `frontend/src/components/common/FormView.vue`
- Modify: `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- Modify: `frontend/src/departments/Cutting.vue`
- Modify: `frontend/src/departments/FabricStore.vue`
- Modify: `frontend/src/departments/CutPanelStore.vue`
- Modify: `frontend/src/departments/CuttingPlans.vue`
- Modify: `frontend/src/departments/CuttingOrders.vue`
- Modify: `frontend/src/departments/CuttingBulkLaySheets.vue`
- Modify: `frontend/src/departments/CuttingReports.vue`
- Modify: `frontend/src/departments/FabricStoreSection.vue`
- Modify: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `frontend/src/departments/CuttingPlan.vue`
- Modify: `frontend/src/departments/CuttingOrder.vue`
- Modify: `frontend/src/departments/CuttingBulkLaySheet.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Modify: `frontend/src/departments/FabricPurchaseOrder.vue`
- Modify: `frontend/src/departments/FabricDeliveryChallan.vue`
- Modify: `frontend/src/departments/FabricGoodsReceivedNote.vue`
- Modify: existing browser verification scripts for each affected workspace.

**Interfaces:**
- `DepartmentPage` accepts `inline-navigation`, default `false`, and provides `{ backTo, backLabel, inline }`.
- `InlinePageNavigation` consumes the provided fallback and accepts `show-document-navigation`, `navigation-disabled`, and `title-target` options.
- Shared heading owners render the control only when inline mode is provided.

- [ ] **Step 1: Add failing layout assertions**

Assert migrated pages have no `.department-page__nav` row, contain one labelled inline Back link adjacent to the visible heading, and reclaim the former vertical space. Assert representative creation pages retain the old nav. Assert embedded DC/GRN dialogs have no page-level control.

- [ ] **Step 2: Verify failures on workspace launcher, list, report, FormView, FabricDocumentWorkspace, and custom-header fixtures**

Run the relevant `verify_web_ui_redesign`, `verify_fabric_store_workspace`, `verify_cutting_order_workspace`, and `verify_cutting_bulk_laysheets_workspace` suites.

- [ ] **Step 3: Implement opt-in context and shared control**

Use a RouterLink for Back, preserve the current standalone row as the default, keep a stable 44px target on touch devices, and avoid global positional CSS.

- [ ] **Step 4: Opt in only the approved non-creation pages**

For Cutting Plan/Order draft editors and DC/GRN new routes, keep the existing creation navigation. Do not edit any LaySheet Planner or Sewing file.

- [ ] **Step 5: Re-run layout and responsive tests**

Expected: PASS at desktop, tablet, and mobile widths.

- [ ] **Step 6: Commit inline navigation**

Commit message: `feat: place web back navigation beside titles`

### Task 4: Validated Previous and Next Document Movement

**Files:**
- Create: `frontend/src/composables/useDocumentListNavigation.js`
- Modify: `frontend/src/components/navigation/InlinePageNavigation.vue`
- Modify: `frontend/src/components/common/FormView.vue`
- Modify: `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- Modify: `frontend/src/departments/CuttingOrder.vue`
- Modify: `frontend/src/departments/CuttingBulkLaySheet.vue`
- Modify: document wrapper files that perform `router.replace` after save/rename.
- Modify: browser verification scripts from Tasks 2–3.

**Interfaces:**
- `useDocumentListNavigation({ currentName, disabled })` returns `previousName`, `nextName`, `loading`, `changed`, `error`, `goPrevious()`, and `goNext()`.
- The composable calls `getList(doctype, { fields: ["name"], filters, orderBy, start, pageLength: 3 })` and validates the current record before exposing neighbors.
- Previous/Next uses `router.replace` and preserves the navigation reference.

- [ ] **Step 1: Add failing navigation behavior tests**

Cover direct-link Back-only behavior, first/middle/last records, crossing a page boundary, deterministic tied values, `router.replace`, browser Back returning to the list, list-changed detection after modification, load failure, editing/dirty blocking, focus transfer, and history-state preservation during save-time replace.

- [ ] **Step 2: Run focused suites and verify expected failures**

Expected: FAIL because no shared document navigator exists.

- [ ] **Step 3: Implement the composable and control states**

Fetch and validate a three-row window. Never derive a neighbor from stale `total` alone. Keep disabled controls visible, expose `List changed — return to list`, and keep the current document open on errors.

- [ ] **Step 4: Wire host editing and dirty states**

`FormView` supplies its mode; DC/GRN workspaces supply `canEdit || dirty`; custom Cutting headers supply their busy/editor state. Embedded presentation remains excluded.

- [ ] **Step 5: Re-run all navigation behavior tests**

Expected: PASS without browser errors.

- [ ] **Step 6: Commit Previous/Next movement**

Commit message: `feat: navigate filtered documents safely`

### Task 5: Server-Paginated Related Records Dialog

**Files:**
- Create: `frontend/src/components/documents/RelatedRecordsDialog.vue`
- Modify: `frontend/src/components/common/ListView.vue`
- Modify: `scripts/verify_web_ui_redesign.mjs`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- `RelatedRecordsDialog` supports `v-model:visible` and `v-model:filters`.
- Props: `title`, `doctype`, `baseFilters`, `defaultColumns`, `columnLabels`, `statusField`, `statusOptions`, `rowMark`.
- Emits: `open(row)` and `closed`.
- `ListView` accepts controlled initial advanced filters, emits applied advanced-filter changes, supports `navigation-enabled=false`, and supports `allow-bulk-actions=false`.

- [ ] **Step 1: Add failing generic-dialog tests**

Assert exact base filters reach the server list request, advanced filters synchronize outward, search/sort/pagination work, row open emits the record, bulk/page navigation are absent, empty/error states render, and a mocked 501st record is reachable through pagination.

- [ ] **Step 2: Verify the dialog tests fail because the component and controlled filter interface are absent**

- [ ] **Step 3: Implement the controlled `ListView` additions and dialog**

Reuse `ListView`; do not create a second table/filter implementation. Keep the dialog mounted across record open/return so pagination and filters survive.

- [ ] **Step 4: Re-run generic dialog tests**

Expected: PASS at desktop and mobile sizes.

- [ ] **Step 5: Commit the reusable dialog**

Commit message: `feat: add expanded related records dialog`

### Task 6: Expand Cutting Marker and Lay Sheet Lists

**Files:**
- Modify: `frontend/src/departments/cutting/CuttingPlanSidebar.vue`
- No modification: `frontend/src/departments/cutting/shared/CuttingParentSidebar.vue` unless a prop passthrough is demonstrably required.
- Modify: `scripts/verify_web_ui_redesign.mjs`
- Modify: `scripts/verify_cutting_order_workspace.mjs`

**Interfaces:**
- Expand buttons open `RelatedRecordsDialog` with resolved `cutting_plan` or `cutting_order` base filters.
- Existing `CuttingMarkerDialog` and `CuttingLaySheetDialog` remain record views.

- [ ] **Step 1: Add failing Cutting rail tests**

Assert Expand sits immediately left of Filters for both sections, carries accessible dialog attributes, opens the correct DocType and parent filter for Cutting Plan and Cutting Order, synchronizes safe filters, and returns focus after close.

- [ ] **Step 2: Verify the focused Cutting suites fail**

- [ ] **Step 3: Implement expanded list state and record handoff**

Close the list before opening a Marker/Lay Sheet, remember its origin, and reopen the list when the record dialog closes. Preserve create, filter, permission, refresh, and existing dialog behavior.

- [ ] **Step 4: Re-run Cutting Plan, Cutting Order, and entity-dialog suites**

Expected: PASS with existing Marker/Lay Sheet flows unchanged.

- [ ] **Step 5: Commit Cutting expansion**

Commit message: `feat: expand cutting related record lists`

### Task 7: Expand Work Order DC and GRN Lists

**Files:**
- Modify: `frontend/src/departments/fabric-store/WorkOrderActivityRail.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- `WorkOrderActivityRail` accepts `workOrder`, keeps the existing `open({ type, row })` record contract, and exposes `reopenExpanded()` for the parent to call when the related-record dialog closes.
- DC base filter is `{ work_order: workOrder }`.
- GRN base filters are `{ against: "YRP Work Order", against_id: workOrder }`.

- [ ] **Step 1: Add failing shared Work Order rail tests**

Cover Fabric, Cut Panel, and Accessory route fixtures. Assert Expand precedes the filter action, exact base filters are requested, Purchase Order remains unchanged, permissions hide unreadable sections, and closing the existing related-record dialog reopens the expanded list.

- [ ] **Step 2: Verify the Work Order suite fails on missing Expand actions**

- [ ] **Step 3: Implement the shared rail integration**

Reuse `RelatedRecordsDialog` and `RelatedDocumentWorkspaceDialog`. Keep current compact search, New actions, card previews, and mobile behavior.

- [ ] **Step 4: Re-run Work Order, DC, GRN, Purchase Order, document-dialog, and responsive tests**

Expected: PASS without changing Purchase Order related lists.

- [ ] **Step 5: Commit Work Order expansion**

Commit message: `feat: expand work order activity lists`

### Task 8: Whole-Flow Verification, Review, and Telegram Evidence

**Files:**
- Modify tests only if a real defect discovered during verification requires a new failing regression.
- Create screenshots outside the repository or in the existing approved evidence location.

**Interfaces:**
- Final evidence covers inline Back, Previous/Next, expanded Cutting related lists, and expanded Work Order related lists.

- [ ] **Step 1: Run static and unit verification**

```bash
git diff --check
node scripts/test_list_navigation.mjs
node scripts/test_document_overview.mjs
npm run build --prefix frontend
```

- [ ] **Step 2: Run focused and surrounding browser suites**

Run the navigation/list/entity suites plus complete Cutting Plan, Cutting Order, Bulk LaySheet, Fabric Work Order, Purchase Order, DC, and GRN suites. Report any unrelated pre-existing failure explicitly.

- [ ] **Step 3: Prove excluded areas are untouched**

Compare checksums and scoped diffs for all Sewing and Cutting LaySheet Planner source files against the pre-implementation baseline. Open representative creation routes and verify their forms remain unchanged.

- [ ] **Step 4: Request independent code review**

Review for wrong-record navigation, stale state, permission leakage, embedded-navigation leakage, focus/accessibility regressions, and accidental changes to excluded areas. Fix every Critical or Important finding with a failing test first.

- [ ] **Step 5: Capture final screenshots**

Capture desktop screenshots of:

- inline Back plus Previous/Next on a filtered Cutting Plan;
- expanded Markers list;
- expanded Lay Sheets list;
- expanded Work Order Delivery Challans list;
- expanded Work Order GRNs list.

- [ ] **Step 6: Send screenshots to Telegram**

Use the existing project Telegram sender, attach all screenshots under topic `yrp_po`, verify successful delivery, and report the message identifiers. If no sender is configured, report the exact blocker without exposing credentials.

- [ ] **Step 7: Commit any final test-only fixes and report completion**

Final report includes commit IDs, passed suites, excluded-area proof, Telegram delivery IDs, and any non-blocking known limitations.
