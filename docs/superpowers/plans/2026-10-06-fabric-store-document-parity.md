# Fabric Store Document Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver permission-safe `/web` parity for Purchase Orders, Work Orders, Delivery Challans, and Goods Received Notes, with complete DC/GRN workspaces embedded inside WO/PO.

**Architecture:** Keep Frappe controllers, hooks, and existing YRP/Essdee services authoritative. Add focused Fabric Store service modules that project effective metadata, matrices, capabilities, and named commands; render those contracts through reusable Vue workspaces that can run either as a routed page or a maximizable embedded popup.

**Tech Stack:** Frappe 16/Python, Vue 3 Composition API, PrimeVue 4, Vite 5, existing YRP stock item grouping services, Python `unittest`, Playwright verification scripts.

**Spec:** `docs/superpowers/specs/2026-10-06-fabric-store-document-parity-design.md`

## Global Constraints

- Reuse base YRP and `essdee_yrp` controllers, hooks, defaults, and calculation services; never reproduce business calculations in Vue.
- Effective metadata includes base JSON, ERPNext Purchase Order metadata, custom fields, property setters, permissions, and installed stock dimensions.
- Unauthorized actions are absent from the UI and are rejected again by the server.
- DC and GRN use one domain component in both embedded-popup and routed-page modes.
- Embedded DC/GRN work must not navigate away from its parent WO/PO.
- Hidden automation fields remain hidden and source-owned mode flags are not manually editable.
- Every existing-document mutation uses an expected modified timestamp where the underlying service supports mutation.
- Preserve unrelated dirty-worktree changes; stage or commit only exact task files after reviewing their diffs. If a listed file already contains uncommitted user-owned work, do not commit that file until our hunks can be isolated safely.
- Do not remove reduced editors or compatibility endpoints until replacement tests pass.

## Review Focus

- A normal GRN save after Calculate must preserve the selected received-type split, every other received-type split, correction rows, and special-mode rows; Task 9 owns this regression.
- Permission or document-state changes after load must hide actions on reload and reject a forged command; Tasks 1, 3, 5, 7, and 9 cover both halves.
- Changing WO/PO/DC/process/lot/item with unsaved quantities must require confirmation and must apply one authoritative server preview atomically; Tasks 4, 6, 8, and 10 cover this.
- Packing, rework, return, cutting, finishing, and additional-GRN documents must not be normalized into ordinary rows or expose their internal flags; Tasks 7 through 10 cover representative modes and capability projection.
- Embedded and routed DC/GRN must use the same component, preserve state on errors, and refresh the parent after success without navigation; Tasks 2, 8, 10, and 11 cover this.

---

### Task 1: Shared Server Document Contract

**Files:**
- Create: `essdee_yrp/fabric_store/documents/__init__.py`
- Create: `essdee_yrp/fabric_store/documents/common.py`
- Create: `essdee_yrp/test_fabric_store_document_contract.py`
- Modify: `essdee_yrp/fabric_store/web_workspace.py`

**Interfaces:**
- Produces: `get_document_permissions(doctype: str, doc=None) -> dict[str, bool]`, `get_effective_fields(doc, fieldnames: tuple[str, ...]) -> list[dict]`, `get_workspace_base(doc, *, fieldnames, totals=()) -> dict`, `assert_expected_modified(doc, expected_modified: str | None) -> None`, and compatibility re-exports from `web_workspace.py`.
- Produces response keys: `record`, `fields`, `totals`, `permissions`, `capabilities`, `print_formats`.

- [ ] **Step 1: Write contract tests**

Add tests asserting effective custom labels/required/read-only/dependency values are projected only for readable fields; document-state permission flags are exact; unauthorized action capabilities are omitted; a direct forged lifecycle call fails; and stale timestamps raise `frappe.TimestampMismatchError`.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_document_contract`

Expected: FAIL because `fabric_store.documents.common` and its interfaces do not exist.

- [ ] **Step 3: Implement the shared contract and compatibility delegates**

Use `get_permitted_fields`, effective `doc.meta`, `frappe.has_permission`, `get_document_print_formats`, and the existing serializer. Capability dictionaries must contain only authorized actions, not false-valued unauthorized entries.

- [ ] **Step 4: Run focused and legacy Fabric Store server tests**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_document_contract && bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_web_workspace`

Expected: both modules PASS.

- [ ] **Step 5: Review and commit only Task 1 files**

Commit message: `refactor: add fabric document workspace contract`

### Task 2: Reusable Frontend Workspace Shell and Embedded Host

