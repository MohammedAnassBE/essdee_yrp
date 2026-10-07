# Cut Panel Store Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the complete six-card Cut Panel Store in `/web`, including global Cut Panel Movement operations, shared Work Orders, Cut Bundle Edit, Box Sticker Print, Excel Sticker Print, and two reports.

**Architecture:** Add a permission-aware `essdee_yrp.cut_panel_store` browser-service boundary that delegates all domain behavior to existing Frappe/YRP/Essdee controllers. Compose the UI from the established Cutting and Fabric Store shells, extracting only the movement editor boundary needed for shared plan-scoped and global use. Keep each operational tool in a focused Vue component and backend module.

**Tech Stack:** Python/Frappe 16, Vue 3 Composition API, PrimeVue, Vite, Frappe REST/RPC, Playwright-style browser verification, QZ Tray/ZPL.

**Spec:** `docs/superpowers/specs/2026-10-07-cut-panel-store-workspace-design.md`

## Global Constraints

- The landing page has exactly six permission-aware cards: Cut Panel Movement, Work Orders, Cut Bundle Edit, Box Sticker Print, Excel Sticker Print, and Reports.
- Raw Sticker Print is absent.
- Normal work remains inside `/web`; no Desk redirects and no browser-native confirmations.
- Reuse the existing enterprise theme, shared lists, shared application error popup, document dialogs, printing utilities, and report shell.
- Frappe controllers and installed YRP/Essdee services remain authoritative for business rules, stock, bundles, printing totals, lifecycle, and permissions.
- Lists have no implicit department, process, warehouse, supplier, or item filters.
- Every mutation rechecks permission, state, authoritative source data, and expected `modified` where applicable.
- Existing Cutting, Fabric Store, Stock Transfer, and report behavior must remain green.
- Use test-first implementation: every production behavior begins with a failing focused test.

## Review Focus

- A store-created movement has no Cutting Plan: it must derive Item from Lot, keep `movement_from_cutting = 0`, and still load/save exact, collapsed, and accessory rows.
- A second root transaction is created concurrently: Stock Entry/DC/GRN creation must fail clearly and refresh the movement rail without corrupting the first transaction.
- QZ fails after Box Sticker quantities are reserved: rollback must run exactly once and restore printed quantities before the error popup appears.
- An Excel attachment is empty, malformed, unreadable, or not owned/readable by the user: submission must preserve the draft and return a safe message without a traceback.
- A Work Order opened under Cut Panel Store must keep Cut Panel Store back/create/edit routes while the same component under Fabric Store retains Fabric Store routes.

---

## File Structure

### Backend

- `essdee_yrp/cut_panel_store/__init__.py`: package boundary.
- `essdee_yrp/cut_panel_store/common.py`: permission, lifecycle, concurrency, and serialization helpers shared by the four editors.
- `essdee_yrp/cut_panel_store/web_workspace.py`: capabilities facade and whitelisted API exports.
- `essdee_yrp/cut_panel_store/movement_workspace.py`: global movement editor, authoritative availability, linked projection, and transaction orchestration.
- `essdee_yrp/cut_panel_store/cut_bundle_workspace.py`: Cut Bundle Edit editor and label-print orchestration.
- `essdee_yrp/cut_panel_store/box_sticker_workspace.py`: Box Sticker editor, preview, printer, quantity, and rollback contract.
- `essdee_yrp/cut_panel_store/excel_sticker_workspace.py`: attachment, document, preview, and print contract.
- `essdee_yrp/cut_panel_store/report_workspace.py`: Cut Bundle Balance permission and report facade.
- `essdee_yrp/test_cut_panel_store_capabilities.py`: launcher and permission tests.
- `essdee_yrp/test_cut_panel_store_movement.py`: movement and linked-transaction tests.
- `essdee_yrp/test_cut_panel_store_cut_bundle.py`: Cut Bundle Edit tests.
- `essdee_yrp/test_cut_panel_store_box_sticker.py`: Box Sticker tests.
- `essdee_yrp/test_cut_panel_store_excel_sticker.py`: Excel Sticker tests.
- `essdee_yrp/test_cut_panel_store_reports.py`: report contract tests.

