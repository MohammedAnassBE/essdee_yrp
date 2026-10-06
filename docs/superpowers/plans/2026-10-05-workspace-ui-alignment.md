# Cutting and Fabric Store Workspace UI Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align Cutting Orders, Bulk LaySheets, LaySheet Planner, and Fabric Store with the finalized Cutting Plan UI strategy.

**Architecture:** Extract the existing Cutting card launcher into a shared presentation component, route each Fabric Store destination to a focused page, and adapt existing record action components into header controls. Keep current server contracts and workflow dialogs authoritative and unchanged.

**Tech Stack:** Vue 3, PrimeVue, Vue Router, Vite, Frappe RPC, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-workspace-ui-alignment.md`

## Global Constraints

- Preserve existing business logic and Frappe permission enforcement.
- Reuse existing enterprise CSS tokens and common ListView components.
- Do not add dependencies or redirect workflows to Desk.
- Do not commit changes.

## Review Focus

- A user lacking permission for one Fabric Store section must not see its launcher card or route content.
- Header context must truncate long values without pushing actions outside the viewport.
- Action menus must expose exactly the controller-authorized actions and remain server-protected.
- Fabric Store dialogs must retain their current create, submit, cancel, amend, return, and print behavior after routing changes.
- All focused pages must remain usable without page-level horizontal overflow at supported viewports.

---

### Task 1: Shared workspace launcher and routed Fabric Store sections

**Files:**
- Create: `frontend/src/components/common/WorkspaceLauncher.vue`
- Modify: `frontend/src/departments/Cutting.vue`
- Modify: `frontend/src/departments/FabricStore.vue`
- Create: `frontend/src/departments/FabricStoreSection.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Produces: `WorkspaceLauncher` accepting `title`, `items`, and `loading`; Fabric routes `/fabric-store/work-orders`, `/purchase-orders`, `/stock-transfers`, and `/reports`.

- [ ] Write browser assertions for four permission-aware cards and four focused routes.
- [ ] Run the shell suite and confirm it fails against the tabbed Fabric Store page.
- [ ] Extract the launcher and implement the focused routes without changing child workflows.
- [ ] Run the Fabric Store suites and frontend build.

### Task 2: Cutting Order header and action alignment

**Files:**
- Modify: `frontend/src/departments/CuttingOrders.vue`
- Modify: `frontend/src/departments/CuttingOrder.vue`
- Modify: `frontend/src/departments/cutting/order/CuttingOrderActions.vue`
- Modify: `frontend/src/departments/cutting/order/CuttingOrderTabs.vue`
- Modify: `scripts/verify_cutting_order_workspace.mjs`

**Interfaces:**
- Produces: header-level `More Actions` menu with existing calculate/completion commands.

- [ ] Add assertions for the primary Create button, context facts, header menu, and removed command strip.
- [ ] Run the order suite and confirm the new assertions fail.
- [ ] Implement the header/menu changes and remove duplicate Detail/Item cells.
- [ ] Run the order and shared UI suites.

### Task 3: Bulk LaySheets and Planner alignment

**Files:**
- Modify: `frontend/src/departments/CuttingBulkLaySheets.vue`
- Modify: `frontend/src/departments/CuttingBulkLaySheet.vue`
- Modify: `frontend/src/departments/cutting/bulk/BulkActions.vue`
- Modify: `frontend/src/departments/CuttingLaySheetPlanners.vue`
- Modify: `frontend/src/departments/CuttingLaySheetPlanner.vue`
- Modify: `scripts/verify_cutting_bulk_laysheets_workspace.mjs`
- Modify: `scripts/verify_cutting_laysheet_planner_workspace.mjs`

**Interfaces:**
- Produces: Bulk header `More Actions`, compact non-duplicated setup facts, and Planner header context with one conventional primary action.

- [ ] Add failing browser assertions for the aligned headers and primary list actions.
- [ ] Implement the targeted component changes without changing workflow methods.
- [ ] Run Bulk, Planner, and shared UI suites.

### Task 4: Final responsive and regression verification

**Files:**
- Modify: `scripts/verify_web_ui_redesign.mjs` only where shared route expectations changed.

**Interfaces:**
- Consumes: all aligned routes and header components from Tasks 1–3.

- [ ] Extend responsive route coverage for focused Fabric Store pages.
- [ ] Run all focused browser suites and `node scripts/verify_web_ui_redesign.mjs all`.
- [ ] Run `npm run build` and `git diff --check`.
- [ ] Visually inspect the landing pages and one representative record from each workspace at 1800×1100.

### Task 5: Shared rendered-control quality contract

**Files:**
- Modify: `frontend/src/styles/enterprise.css`
- Modify: focused Vue components only when a component selector leaks into a control
- Modify: `scripts/verify_web_ui_redesign.mjs`
- Modify: `scripts/verify_cutting_order_workspace.mjs`
- Modify: `scripts/verify_cutting_bulk_laysheets_workspace.mjs`
- Modify: `scripts/verify_cutting_laysheet_planner_workspace.mjs`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Produces: a rendered-browser contract for readable button labels/icons, no accidental descendant-style inheritance, no visible text below 11px, and no page-level horizontal overflow across every implemented `/web` route.

- [ ] Add browser assertions that enabled button labels/icons inherit the owning button colour and remain visible in Cutting Plan dialogs.
- [ ] Run the dialog suite and confirm the selector-leak assertion fails against the broad Lay Sheet header selector.
- [ ] Narrow component selectors to their semantic label/count elements; never target generic descendant `span` elements around interactive controls.
- [ ] Inventory and render every implemented Cutting and Fabric Store route at desktop, tablet, and mobile widths; repair overflow, truncation without recovery, weak action hierarchy, and duplicated context without changing workflows.
- [ ] Run all focused browser suites, the shared redesign suite, `npm run build`, and `git diff --check`.

### Task 6: Cutting Plan completion gate

**Files:**
- Modify: `frontend/src/departments/cutting/CuttingPlanTabs.vue`
- Modify: `frontend/src/departments/cutting/CuttingCompletedReport.vue`
- Modify: `frontend/src/departments/cutting/CuttingMarkerDialog.vue`
- Modify: `frontend/src/departments/cutting/CuttingLaySheetDialog.vue`
- Modify: `frontend/src/departments/cutting/CuttingPlanSidebar.vue`
- Modify: `frontend/src/departments/cutting/CuttingPlanActions.vue`
- Modify: `essdee_yrp/essdee_yrp/doctype/sd_yrp_cutting_plan/sd_yrp_cutting_plan.py`
- Modify: relevant cutting tests and `scripts/verify_web_ui_redesign.mjs`

**Interfaces:**
- Produces: truthful completion/excess summaries, permission-gated Recut/Print Panel data, compact Marker read mode, fixed Lay Sheet tabs, recoverable rail identities, and guarded dirty dialogs.

- [ ] Add failing backend permission tests for Recut/Print Panel payloads and endpoints.
- [ ] Enforce the child DocType read permission on the server and hide unauthorized Summary sections.
- [ ] Add failing browser assertions for completed/excess counts and totals, then make Summary show only business-relevant rows.
- [ ] Add failing browser assertions for compact submitted Marker view, sticky Lay Sheet tabs, tab reset, full rail identity recovery, and fixed action-dialog footers.
- [ ] Implement the smallest UI changes that satisfy those assertions while preserving all existing mutation and permission checks.
- [ ] Run Cutting Plan backend, permission, creation, sidebar, stock, and shared UI suites.