**Files:**
- Create: `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- Create: `frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue`
- Create: `frontend/src/departments/FabricDeliveryChallan.vue`
- Create: `frontend/src/departments/FabricGoodsReceivedNote.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Consumes: Task 1 response keys.
- Produces: shell slots `header`, `fields`, `matrix`, `rail`, `panel`, and `footer`; dialog props `{ doctype, name, sourceContext }`; events `changed(workspace)` and `closed`; routed DC/GRN page wrappers.

- [ ] **Step 1: Add failing browser-contract assertions**

Extend the mocked Playwright suite to assert both DC and GRN routes exist, the embedded host is maximizable, no route change occurs while it is open, unauthorized Submit is absent, and the routed and embedded forms expose the same domain root selector.

- [ ] **Step 2: Run the focused browser suite and verify RED**

Run: `node scripts/verify_fabric_store_workspace.mjs documents`

Expected: FAIL because the routes, shell, and host do not exist.

- [ ] **Step 3: Implement the shell, host, routes, and API transport**

The shell owns sticky identity/actions, loading/error state, totals rail, footer, unsaved-change prompt, and presentation mode. The host maps only supported related doctypes to their domain components and never uses an iframe or Desk route.

- [ ] **Step 4: Run browser contract and frontend build**

Run: `node scripts/verify_fabric_store_workspace.mjs documents && yarn --cwd frontend build`

Expected: browser contract PASS and Vite exits 0.

- [ ] **Step 5: Review and commit only Task 2 files**

Commit message: `feat: add reusable fabric document workspace`

### Task 3: Purchase Order Server Parity

**Files:**
- Create: `essdee_yrp/fabric_store/documents/purchase_order.py`
- Create: `essdee_yrp/test_fabric_store_purchase_order.py`
- Modify: `essdee_yrp/fabric_store/web_workspace.py`

**Interfaces:**
- Consumes: Task 1 common contract.
- Produces: `get_purchase_order_workspace(name: str) -> dict`, `get_purchase_order_editor(name: str | None = None) -> dict`, `save_purchase_order_document(values, *, name=None, submit=False, expected_modified=None) -> dict`, `execute_purchase_order_command(name, command, payload=None, expected_modified=None) -> dict`.
- Commands: `refresh_status`, `close`, `reopen`, `send_approval_request`, `approve`, `reject`, `update_linked_lots`.

- [ ] **Step 1: Write failing PO service tests**

Assert item matrices and effective fields are returned; price/tax totals still come from the controller; approval and linked-lot capabilities follow state and permission; forged approve/submit calls fail; close/reopen call the YRP service; and create-DC/create-GRN capabilities require target create permission.

- [ ] **Step 2: Run the PO module and verify RED**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_purchase_order`

- [ ] **Step 3: Implement the PO service and keep old endpoint names as delegates**

Use `YRPPurchaseOrderMixin`, `get_item_price_for_ui`, `purchase_order_approval`, and `purchase_order_lots`; do not calculate prices or approval state in this module.

- [ ] **Step 4: Run PO, approval, and lot-related tests**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_purchase_order && bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_purchase_order_approval`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 3 files**

Commit message: `feat: expose purchase order parity service`

### Task 4: Purchase Order Page Parity