### Frontend

- `frontend/src/api/cutPanelStore.js`: typed-by-convention RPC wrapper functions for Cut Panel Store endpoints.
- `frontend/src/api/frappe.js`: authenticated file upload helper.
- `frontend/src/departments/CutPanelStore.vue`: six-card permission-aware launcher.
- `frontend/src/departments/CutPanelStoreSection.vue`: section shell, loading, permission, and routing.
- `frontend/src/departments/cut-panel-store/CutPanelMovements.vue`: global movement list and dialog host.
- `frontend/src/departments/cut-panel-store/CutPanelMovementDialog.vue`: global movement popup and 80/20 composition.
- `frontend/src/departments/cut-panel-store/CutPanelMovementRail.vue`: linked Stock Entry/DC/GRN rail.
- `frontend/src/departments/cut-panel-store/CutBundleEdits.vue`: list and editor host.
- `frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue`: bundle edit form and printing.
- `frontend/src/departments/cut-panel-store/BoxStickerPrints.vue`: list and editor host.
- `frontend/src/departments/cut-panel-store/BoxStickerPrintDialog.vue`: Box Sticker form, preview, and printing.
- `frontend/src/departments/cut-panel-store/ExcelStickerPrints.vue`: list and editor host.
- `frontend/src/departments/cut-panel-store/ExcelStickerPrintDialog.vue`: Excel upload, preview, and printing.
- `frontend/src/departments/cut-panel-store/PrinterDialog.vue`: shared single-printer/resolution selector for Cut Panel Store tools.
- `frontend/src/departments/cut-panel-store/CutPanelStoreReports.vue`: two-report tab shell.
- `frontend/src/departments/cut-panel-store/CutBundleBalanceReport.vue`: Cut Bundle Balance filters, metrics, and table.
- `frontend/src/departments/cutting/CpmMovementDialog.vue`: thin Cutting-specific dialog wrapper after editor extraction.
- `frontend/src/departments/cutting/CutPanelMovementEditor.vue`: shared exact/collapsed/accessory movement editor.
- `frontend/src/departments/fabric-store/FabricWorkOrders.vue`: configurable route names.
- `frontend/src/departments/FabricWorkOrder.vue`: configurable navigation context.
- `frontend/src/departments/FabricWorkOrderEditorPage.vue`: configurable navigation context.
- `frontend/src/router/index.js`: Cut Panel Store routes and route props.
- `frontend/src/styles/enterprise.css`: only shared dialog/list refinements that cannot remain component-scoped.

### Verification

- `scripts/verify_cut_panel_store_workspace.mjs`: mocked and live-safe browser contract covering all six cards and state paths.
- `scripts/audit_web_ui_contract.mjs`: Cut Panel Store route inventory.
- `scripts/verify_theme_portals.mjs`: Cut Panel Store theme/portal coverage.

---

### Task 1: Capability facade, six-card launcher, and route shell

**Files:**
- Create: `essdee_yrp/cut_panel_store/__init__.py`
- Create: `essdee_yrp/cut_panel_store/common.py`
- Create: `essdee_yrp/cut_panel_store/web_workspace.py`
- Create: `essdee_yrp/test_cut_panel_store_capabilities.py`
- Create: `frontend/src/api/cutPanelStore.js`
- Modify: `frontend/src/departments/CutPanelStore.vue`
- Create: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `frontend/src/router/index.js`
- Create: `scripts/verify_cut_panel_store_workspace.mjs`
- Modify: `scripts/audit_web_ui_contract.mjs`

**Interfaces:**
- Produces: `get_capabilities() -> {sections: Record<string, Capability>}` in `web_workspace.py`.
- Produces: `getCutPanelStoreCapabilities()` in `cutPanelStore.js`.
- Produces: route names `cut-panel-movements`, `cut-panel-work-orders`, `cut-panel-cut-bundle-edits`, `cut-panel-box-stickers`, `cut-panel-excel-stickers`, and `cut-panel-reports`.