**Files:**
- Modify: `frontend/src/departments/FabricPurchaseOrder.vue`
- Modify: `frontend/src/departments/FabricPurchaseOrderEditorPage.vue`
- Modify: `frontend/src/departments/fabric-store/PurchaseOrderEditor.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Consumes: Task 3 PO workspace/editor/command contract and Task 2 shell/host.
- Produces: complete PO create/view/edit page and embedded GRN/DC launch events.

- [ ] **Step 1: Add failing PO browser assertions**

Assert permission-based action absence; approval request versus approve/reject visibility; close/reopen; linked-lot editor with required reason; complete field groups and totals; source-changing confirmation when item quantities are dirty; and Create GRN opens the embedded host without URL change.

- [ ] **Step 2: Run PO browser suite and verify RED**

Run: `node scripts/verify_fabric_store_workspace.mjs purchase-order`

- [ ] **Step 3: Implement PO page actions and fields**

Keep the existing `StockItemComposer`; populate it exclusively from server matrices and pricing responses. Replace the reduced `PurchaseOrderGrnEditor` launch with `RelatedDocumentWorkspaceDialog`.

- [ ] **Step 4: Run PO browser suite and build**

Run: `node scripts/verify_fabric_store_workspace.mjs purchase-order && yarn --cwd frontend build`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 4 files**

Commit message: `feat: complete purchase order web workflow`

### Task 5: Work Order Server Parity

**Files:**
- Create: `essdee_yrp/fabric_store/documents/work_order.py`
- Create: `essdee_yrp/test_fabric_store_work_order.py`
- Modify: `essdee_yrp/fabric_store/web_workspace.py`

**Interfaces:**
- Consumes: Task 1 common contract and existing `api.work_order`, `garment_work_order`, `work_order_actions`, and base Work Order functions.
- Produces: `get_work_order_workspace(name: str) -> dict`, `get_work_order_editor(name: str | None = None, source=None) -> dict`, `save_work_order_document(values, *, name=None, submit=False, expected_modified=None) -> dict`, `execute_work_order_command(name, command, payload=None, expected_modified=None) -> dict`.
- Commands include close/request close, debit, rework, calculate garment/fabric, calculate pieces, change item/date, and create/open related workflow context.

- [ ] **Step 1: Write failing WO service tests**

Assert effective header fields and dynamic dimensions; selection context; separate quantity/pending matrix values; calculated editor rows; permission-filtered action context; close/debit/rework payloads; stale calculation rejection; and no create-related capability without target permission.

- [ ] **Step 2: Run the WO module and verify RED**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_work_order`

- [ ] **Step 3: Implement WO service coordination**

Return existing garment/fabric calculation contexts unchanged under named capabilities. Saving must pass grouped deliverables/receivables through the Work Order controller rather than editing calculated rows directly.

- [ ] **Step 4: Run WO domain and existing garment tests**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_work_order && bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_garment_work_order`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 5 files**

Commit message: `feat: expose work order parity service`

### Task 6: Work Order Page and Action Panels

**Files:**
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Create: `frontend/src/departments/FabricWorkOrderEditorPage.vue`
- Create: `frontend/src/departments/fabric-store/WorkOrderEditor.vue`
- Modify: `frontend/src/departments/fabric-store/WorkOrderDetails.vue`
- Modify: `frontend/src/departments/fabric-store/WorkOrderItemMatrix.vue`
- Create: `frontend/src/departments/fabric-store/WorkOrderActionPanel.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `frontend/src/router/index.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Consumes: Task 5 WO contract and Task 2 embedded host.
- Produces: complete WO page with focused calculation/close/rework/change panels and embedded DC/GRN workspaces.

- [ ] **Step 1: Add failing WO browser assertions**

Assert WO new/edit/detail routes; Process/Item/Lot appear once; Pending is a separate matrix column from Quantity; calculation actions follow server capabilities; focused action panels preserve unsaved values on errors; dirty source changes confirm; and related DC/GRN open without navigation.

- [ ] **Step 2: Run WO browser suite and verify RED**

Run: `node scripts/verify_fabric_store_workspace.mjs work-order`

- [ ] **Step 3: Implement WO editor/action panels and replace related-document reduced editors**

Use one `WorkOrderActionPanel` with explicit action modes rather than duplicating dialogs. Add the new/edit route wrappers around `WorkOrderEditor`. The related activity rail opens Task 2's host for create, view, edit, amend, and return results.

- [ ] **Step 4: Run WO browser suite and build**

Run: `node scripts/verify_fabric_store_workspace.mjs work-order && yarn --cwd frontend build`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 6 files**

Commit message: `feat: complete work order web workflow`

### Task 7: Delivery Challan Server Parity

**Files:**
- Create: `essdee_yrp/fabric_store/documents/delivery_challan.py`
- Create: `essdee_yrp/test_fabric_store_delivery_challan.py`
- Modify: `essdee_yrp/fabric_store/web_workspace.py`

**Interfaces:**
- Consumes: Task 1 common contract, YRP DC defaults/return/completion services, and Essdee return hooks.
- Produces: `get_delivery_challan_workspace(name=None, source=None) -> dict`, `preview_delivery_challan_source(work_order, values=None) -> dict`, `save_delivery_challan(values, *, name=None, submit=False, expected_modified=None) -> dict`, `execute_delivery_challan_command(name, command, payload=None, expected_modified=None) -> dict`.
- Commands: `return`, `complete_transfer`, `submit`, `cancel`, `amend`, and notification-context preparation.

- [ ] **Step 1: Write failing DC tests**

Assert base and custom fields; authoritative normal/correction matrices; server totals; stable row merge; stock checks delegated to the controller; return variants; transfer capability; forged return/transfer rejection; and representative cutting/packing modes retain prepared hidden fields and rows.

- [ ] **Step 2: Run the DC module and verify RED**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_delivery_challan`

- [ ] **Step 3: Implement the DC service and compatibility delegates**

Derive ordinary rows from `get_delivery_challan_defaults`; for existing and source-owned special documents, start from the saved document and merge only editable quantities/headers.

- [ ] **Step 4: Run DC and existing return/transfer tests**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_delivery_challan && bench --site erp-migration-test.site run-tests --app yrp --module yrp.yrp.doctype.yrp_delivery_challan.test_yrp_delivery_challan_return && bench --site erp-migration-test.site run-tests --app yrp --module yrp.yrp.doctype.yrp_delivery_challan.test_internal_unit_transfer`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 7 files**

Commit message: `feat: expose delivery challan parity service`

### Task 8: Complete Delivery Challan Workspace

**Files:**
- Create: `frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue`
- Create: `frontend/src/departments/fabric-store/DeliveryChallanReturnPanel.vue`
- Modify: `frontend/src/departments/FabricDeliveryChallan.vue`
- Modify: `frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Modify: `frontend/src/departments/FabricPurchaseOrder.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Consumes: Task 7 DC contract and Task 2 shell.
- Produces: `.delivery-challan-workspace` in page and embedded modes; emits `changed(workspace)` after every mutation.

- [ ] **Step 1: Add failing DC browser assertions**

Assert editable headers and both matrices; highlighted delivered quantity/stock value; save/submit permission absence; error-state value preservation; source-change confirmation; return internal panel; Complete Transfer after submit; special-mode read-only context; same root component in route/popup; and parent refresh after success.

- [ ] **Step 2: Run DC browser suite and verify RED**

Run: `node scripts/verify_fabric_store_workspace.mjs delivery-challan`

- [ ] **Step 3: Implement the complete DC workspace and replace old DC editor usage**

Reuse `WorkOrderItemMatrix` or extract only its generic matrix body; do not maintain a second data model. Keep submitted documents open read-only after submit.

- [ ] **Step 4: Run DC browser suite and build**

Run: `node scripts/verify_fabric_store_workspace.mjs delivery-challan && yarn --cwd frontend build`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 8 files**

Commit message: `feat: add complete delivery challan workspace`

### Task 9: GRN Server Parity and Calculate Preservation

**Files:**
- Create: `essdee_yrp/fabric_store/documents/goods_received_note.py`
- Create: `essdee_yrp/test_fabric_store_goods_received_note.py`
- Modify: `essdee_yrp/fabric_store/web_workspace.py`

**Interfaces:**
- Consumes: Task 1 contract, base WO/PO defaults and completion, `garment_grn.get_grn_calculation_context`, `garment_grn.calculate_grn_receivables`, Inspection Entry initial payload, and Essdee GRN override behavior.
- Produces: `get_goods_received_note_workspace(name=None, source=None) -> dict`, `preview_goods_received_note_source(source) -> dict`, `save_goods_received_note(values, *, name=None, submit=False, expected_modified=None) -> dict`, `get_goods_received_note_calculation(name) -> dict`, `calculate_goods_received_note(name, rows, received_type, expected_modified) -> dict`, `save_goods_received_note_inspection(name, values, *, inspection_name=None, submit=False, expected_modified=None) -> dict`, `execute_goods_received_note_command(name, command, payload=None, expected_modified=None) -> dict`.

- [ ] **Step 1: Write failing GRN regression tests**

Cover WO and PO defaults; Calculate eligibility; selected received-type replacement; preservation of other received types, correction rows, and prepared special rows after ordinary save; stale calculate rejection; excess/freight/valuation delegation; inspection initial payload plus save/submit and existing-entry view capability; transfer; lifecycle; and forged command rejection.

- [ ] **Step 2: Run the GRN module and verify RED**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_goods_received_note`

- [ ] **Step 3: Implement saved-document-first GRN merging and named commands**

Identify rows by authoritative references plus item variant, stable row index, received type, delivery-challan item, correction reference, dimensions, and set combination. New ordinary documents may derive pending rows; existing documents must never be rebuilt solely from fresh defaults.

- [ ] **Step 4: Run GRN customization and base GRN suites**

Run: `bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_goods_received_note && bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_goods_received_note_customization && bench --site erp-migration-test.site run-tests --app yrp --module yrp.yrp.doctype.yrp_goods_received_note.test_purchase_order_grn`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 9 files**

Commit message: `feat: expose safe goods receipt parity service`