- [ ] **Step 1: Write failing capability tests**

Add tests named `test_capabilities_expose_exact_six_sections_when_permitted`, `test_capabilities_omit_unreadable_sections`, and `test_report_capability_requires_report_permission`. Assert exact keys and the absence of Raw Sticker Print.

- [ ] **Step 2: Run capability tests and verify RED**

Run: `bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_capabilities`

Expected: FAIL because `essdee_yrp.cut_panel_store.web_workspace` does not exist.

- [ ] **Step 3: Write failing launcher/route browser assertions**

Add a `launcher` suite that mocks capabilities, visits `/web/cut-panel-store`, asserts the six exact cards and links, asserts Raw Sticker Print is absent, visits every section route, and verifies loading/error/permission states.

- [ ] **Step 4: Run the browser suite and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs launcher`

Expected: FAIL because the launcher and section routes do not exist.

- [ ] **Step 5: Implement the capability facade and route shell**

Implement `_permission_flags(doctype: str) -> dict`, `_section_capability(key: str, doctype: str) -> dict`, and `get_capabilities() -> dict`. Implement the six cards and route shells with permission-driven rendering and shared loading/empty states.

- [ ] **Step 6: Verify GREEN**

Run both commands from Steps 2 and 4. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add essdee_yrp/cut_panel_store essdee_yrp/test_cut_panel_store_capabilities.py frontend/src/api/cutPanelStore.js frontend/src/departments/CutPanelStore.vue frontend/src/departments/CutPanelStoreSection.vue frontend/src/router/index.js scripts/verify_cut_panel_store_workspace.mjs scripts/audit_web_ui_contract.mjs
git commit -m "feat: add cut panel store workspace shell"
```

### Task 2: Global Cut Panel Movement editor

**Files:**
- Create: `essdee_yrp/cut_panel_store/movement_workspace.py`
- Create: `essdee_yrp/test_cut_panel_store_movement.py`
- Modify: `essdee_yrp/cutting/web_workspace.py`
- Modify: `frontend/src/api/cutPanelStore.js`
- Create: `frontend/src/departments/cutting/CutPanelMovementEditor.vue`
- Modify: `frontend/src/departments/cutting/CpmMovementDialog.vue`
- Create: `frontend/src/departments/cut-panel-store/CutPanelMovements.vue`
- Create: `frontend/src/departments/cut-panel-store/CutPanelMovementDialog.vue`
- Modify: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`

**Interfaces:**
- Consumes: Task 1 capability and section shell.
- Produces: `get_movement_editor(name: str | None, source=None) -> dict`, `generate_movement_bundles(values) -> dict`, `save_movement(values, name=None, submit=False, expected_modified=None) -> dict`, and `execute_movement_command(name, command, expected_modified=None) -> dict`.
- Produces: `CutPanelMovementEditor` props `modelValue`, `context`, `record`, `editable`; emits `update:modelValue`.

- [ ] **Step 1: Write failing movement server tests**

Cover new global movement defaults, Item derivation from Lot, `movement_from_cutting = 0`, exact/collapsed/accessory selections, authoritative regeneration, overdrawn/forged row rejection, stale modification rejection, and preservation of plan-created movement reads.

- [ ] **Step 2: Run movement tests and verify RED**

Run: `bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_movement`

Expected: FAIL because global movement endpoints do not exist.

- [ ] **Step 3: Add failing movement browser tests**

Assert list defaults, Create Movement visibility, maximizable popup, Lot/From Warehouse/posting controls, exact/collapsed/accessory matrices, one primary Save action, submit/cancel confirmation, popup errors, unsaved-value preservation, and responsive popup containment.

- [ ] **Step 4: Run focused browser test and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs movements`

Expected: FAIL at the missing movement list/editor.

- [ ] **Step 5: Extract the shared movement editor**