### Task 10: Complete GRN Workspace and Calculate Panel

**Files:**
- Create: `frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue`
- Create: `frontend/src/departments/fabric-store/GrnCalculatePanel.vue`
- Create: `frontend/src/departments/fabric-store/InspectionEntryPanel.vue`
- Modify: `frontend/src/departments/FabricGoodsReceivedNote.vue`
- Modify: `frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Modify: `frontend/src/departments/FabricPurchaseOrder.vue`
- Modify: `frontend/src/api/fabricStore.js`
- Modify: `scripts/verify_fabric_store_workspace.mjs`

**Interfaces:**
- Consumes: Task 9 GRN contract and Task 2 shell.
- Produces: `.goods-received-note-workspace`, internal Calculate and Inspection panels, and `changed(workspace)`.

- [ ] **Step 1: Add failing GRN browser assertions**

Assert WO/PO modes; saved-draft-only Calculate; Received Type and availability matrix; selection and row/column/grand totals; preservation after Calculate/reload/save; highlighted received quantity/value; corrections; inspection/transfer actions; permission absence; source-change confirmation; error-state preservation; special-mode display; same route/popup component; and parent refresh without navigation.

- [ ] **Step 2: Run GRN browser suite and verify RED**

Run: `node scripts/verify_fabric_store_workspace.mjs goods-received-note`

- [ ] **Step 3: Implement GRN workspace and internal panels**

Keep Calculate inside the open GRN workspace. After save, calculate, submit, transfer, or inspection creation, replace local state with the returned authoritative workspace and keep the host open.

- [ ] **Step 4: Run GRN browser suite and build**

Run: `node scripts/verify_fabric_store_workspace.mjs goods-received-note && yarn --cwd frontend build`

Expected: PASS.

- [ ] **Step 5: Review and commit only Task 10 files**

Commit message: `feat: add complete goods receipt workspace`

### Task 11: Notification Actions, Compatibility Cleanup, and Full Parity Gate

**Files:**
- Modify: `essdee_yrp/fabric_store/documents/purchase_order.py`
- Modify: `essdee_yrp/fabric_store/documents/delivery_challan.py`
- Modify: `essdee_yrp/fabric_store/documents/goods_received_note.py`
- Modify: `frontend/src/departments/FabricPurchaseOrder.vue`
- Modify: `frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue`
- Modify: `frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue`
- Modify: `frontend/src/departments/FabricWorkOrder.vue`
- Delete after parity passes: `frontend/src/departments/fabric-store/WorkOrderTransactionEditor.vue`
- Delete after parity passes: `frontend/src/departments/fabric-store/PurchaseOrderGrnEditor.vue`
- Modify: `scripts/verify_fabric_store_workspace.mjs`
- Create: `docs/fabric-store-document-parity.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: audited mapping from each applicable base/Essdee JS action to server capability, Vue surface, and automated test; no runtime imports of reduced editors.

- [ ] **Step 1: Add final parity and compatibility assertions**

Assert SMS/WhatsApp capabilities follow supplier/status/permission rules and reuse existing notification endpoints; every audited JS action has a mapping; old reduced components are not imported; unauthorized buttons are absent; embedded actions do not navigate; and all four direct routes remain functional.

- [ ] **Step 2: Run the all-documents browser suite and verify RED for remaining gaps**

Run: `node scripts/verify_fabric_store_workspace.mjs all`

- [ ] **Step 3: Complete notification adapters, remove obsolete imports/endpoints, and write the parity inventory**

Delete the old reduced Vue components only after the browser suite no longer imports them. Keep server endpoint delegates only where another checked-in caller still uses them; document each retained compatibility route.

- [ ] **Step 4: Run complete verification**

Run:

```bash
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_document_contract
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_purchase_order
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_work_order
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_delivery_challan
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_store_goods_received_note
bench --site erp-migration-test.site run-tests --app essdee_yrp --module essdee_yrp.test_goods_received_note_customization
node scripts/verify_fabric_store_workspace.mjs all
yarn --cwd frontend build
```

Expected: every command exits 0; browser assertions report no overflow or text below 11px at 1600, 1280, 900, and 390 widths.

- [ ] **Step 5: Inspect the final diff against the spec and dirty-worktree baseline**

Confirm no unrelated files were staged, all retained compatibility endpoints have live callers, and the acceptance checklist in the parity inventory is complete.

- [ ] **Step 6: Commit only reviewed Task 11 files**

Commit message: `feat: complete fabric store document parity`