Move matrix rendering and selection behavior from `CpmMovementDialog.vue` into `CutPanelMovementEditor.vue`. Keep Cutting's API wrapper and visible behavior unchanged; its dialog retains plan identity and lifecycle orchestration.

- [ ] **Step 6: Implement global movement services and UI**

Implement `_movement_context(doc=None, source=None) -> dict`, `_authoritative_selection(values, doc=None) -> dict`, and the four public interfaces. Add the list and popup using the extracted editor and shared confirmation/error components.

- [ ] **Step 7: Verify GREEN and Cutting regression**

Run the server test, `node scripts/verify_cut_panel_store_workspace.mjs movements`, and `node scripts/verify_cutting_stock_workflows.mjs`.

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add essdee_yrp/cut_panel_store/movement_workspace.py essdee_yrp/test_cut_panel_store_movement.py essdee_yrp/cutting/web_workspace.py frontend/src/api/cutPanelStore.js frontend/src/departments/cutting/CutPanelMovementEditor.vue frontend/src/departments/cutting/CpmMovementDialog.vue frontend/src/departments/cut-panel-store/CutPanelMovements.vue frontend/src/departments/cut-panel-store/CutPanelMovementDialog.vue frontend/src/departments/CutPanelStoreSection.vue scripts/verify_cut_panel_store_workspace.mjs
git commit -m "feat: add cut panel movement workspace"
```

### Task 3: Movement linked-document rail and Stock Entry/DC/GRN creation

**Files:**
- Modify: `essdee_yrp/cut_panel_store/movement_workspace.py`
- Modify: `essdee_yrp/test_cut_panel_store_movement.py`
- Modify: `frontend/src/api/cutPanelStore.js`
- Create: `frontend/src/departments/cut-panel-store/CutPanelMovementRail.vue`
- Modify: `frontend/src/departments/cut-panel-store/CutPanelMovementDialog.vue`
- Reuse: `frontend/src/departments/cutting/CpmMovementTransactionDialog.vue`
- Reuse: `frontend/src/departments/cutting/CpmTransactionDialog.vue`
- Reuse: `frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue`
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`

**Interfaces:**
- Consumes: Task 2 movement workspace and existing `build_stock_entry_defaults`, `build_delivery_challan_defaults`, and `build_goods_received_note_defaults`.
- Produces: `get_movement_linked_documents(name: str) -> dict`, `get_movement_work_orders(name: str, txt='') -> list`, and `create_movement_transaction(name, operation, values, submit=False) -> dict`.

- [ ] **Step 1: Extend failing server tests**

Assert the rail includes readable active Stock Entry/DC/GRN records; unreadable records are omitted; Work Order choices are submitted and same-Lot; all three creation paths use authoritative defaults; a concurrent second root transaction is rejected with a clear message; and successful/cancelled transactions refresh capabilities.

- [ ] **Step 2: Run server tests and verify RED**

Run the movement test module. Expected: FAIL at missing linked-document interfaces.

- [ ] **Step 3: Add failing 80/20 and transaction browser tests**

Assert desktop column proportions, responsive rail placement, three rail sections, open-row dialogs, Work Order selection for DC/GRN, Stock Entry editor, complete embedded Fabric DC/GRN workspaces, shared error popup, and parent refresh after save/submit/cancel.

- [ ] **Step 4: Run focused browser test and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs movement-transactions`

Expected: FAIL because the rail/actions are absent.

- [ ] **Step 5: Implement linked projection and named transaction commands**

Use `get_active_root_transactions` plus permission-aware document serialization. Validate `operation` against `{'stock_entry', 'delivery_challan', 'goods_received_note'}` and validate the selected Work Order server-side before calling existing builders/services.

- [ ] **Step 6: Implement the rail and embedded flows**

Keep related lists independently scrollable, newest-first, and refresh the movement workspace after every mutation. Use the full Fabric Store DC/GRN workspace rather than reduced forms.

- [ ] **Step 7: Verify GREEN and Fabric regression**

Run the movement server tests, focused browser test, and `node scripts/verify_fabric_store_workspace.mjs all`.

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add essdee_yrp/cut_panel_store/movement_workspace.py essdee_yrp/test_cut_panel_store_movement.py frontend/src/api/cutPanelStore.js frontend/src/departments/cut-panel-store/CutPanelMovementRail.vue frontend/src/departments/cut-panel-store/CutPanelMovementDialog.vue scripts/verify_cut_panel_store_workspace.mjs
git commit -m "feat: add cut panel movement transactions"
```

### Task 4: Shared Work Orders under Cut Panel Store routes

**Files:**
- Modify: `frontend/src/departments/fabric-store/FabricWorkOrders.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Modify: `frontend/src/departments/FabricWorkOrderEditorPage.vue`
- Modify: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Consumes: existing Fabric Store Work Order API and domain components.
- Produces: route-context props `{ listRouteName, viewRouteName, newRouteName, editRouteName, backTo, backLabel }` with Fabric Store defaults.

- [ ] **Step 1: Add failing dual-context browser tests**

Assert Cut Panel Store list/view/new/edit routes, Cut Panel Store back navigation, duplicate/edit staying in Cut Panel Store, embedded DC/GRN parity, and unchanged Fabric Store route behavior.

- [ ] **Step 2: Run focused suites and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs work-orders`

Expected: FAIL because Cut Panel Store Work Order routes are missing.

- [ ] **Step 3: Parameterize Work Order navigation**

Add the route-context props with existing Fabric Store values as defaults. Pass Cut Panel Store values only from its routes/section shell; do not branch domain behavior.

- [ ] **Step 4: Verify GREEN in both contexts**

Run the Cut Panel Store Work Order suite and `node scripts/verify_fabric_store_workspace.mjs work-order`.

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/departments/fabric-store/FabricWorkOrders.vue frontend/src/departments/FabricWorkOrder.vue frontend/src/departments/FabricWorkOrderEditorPage.vue frontend/src/departments/CutPanelStoreSection.vue frontend/src/router/index.js scripts/verify_cut_panel_store_workspace.mjs scripts/verify_fabric_store_workspace.mjs
git commit -m "feat: share work orders with cut panel store"
```

### Task 5: Cut Bundle Edit list, editor, lifecycle, and label printing

**Files:**
- Create: `essdee_yrp/cut_panel_store/cut_bundle_workspace.py`
- Create: `essdee_yrp/test_cut_panel_store_cut_bundle.py`
- Modify: `essdee_yrp/cut_panel_store/web_workspace.py`
- Modify: `frontend/src/api/cutPanelStore.js`
- Create: `frontend/src/departments/cut-panel-store/CutBundleEdits.vue`
- Create: `frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue`
- Create: `frontend/src/departments/cut-panel-store/PrinterDialog.vue`
- Modify: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`

**Interfaces:**
- Produces: `get_cut_bundle_editor(name=None, source=None) -> dict`, `preview_cut_bundle_source(lot, warehouse, values=None) -> dict`, `save_cut_bundle(values, name=None, submit=False, expected_modified=None) -> dict`, `execute_cut_bundle_command(name, command, expected_modified=None) -> dict`, and `get_cut_bundle_print_data(name, printer) -> dict`.

- [ ] **Step 1: Write failing Cut Bundle server tests**

Cover permission, defaults, authoritative input/output bundle identity, stale and forged rows, save/submit/cancel, printed-time update only after confirmed print, and safe handling of a record without a Cutting Plan.

- [ ] **Step 2: Run server tests and verify RED**

Run: `bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_cut_bundle`

Expected: FAIL because the workspace module does not exist.

- [ ] **Step 3: Add failing browser tests**

Assert list/default columns, maximizable popup, compact fields, before/after bundle tables, lifecycle actions, QZ printer selection, Print Labels eligibility, printed-time refresh, error popup, and responsive containment.

- [ ] **Step 4: Run browser test and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs cut-bundle-edit`

Expected: FAIL at missing list/editor.

- [ ] **Step 5: Implement backend and frontend**

Delegate data generation and validation to the existing `SD YRP Cut Bundle Edit` controller/onload contract. Keep the printer selector reusable for later sticker tasks.

- [ ] **Step 6: Verify GREEN**

Run the server and browser commands. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add essdee_yrp/cut_panel_store/cut_bundle_workspace.py essdee_yrp/test_cut_panel_store_cut_bundle.py essdee_yrp/cut_panel_store/web_workspace.py frontend/src/api/cutPanelStore.js frontend/src/departments/cut-panel-store/CutBundleEdits.vue frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue frontend/src/departments/cut-panel-store/PrinterDialog.vue frontend/src/departments/CutPanelStoreSection.vue scripts/verify_cut_panel_store_workspace.mjs
git commit -m "feat: add cut bundle edit workspace"
```

### Task 6: Box Sticker Print list, editor, preview, and transactional printing

**Files:**
- Create: `essdee_yrp/cut_panel_store/box_sticker_workspace.py`
- Create: `essdee_yrp/test_cut_panel_store_box_sticker.py`
- Modify: `essdee_yrp/cut_panel_store/web_workspace.py`
- Modify: `frontend/src/api/cutPanelStore.js`
- Create: `frontend/src/departments/cut-panel-store/BoxStickerPrints.vue`
- Create: `frontend/src/departments/cut-panel-store/BoxStickerPrintDialog.vue`
- Modify: `frontend/src/departments/cut-panel-store/PrinterDialog.vue`
- Modify: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`

**Interfaces:**
- Produces: `get_box_sticker_editor(name=None, source=None) -> dict`, `preview_box_sticker_source(lot, fg_item, values=None) -> dict`, `save_box_sticker(values, name=None, submit=False, expected_modified=None) -> dict`, `get_box_sticker_preview(name) -> dict`, `reserve_box_sticker_print(name, rows, printer_type, expected_modified=None) -> dict`, and `rollback_box_sticker_print(reservation) -> dict`.

- [ ] **Step 1: Write failing Box Sticker server tests**

Cover authoritative size/MRP rows, excess limits, zero quantities, print permission, configured printer filtering, preview output, locked reservation, successful totals, idempotent rollback, rollback after failure, and stale/forged detail names.

- [ ] **Step 2: Run server tests and verify RED**

Run the Box Sticker test module. Expected: FAIL at missing workspace functions.

- [ ] **Step 3: Add failing browser tests**

Assert list/editor, source refresh, row fields, preview image state, printer/resolution selection, positive quantities, QZ success, QZ failure invoking rollback exactly once, updated printed totals, and application error popup.

- [ ] **Step 4: Run browser test and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs box-stickers`

Expected: FAIL at missing list/editor.

- [ ] **Step 5: Implement transactional print orchestration**

Wrap existing Box Sticker ZPL and rollback methods behind reservation IDs or equivalent idempotency data. The client must call rollback only when raw output was reserved but QZ did not confirm success.

- [ ] **Step 6: Verify GREEN**

Run server and browser tests. Expected: PASS, including the exact-once rollback assertion.

- [ ] **Step 7: Commit**

```bash
git add essdee_yrp/cut_panel_store/box_sticker_workspace.py essdee_yrp/test_cut_panel_store_box_sticker.py essdee_yrp/cut_panel_store/web_workspace.py frontend/src/api/cutPanelStore.js frontend/src/departments/cut-panel-store/BoxStickerPrints.vue frontend/src/departments/cut-panel-store/BoxStickerPrintDialog.vue frontend/src/departments/cut-panel-store/PrinterDialog.vue frontend/src/departments/CutPanelStoreSection.vue scripts/verify_cut_panel_store_workspace.mjs
git commit -m "feat: add box sticker print workspace"
```

### Task 7: Excel Sticker upload, preview, lifecycle, and printing

**Files:**
- Create: `essdee_yrp/cut_panel_store/excel_sticker_workspace.py`
- Create: `essdee_yrp/test_cut_panel_store_excel_sticker.py`
- Modify: `essdee_yrp/cut_panel_store/web_workspace.py`
- Modify: `frontend/src/api/frappe.js`
- Modify: `frontend/src/api/cutPanelStore.js`
- Create: `frontend/src/departments/cut-panel-store/ExcelStickerPrints.vue`
- Create: `frontend/src/departments/cut-panel-store/ExcelStickerPrintDialog.vue`
- Modify: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`

**Interfaces:**
- Produces: `uploadFile(file: File, options={}) -> Promise<FileRecord>` in `frappe.js`.
- Produces: `get_excel_sticker_editor(name=None) -> dict`, `save_excel_sticker(values, name=None, submit=False, expected_modified=None) -> dict`, `get_excel_sticker_preview(name) -> dict`, and `get_excel_sticker_print_data(name, printer_type) -> str`.

- [ ] **Step 1: Write failing Excel Sticker server tests**

Cover readable attachment ownership, `.xlsx` requirement, empty/malformed/unreadable workbook messages, draft preservation, serialized row count/sample projection, preview, 200/300 dpi output, positive print-quantity rows, lifecycle, and permissions.

- [ ] **Step 2: Run server tests and verify RED**

Run the Excel Sticker test module. Expected: FAIL at missing workspace functions.

- [ ] **Step 3: Add failing upload/print browser tests**

Assert list/editor, authenticated multipart upload, upload progress/disabled submit, format selection, submitted preview, row count/sample, printer/resolution selection, QZ output, malformed workbook popup, and retained draft inputs.

- [ ] **Step 4: Run browser test and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs excel-stickers`

Expected: FAIL at missing editor/upload helper.

- [ ] **Step 5: Implement attachment and print workflow**

Use `/api/method/upload_file` with CSRF credentials and `FormData`; do not force JSON content headers. Delegate parsing/ZPL to `YRP Excel Sticker Print` and project only a bounded safe sample to the browser.

- [ ] **Step 6: Verify GREEN**

Run server and browser tests. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add essdee_yrp/cut_panel_store/excel_sticker_workspace.py essdee_yrp/test_cut_panel_store_excel_sticker.py essdee_yrp/cut_panel_store/web_workspace.py frontend/src/api/frappe.js frontend/src/api/cutPanelStore.js frontend/src/departments/cut-panel-store/ExcelStickerPrints.vue frontend/src/departments/cut-panel-store/ExcelStickerPrintDialog.vue frontend/src/departments/CutPanelStoreSection.vue scripts/verify_cut_panel_store_workspace.mjs
git commit -m "feat: add excel sticker print workspace"
```

### Task 8: Stock Balance and Cut Bundle Balance reports

**Files:**
- Create: `essdee_yrp/cut_panel_store/report_workspace.py`
- Create: `essdee_yrp/test_cut_panel_store_reports.py`
- Modify: `essdee_yrp/cut_panel_store/web_workspace.py`
- Modify: `frontend/src/api/cutPanelStore.js`
- Create: `frontend/src/departments/cut-panel-store/CutPanelStoreReports.vue`
- Create: `frontend/src/departments/cut-panel-store/CutBundleBalanceReport.vue`
- Modify: `frontend/src/departments/CutPanelStoreSection.vue`
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`

**Interfaces:**
- Produces: `get_cut_bundle_balance(filters=None) -> {columns: list, result: list}`.
- Reuses: `components/reports/StockBalanceReport.vue` unchanged.

- [ ] **Step 1: Write failing report tests**

Assert report permission, exact Lot/Supplier filters, stable column projection, positive balance rows, and denial without ledger/report access.

- [ ] **Step 2: Run server tests and verify RED**

Run the reports test module. Expected: FAIL because the report facade does not exist.

- [ ] **Step 3: Add failing report browser tests**

Assert exactly two tabs, shared Stock Balance behavior, Cut Bundle filters/metrics/table, contained overflow, loading/empty/error states, and absence of unrelated reports.

- [ ] **Step 4: Run browser test and verify RED**

Run: `node scripts/verify_cut_panel_store_workspace.mjs reports`

Expected: FAIL at missing report workspace.

- [ ] **Step 5: Implement the report facade and UI**

Call the existing report execute function through a permission-checked allowlist. Format only display values and aggregate visible quantities in Vue.

- [ ] **Step 6: Verify GREEN**

Run server and browser report tests. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add essdee_yrp/cut_panel_store/report_workspace.py essdee_yrp/test_cut_panel_store_reports.py essdee_yrp/cut_panel_store/web_workspace.py frontend/src/api/cutPanelStore.js frontend/src/departments/cut-panel-store/CutPanelStoreReports.vue frontend/src/departments/cut-panel-store/CutBundleBalanceReport.vue frontend/src/departments/CutPanelStoreSection.vue scripts/verify_cut_panel_store_workspace.mjs
git commit -m "feat: add cut panel store reports"
```

### Task 9: Cross-workspace polish, accessibility, and full verification

**Files:**
- Modify: `frontend/src/styles/enterprise.css`
- Modify: component-scoped styles from Tasks 1-8 as audit findings require.
- Modify: `scripts/verify_cut_panel_store_workspace.mjs`
- Modify: `scripts/verify_theme_portals.mjs`
- Modify: `scripts/audit_web_ui_contract.mjs`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: one complete Cut Panel Store verification suite with `all`, focused suite names, and JSON summary output.

- [ ] **Step 1: Add failing acceptance assertions**

Cover 1600/1280/900/390 widths, popup focus and Escape behavior, sticky actions, 80/20-to-stacked movement layout, no page-level horizontal overflow, theme tokens, popup error use, no native confirmation, card/action contrast, and all six routes.

- [ ] **Step 2: Run acceptance suite and verify RED where gaps remain**

Run: `node scripts/verify_cut_panel_store_workspace.mjs all`

Expected: any remaining visual/interaction gaps fail with named assertions.

- [ ] **Step 3: Apply the smallest shared/component-scoped polish changes**

Keep the Cutting/Fabric visual vocabulary. Do not introduce a Cut Panel Store-only palette or global rules that alter unrelated Desk pages.

- [ ] **Step 4: Run focused backend suite**

Run:

```bash
bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_capabilities
bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_movement
bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_cut_bundle
bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_box_sticker
bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_excel_sticker
bench --site erp-migration-test.localhost run-tests --app essdee_yrp --module essdee_yrp.test_cut_panel_store_reports
```

Expected: all PASS with zero failures/errors.

- [ ] **Step 5: Run frontend and cross-workspace verification**

Run:

```bash
cd frontend && yarn build
cd .. && node scripts/verify_cut_panel_store_workspace.mjs all
node scripts/verify_fabric_store_workspace.mjs all
node scripts/verify_cutting_stock_workflows.mjs
node scripts/verify_cutting_workspace_lists.mjs
node scripts/verify_theme_portals.mjs
node scripts/audit_web_ui_contract.mjs
```

Expected: build exits 0 and every script reports success.

- [ ] **Step 6: Run broad backend regression**

Run: `bench --site erp-migration-test.localhost run-tests --app essdee_yrp`

Expected: zero failures/errors. If a pre-existing unrelated failure appears, record its exact test and prove it is unchanged before proceeding.

- [ ] **Step 7: Inspect and review**

Run `git diff --check`, inspect `git diff --stat` and the full diff, then request an independent whole-branch review focused on permissions, stale writes, stock/bundle ownership, printing rollback, shared-component regressions, and responsive UI. Resolve every Critical or Important finding and rerun affected tests.

- [ ] **Step 8: Commit final integration**

```bash
git add frontend/src/styles/enterprise.css scripts/verify_cut_panel_store_workspace.mjs scripts/verify_theme_portals.mjs scripts/audit_web_ui_contract.mjs
git commit -m "fix: polish cut panel store workspace"
```

- [ ] **Step 9: Final clean-state evidence**

Run `git status --short`, `git log --oneline -10`, and the complete verification commands again after the final review change. Report exact pass counts, any intentionally unchanged limitations, and the commit range.
