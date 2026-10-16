#!/usr/bin/env node

import { readFileSync } from "node:fs"

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const assert = (condition, message) => {
	if (!condition) throw new Error(message)
}

const enterprise = read("../frontend/src/styles/enterprise.css")
const formView = read("../frontend/src/components/common/FormView.vue")
const listView = read("../frontend/src/components/common/ListView.vue")
const linkField = read("../frontend/src/components/common/LinkField.vue")
const launcher = read("../frontend/src/components/common/WorkspaceLauncher.vue")
const documentWorkspace = read("../frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue")
const purchaseOrder = read("../frontend/src/departments/FabricPurchaseOrder.vue")
const deliveryChallan = read("../frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue")
const goodsReceivedNote = read("../frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue")
const departmentCard = read("../frontend/src/components/DepartmentCard.vue")
const departmentPage = read("../frontend/src/components/DepartmentPage.vue")
const departmentRegistry = read("../frontend/src/departments/registry.js")
const mainStyles = read("../frontend/src/styles/main.css")
const workOrderEditor = read("../frontend/src/departments/fabric-store/WorkOrderEditor.vue")
const purchaseOrderEditor = read("../frontend/src/departments/fabric-store/PurchaseOrderEditor.vue")
const documentTransactionDialog = read("../frontend/src/components/documents/DocumentTransactionDialog.vue")
const cuttingOrderEditor = read("../frontend/src/departments/cutting/order/CuttingOrderEditor.vue")
const cuttingOrderDetailDialog = read("../frontend/src/departments/cutting/order/CuttingOrderDetailDialog.vue")
const cuttingOrderActions = read("../frontend/src/departments/cutting/order/CuttingOrderActions.vue")
const cuttingPlanActions = read("../frontend/src/departments/cutting/CuttingPlanActions.vue")
const cuttingPlanEditor = read("../frontend/src/departments/cutting/plan/CuttingPlanEditor.vue")
const workOrderActionPanel = read("../frontend/src/departments/fabric-store/WorkOrderActionPanel.vue")
const movementDialog = read("../frontend/src/departments/cut-panel-store/CutPanelMovementDialog.vue")
const movementRail = read("../frontend/src/departments/cut-panel-store/CutPanelMovementRail.vue")
const cutBundleDialog = read("../frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue")
const boxStickerDialog = read("../frontend/src/departments/cut-panel-store/BoxStickerPrintDialog.vue")
const excelStickerDialog = read("../frontend/src/departments/cut-panel-store/ExcelStickerPrintDialog.vue")
const cuttingReports = read("../frontend/src/departments/CuttingReports.vue")
const cutPanelStoreReports = read("../frontend/src/departments/cut-panel-store/CutPanelStoreReports.vue")
const purchaseOrderDialog = read("../frontend/src/departments/fabric-store/PurchaseOrderDialog.vue")
const stockOperationDialog = read("../frontend/src/departments/fabric-store/FabricStockOperationDialog.vue")
const deliveryChallanReturnDialog = read("../frontend/src/departments/fabric-store/DeliveryChallanReturnDialog.vue")
const deliveryChallanReturnPanel = read("../frontend/src/departments/fabric-store/DeliveryChallanReturnPanel.vue")
const cutPanelMovementEditor = read("../frontend/src/departments/cutting/CutPanelMovementEditor.vue")
const documentSaveButton = read("../frontend/src/components/documents/DocumentSaveButton.vue")
const documentErrorDialog = read("../frontend/src/components/documents/DocumentErrorDialog.vue")
const childTableField = read("../frontend/src/components/common/ChildTableField.vue")
const cuttingOrderPage = read("../frontend/src/departments/CuttingOrder.vue")
const cuttingBulkLaySheet = read("../frontend/src/departments/CuttingBulkLaySheet.vue")
const plannerPlanWorkspace = read("../frontend/src/departments/cutting/planner/PlannerPlanWorkspace.vue")
const plannerStrategies = read("../frontend/src/departments/cutting/planner/PlannerStrategies.vue")
const plannerLayPlan = read("../frontend/src/departments/cutting/planner/PlannerLayPlan.vue")
const workspaceLoadError = read("../frontend/src/components/common/WorkspaceLoadError.vue")
const cuttingLauncher = read("../frontend/src/departments/Cutting.vue")
const fabricLauncher = read("../frontend/src/departments/FabricStore.vue")
const cutPanelLauncher = read("../frontend/src/departments/CutPanelStore.vue")
const cuttingPlans = read("../frontend/src/departments/CuttingPlans.vue")
const cuttingOrders = read("../frontend/src/departments/CuttingOrders.vue")
const cuttingLaySheetPlanners = read("../frontend/src/departments/CuttingLaySheetPlanners.vue")
const cuttingBulkLaySheets = read("../frontend/src/departments/CuttingBulkLaySheets.vue")
const fabricSection = read("../frontend/src/departments/FabricStoreSection.vue")
const cutPanelSection = read("../frontend/src/departments/CutPanelStoreSection.vue")
const stockBalanceReport = read("../frontend/src/components/reports/StockBalanceReport.vue")
const reportShell = read("../frontend/src/components/reports/ReportShell.vue")
const fabricReports = read("../frontend/src/departments/fabric-store/FabricReports.vue")
const grnCalculatePanel = read("../frontend/src/departments/fabric-store/GrnCalculatePanel.vue")
const documentStatusBadge = read("../frontend/src/components/documents/DocumentStatusBadge.vue")
const cuttingMarkerDialog = read("../frontend/src/departments/cutting/CuttingMarkerDialog.vue")
const cuttingLaySheetDialog = read("../frontend/src/departments/cutting/CuttingLaySheetDialog.vue")
const bulkDeliveryDialog = read("../frontend/src/departments/cutting/bulk/BulkDeliveryDialog.vue")
const bulkPrintDialog = read("../frontend/src/departments/cutting/bulk/BulkPrintDialog.vue")
const cuttingPlanPage = read("../frontend/src/departments/CuttingPlan.vue")
const fabricWorkOrderPage = read("../frontend/src/departments/FabricWorkOrder.vue")
const fabricPurchaseOrderPage = read("../frontend/src/departments/FabricPurchaseOrder.vue")
const fabricWorkOrders = read("../frontend/src/departments/fabric-store/FabricWorkOrders.vue")
const fabricPurchaseOrders = read("../frontend/src/departments/fabric-store/FabricPurchaseOrders.vue")
const fabricStockTransfers = read("../frontend/src/departments/fabric-store/FabricStockTransfers.vue")
const documentActionStrip = read("../frontend/src/components/documents/DocumentActionStrip.vue")
const workOrderDetails = read("../frontend/src/departments/fabric-store/WorkOrderDetails.vue")
const bulkSetupEditor = read("../frontend/src/departments/cutting/bulk/BulkSetupEditor.vue")
const bulkActiveLaySheet = read("../frontend/src/departments/cutting/bulk/BulkActiveLaySheet.vue")
const cpmMovementDialog = read("../frontend/src/departments/cutting/CpmMovementDialog.vue")
const cpmTransactionDialog = read("../frontend/src/departments/cutting/CpmTransactionDialog.vue")
const cuttingPlanCpm = read("../frontend/src/departments/cutting/CuttingPlanCpm.vue")
const cuttingPlanStockTransfers = read("../frontend/src/departments/cutting/CuttingPlanStockTransfers.vue")
const purchaseOrderWorkspaceDialog = read("../frontend/src/departments/fabric-store/PurchaseOrderDialog.vue")
const workOrderActivityRail = read("../frontend/src/departments/fabric-store/WorkOrderActivityRail.vue")
const cuttingLaySheetPlanner = read("../frontend/src/departments/CuttingLaySheetPlanner.vue")
const cuttingLaySheetPlannerEditorPage = read("../frontend/src/departments/CuttingLaySheetPlannerEditorPage.vue")
const bulkWorkflowRail = read("../frontend/src/departments/cutting/bulk/BulkWorkflowRail.vue")
const cuttingPlanSidebar = read("../frontend/src/departments/cutting/CuttingPlanSidebar.vue")
const plannerOrderMatrix = read("../frontend/src/departments/cutting/planner/PlannerOrderMatrix.vue")
const plannerDeviationTable = read("../frontend/src/departments/cutting/planner/PlannerDeviationTable.vue")
const cuttingCompletedReport = read("../frontend/src/departments/cutting/CuttingCompletedReport.vue")
const workOrderItemMatrix = read("../frontend/src/departments/fabric-store/WorkOrderItemMatrix.vue")
const workOrderDeliveryMatrix = read("../frontend/src/departments/cutting/WorkOrderDeliveryMatrix.vue")
const cuttingOrderTabs = read("../frontend/src/departments/cutting/order/CuttingOrderTabs.vue")
const dailyProductionReport = read("../frontend/src/departments/cutting/reports/DailyProductionReport.vue")
const cuttingQuantityMatrix = read("../frontend/src/departments/cutting/shared/CuttingQuantityMatrix.vue")
const stockItemComposer = read("../frontend/src/components/stock/StockItemComposer.vue")
const listviewFilters = read("../frontend/src/components/common/ListviewFilters.vue")
const workspacePlaceholder = read("../frontend/src/components/common/WorkspacePlaceholder.vue")
const unfinishedDepartmentPages = ["AccessoryStore", "Finishing", "Merch", "Purchase", "Sales", "Planning"]
	.map((name) => [name, read(`../frontend/src/departments/${name}.vue`)])

assert(enterprise.includes("--erp-shell-header-height: 56px"), "Compact shell header token is missing")
assert(enterprise.includes("--erp-font-size-label: 12px"), "Shared label-size token is missing")
assert(enterprise.includes("--erp-font-size-table: 13px"), "Shared table-size token is missing")
assert(enterprise.includes("--erp-table-cell-pad-y: 8px"), "Shared table density token is missing")
assert(enterprise.includes("--erp-dialog-width-md:"), "Shared dialog width scale is missing")
assert(enterprise.includes("@media (max-width: 420px)") && enterprise.includes("clip: rect(0 0 0 0)"), "Narrow editor actions still crowd out document titles")
assert(enterprise.includes("@media (max-width: 340px)") && enterprise.includes("-webkit-line-clamp: 2"), "Small-phone editor titles remain truncated instead of wrapping compactly")
assert(enterprise.includes(".p-dialog-mask") && enterprise.includes("backdrop-filter: blur(3px)"), "Dialogs do not use the shared focused backdrop")
assert(enterprise.includes("scrollbar-width: thin"), "App-owned scroll regions do not use a compact scrollbar")
assert(enterprise.includes("::-webkit-scrollbar-thumb"), "Chromium scroll regions do not use the shared scrollbar treatment")
assert(enterprise.includes("--erp-control-height-compact: 44px") && enterprise.includes("--erp-control-height: 44px"), "Touch layouts do not raise shared controls to a 44px target")
assert(documentStatusBadge.includes("document-status-badge--warning") && documentStatusBadge.includes("document-status-badge--danger"), "Document statuses do not share a consistent semantic badge")
assert(documentStatusBadge.includes("document-status-badge--info"), "Active document statuses have no shared informational tone")
for (const [label, source] of [
	["Cutting Plan list", cuttingPlans],
	["Cutting Order list", cuttingOrders],
	["Bulk LaySheet list", cuttingBulkLaySheets],
	["LaySheet Planner list", cuttingLaySheetPlanners],
	["Fabric Work Order list", fabricWorkOrders],
	["Fabric Purchase Order list", fabricPurchaseOrders],
	["Cutting Order header", cuttingOrderPage],
	["Fabric document shell", documentWorkspace],
]) assert(source.includes("<DocumentStatusBadge"), `${label} bypasses the shared status semantics`)
for (const source of [
	movementDialog, cutBundleDialog, boxStickerDialog, excelStickerDialog, movementRail,
	cuttingMarkerDialog, cpmMovementDialog, cpmTransactionDialog, cuttingPlanCpm,
	cuttingPlanStockTransfers, purchaseOrderWorkspaceDialog, workOrderActivityRail,
	documentTransactionDialog, cuttingBulkLaySheet, bulkActiveLaySheet,
]) {
	assert(source.includes("<DocumentStatusBadge"), "A Cut Panel document surface bypasses the shared status badge")
}

assert(listView.includes("<h1>{{ title || doctype }}</h1>"), "List pages do not expose a semantic primary heading")
assert(!listView.includes('class="list-status-tabs" aria-label="Status filters" tabindex="0"'), "Status rail is still a redundant keyboard stop")
assert(!listView.includes('class="list-document-cell__mark"'), "List document IDs still carry decorative acronym blocks")
assert(!listView.includes(".p-datatable-tbody > tr:nth-child(even)"), "List tables still use noisy zebra striping")
assert(listView.includes("hasActiveQuery ? 'Try changing the search or filters.' : `No ${title || doctype} records are available yet.`"), "List empty states do not distinguish an empty dataset from filtered-out results")
assert(listView.includes('new Set([effectiveStatusField.value, "docstatus", "status", "workflow_state"]'), "Mobile list summaries can hide the effective document status")
assert(listView.includes('return isSubmittable.value ? "docstatus" : ""'), "Submittable list views do not infer Draft, Submitted and Cancelled status tabs")
assert(listView.includes("padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x)"), "List rows do not use the shared compact table-density tokens")
assert(listView.includes("background: transparent;\n\tborder: 0;\n\tborder-radius: 0;\n\tbox-shadow: none;"), "List pages still wrap their table in a second raised card")
assert(listView.includes("overflow-y: visible;"), "Mobile list pages still create a nested vertical scrollbar")
assert(listView.includes("overflow-x: auto;\n\t\toverflow-y: visible;"), "Mobile list tables do not preserve horizontal scrolling while yielding vertical scrolling to the page")
assert(listView.includes('class="mobile-list-records"'), "Mobile record lists still depend on wide desktop tables")
assert(listView.includes('<slot :name="`cell-${column.fieldname}`"'), "Mobile record cards bypass custom cell renderers")
assert(listView.includes('class="mobile-list-record__open"'), "Mobile records have no explicit accessible open action")
assert(listView.includes("mobile-list-record__header--without-selection"), "Mobile records without bulk selection use the wrong header grid")
assert(listView.includes(".common-list-view--viewport-bounded :deep(.premium-list-table),\n\t:global(.premium-list-table) {\n\t\tdisplay: none;"), "Desktop tables are not replaced by compact record cards on mobile")
assert(listView.includes('class="list-status-select"') && listView.includes("statusSelectOptions"), "Long status rails have no compact Select alternative")
assert(listView.includes(':placeholder="statusSelectOptions[0]?.label || \'All statuses\'"'), "The compact status selector renders a blank default state")
assert(!listView.includes("list-status-tabs--many") && !listView.includes("list-status-select--many"), "Long desktop status rails still collapse into a dropdown")
assert(listView.includes("min-height: 44px"), "Mobile list controls do not meet the shared touch target")
assert(listView.includes("@media (max-width: 1024px)"), "Tablet-width list views still expose clipped desktop tables")
assert(listView.includes('class="list-load-error"'), "List load failures do not have a dedicated recovery state")
assert(listView.includes('@click="retryLoad"'), "List load failures have no contextual retry action")
assert(listView.includes("metadataReady.value ? refresh() : initialise()"), "Row-load retry resets the user's existing query state")
assert(listView.includes('<div v-if="!error" class="list-table-frame">'), "List load failures still render a misleading empty data region")
assert(listView.includes('class="erp-dialog--md"'), "List configuration dialogs do not use the shared dialog scale")
assert(listView.includes('class="erp-dialog--sm"'), "List confirmation dialogs do not use the shared compact dialog scale")
assert(fabricStockTransfers.includes("viewport-bounded"), "Fabric Stock Transfers can render desktop and mobile list states together")
assert(!fabricStockTransfers.includes("@media (max-width: 520px) {\n\t.stock-operation-grid { grid-template-columns: 1fr; }"), "Fabric Stock Transfers stacks all operation choices into an oversized phone rail")
assert(fabricStockTransfers.includes("grid-template-rows: auto minmax(0, 1fr)") && fabricStockTransfers.includes(":deep(.common-list-view--viewport-bounded) { height: 100%; }"), "Fabric Stock Transfers does not reserve viewport space for its operation selector")
assert(listView.includes(".p-datatable-empty-message") && listView.includes("box-shadow: none"), "Desktop empty rows still inherit interactive hover styling")
assert(listviewFilters.includes("reset-filter-on-hide"), "Field searches can leave the selected filter looking blank after dismissal")
assert(!listviewFilters.includes("fieldControlRevision"), "Filter field controls remount after closing and lose keyboard focus")

const labelPosition = formView.indexOf('<span class="view-field__label">')
const valuePosition = formView.indexOf('class="view-field__value')
assert(labelPosition >= 0 && valuePosition >= 0 && labelPosition < valuePosition, "Read fields are not label-first")
assert(formView.includes("grid-template-columns: repeat(4, minmax(0, 1fr))"), "Read view does not use the compact four-column desktop grid")
assert(formView.includes("grid-auto-flow: dense"), "Read view leaves avoidable gaps around wide fields")
assert(formView.includes("min-height: 54px"), "Read fields have not been compacted")
assert(formView.includes("view-field--wide"), "Long read-only fields are not protected from the four-column grid")
assert(!formView.includes("show-gridlines\n\t\t\t\t\t\t\tstriped-rows"), "Read-only child tables still use noisy stripes and gridlines")
assert(!childTableField.includes("show-gridlines\n\t\t\tstriped-rows"), "Editable child tables still use noisy stripes and gridlines")
assert(childTableField.includes('isDisabled ? "No rows." : "No rows added"'), "Read-only child tables lack a neutral empty state")
assert(childTableField.includes('<span v-if="!isDisabled">Use Add Row to create the first line.</span>'), "Add Row guidance is not limited to editable child tables")
assert(formView.includes("'aria-label': `${table.label || table.fieldname} rows`"), "Read-only child tables are not keyboard-focusable named regions")
assert(stockBalanceReport.includes('role="region" aria-label="Stock Balance results" tabindex="0"'), "Stock Balance results are not a keyboard-focusable named region")
assert(reportShell.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"), "Mobile report filters do not use a compact two-column layout")
assert(reportShell.includes("@media (max-width: 360px)") && reportShell.includes("grid-template-columns: minmax(0, 1fr)"), "Narrow report filters do not fall back to one readable column")
assert(reportShell.includes("report-shell__commands--with-copy") && reportShell.includes("grid-column: 1 / -1"), "Narrow copyable reports do not preserve a full-width primary command")
assert(reportShell.includes("min-height: 44px"), "Narrow report commands do not preserve touch targets while reflowing")
assert(stockBalanceReport.includes("grid-column: 1 / -1") && stockBalanceReport.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"), "Stock Balance checks do not fit as a full-width two-column mobile group")
assert(stockOperationDialog.includes(".fabric-stock-footer > div { display: grid; grid-template-columns: 1fr; }") && stockOperationDialog.includes(":deep(.document-save-button) { width: 100%; }"), "Stock Operation mobile footer leaves an unbalanced half-width action row")

assert(!linkField.includes('searchError || "No matches"'), "LinkField still shows an unconditional No matches message")
assert(linkField.includes("emptyStateMessage"), "LinkField has no contextual empty state")

assert(launcher.includes("min-height: 124px"), "Workspace launcher cards are still oversized")
assert(launcher.includes("width: 44px"), "Workspace launcher icons are still oversized")
assert(launcher.includes("@media (hover: hover)"), "Launcher lift effects are not guarded for hover-capable devices")
assert(launcher.includes("max-width: 1320px"), "Department launcher content does not align with the shared flat-page gutter")
assert(launcher.includes("min-height: 104px"), "Mobile workspace cards still create excessive page scrolling")
assert(launcher.includes("-webkit-line-clamp: 2"), "Mobile workspace descriptions are not kept compact")
assert(launcher.includes("min-height: 69px") && launcher.includes("min-height: 0"), "Workspace launcher titles do not share a stable desktop baseline with a compact mobile override")
assert(workspacePlaceholder.includes('class="workspace-placeholder"') && workspacePlaceholder.includes('aria-live="polite"'), "Unconfigured departments have no intentional accessible empty workspace")
assert(workspacePlaceholder.includes("max-width: 680px") && workspacePlaceholder.includes("min-height: min(420px"), "Department placeholders do not replace the oversized dead canvas with a focused premium state")
for (const [label, source] of unfinishedDepartmentPages) {
	assert(source.includes("<WorkspacePlaceholder") && source.includes(":show-title=\"false\" flat full-width"), `${label} still renders as an oversized blank page`)
}
assert(workspaceLoadError.includes('role="alert"'), "Workspace load failures are not announced accessibly")
assert(workspaceLoadError.includes('@click="$emit(\'retry\')"'), "Workspace load failures do not expose a retry action")
assert(workspaceLoadError.includes('v-if="retryable"'), "Non-recoverable workspace states cannot hide the Retry action")
assert(cuttingPlanPage.includes('<WorkspaceLoadError title="Cutting Plan unavailable"'), "Cutting Plan initial workspace failures have no single recovery state")
assert(cuttingPlanPage.includes(':error="\'\'"') && cuttingPlanPage.includes('workspaceReady.value = true'), "Cutting Plan still duplicates workspace errors across child surfaces")
assert(cuttingPlanPage.includes('@saved="documentSaved"') && cuttingPlanPage.includes('suppressNextLoaded') && cuttingPlanPage.includes('remountsFormAfterSuccess'), "Cutting Plan retry can launch a duplicate workspace request when FormView remounts")
assert(cuttingPlanPage.includes('class="cutting-plan-workspace-error"') && cuttingPlanPage.includes('@click="retryWorkspace"'), "Ready Cutting Plan failures have no local Retry action")
assert(cuttingPlanPage.includes(':loading="workspaceLoading" @retry="retryWorkspace"'), "Cutting Plan initial retry can be submitted repeatedly while loading")
assert(cuttingPlanPage.includes("let probeSequence = 0") && cuttingPlanPage.includes("requestedId !== cuttingPlanId.value"), "Cutting Plan editor probes can overwrite a newly navigated record")
assert(cuttingOrderPage.includes("let initialiseSequence = 0") && cuttingOrderPage.includes("requestedId !== cuttingOrderId.value"), "Cutting Order route changes can retain a stale editor or workspace")
assert(cuttingOrderPage.includes('@retry="initialise"'), "Cutting Order initial-load retry does not repeat the editor capability probe")
assert(cuttingOrderPage.includes("workspace.value = {}") && cuttingOrderPage.includes("editorProbe.value = null"), "Cutting Order route changes do not clear the previous document immediately")
assert(fabricWorkOrderPage.includes('workspace.value = {}') && fabricWorkOrderPage.includes('loadSequence'), "Work Order route changes can retain stale document data")
assert(fabricPurchaseOrderPage.includes('workspace.value = {}') && fabricPurchaseOrderPage.includes('loadSequence'), "Purchase Order route changes can retain stale document data")
assert(fabricWorkOrderPage.includes('let actionSequence = 0') && fabricWorkOrderPage.includes('requestedId !== String(route.params.workOrderId'), "Work Order actions can overwrite a newly navigated record")
assert(fabricPurchaseOrderPage.includes('let actionSequence = 0') && fabricPurchaseOrderPage.includes('requestedId !== String(route.params.purchaseOrderId'), "Purchase Order actions can overwrite a newly navigated record")
assert(fabricWorkOrderPage.includes('relatedVisible.value = false') && fabricWorkOrderPage.includes('materialIssueVisible.value = false') && fabricWorkOrderPage.includes('grnSourceVisible.value = false'), "Work Order route changes preserve dialogs from the previous record")
assert(fabricPurchaseOrderPage.includes('lotEditorVisible.value = false') && fabricPurchaseOrderPage.includes('rejectVisible.value = false') && fabricPurchaseOrderPage.includes('deliverySourceVisible.value = false'), "Purchase Order route changes preserve dialogs from the previous record")
assert(deliveryChallan.includes("let loadSequence = 0") && deliveryChallan.includes("requestedName !== props.name"), "Delivery Challan loads can overwrite a newly navigated document")
assert(goodsReceivedNote.includes("let loadSequence = 0") && goodsReceivedNote.includes("requestedName !== props.name"), "Goods Received Note loads can overwrite a newly navigated document")
assert(deliveryChallan.includes("let actionSequence = 0") && deliveryChallan.includes("requestedRouteName !== props.name"), "Delivery Challan actions can overwrite a newly navigated document")
assert(goodsReceivedNote.includes("let actionSequence = 0") && goodsReceivedNote.includes("requestedRouteName !== props.name"), "Goods Received Note actions can overwrite a newly navigated document")
assert(movementDialog.includes("let loadSequence = 0") && movementDialog.includes("requestedMovement !== props.movement"), "Cut Panel Movement dialog loads can overwrite a newly opened document")
assert(cutBundleDialog.includes("let loadSequence = 0") && cutBundleDialog.includes("requestedDocumentName !== props.documentName"), "Cut Bundle Edit dialog loads can overwrite a newly opened document")
assert(cpmMovementDialog.includes("let loadSequence = 0") && cpmMovementDialog.includes("requestedMovement !== props.movement"), "Cutting Plan movement dialog loads can overwrite a newly opened document")
assert(movementDialog.includes("let actionSequence = 0") && movementDialog.includes("actionIsStale"), "Cut Panel Movement actions can overwrite a newly opened document")
assert(movementDialog.includes(':closable="!busy"') && movementDialog.includes(':close-on-escape="!busy"'), "Cut Panel Movement can be closed while a mutation is active")
assert(cpmMovementDialog.includes("let actionSequence = 0") && cpmMovementDialog.includes("actionIsStale"), "Cutting Plan movement actions can overwrite a newly opened document")
assert(cpmMovementDialog.includes(':closable="!busy"') && cpmMovementDialog.includes(':close-on-escape="!busy"'), "Cutting Plan movement can be closed while a mutation is active")
assert(cutBundleDialog.includes("let actionSequence = 0") && cutBundleDialog.includes("actionIsStale"), "Cut Bundle actions can overwrite a newly opened document")
assert(cutBundleDialog.includes('acting.value = ""') && cutBundleDialog.includes("previewSequence += 1"), "Cut Bundle route changes can preserve a stale busy state")
assert(goodsReceivedNote.includes("actionIsStale(sequence, requestedRouteName)"), "GRN calculation and inspection actions are not scoped to the active route")
assert(deliveryChallan.includes("previewDeliveryChallanSource") && deliveryChallan.includes("actionIsStale(sequence, requestedRouteName)"), "Delivery Challan source previews are not scoped to the active route")
assert(documentWorkspace.includes(':disabled="Boolean(acting)"\n\t\t\t\t\t@click="emit(\'reload\')"'), "Document refresh remains interactive during a mutation")
assert(documentActionStrip.includes('role="status"') && documentActionStrip.includes('showDisabledReason'), "Unavailable document actions do not expose their reason on focus or touch")
assert(documentActionStrip.includes('document-action-strip--with-reason') && documentActionStrip.includes('position: static'), "Mobile unavailable-action guidance can be clipped by the command bar")
assert(documentActionStrip.includes("document-action-strip__more--desktop") && documentActionStrip.includes("document-action-strip__more--mobile"), "Document secondary actions can disappear when the viewport changes")
assert(!documentActionStrip.includes("window.matchMedia"), "Document action visibility still relies on a timing-sensitive viewport listener")
for (const [label, source] of [
	["Cutting Plan", cuttingPlanEditor],
	["Cutting Order", cuttingOrderEditor],
	["Bulk LaySheets", bulkSetupEditor],
	["LaySheet Planner", cuttingLaySheetPlannerEditorPage],
	["Work Order", workOrderEditor],
	["Purchase Order", purchaseOrderEditor],
]) assert(source.includes('label="Cancel" icon="pi pi-times"'), `${label} mobile editor header has no recognizable Cancel icon`)
assert(movementRail.includes('role="status"') && movementRail.includes('showDisabledReason'), "Unavailable Cut Panel actions do not expose their reason on focus or touch")
for (const [label, source] of [
	["Work Order detail", fabricWorkOrderPage],
	["Work Order list", fabricWorkOrders],
	["Purchase Order detail", fabricPurchaseOrderPage],
	["Purchase Order list", fabricPurchaseOrders],
	["Fabric document shell", documentWorkspace],
]) {
	assert(!source.includes('["Cancelled", "Closed"]'), `${label} still presents a normally closed document as a destructive failure`)
}
for (const [label, source] of [
	["Cutting launcher", cuttingLauncher],
	["Fabric Store launcher", fabricLauncher],
	["Cut Panel Store launcher", cutPanelLauncher],
	["Cutting Plans", cuttingPlans],
	["Cutting Orders", cuttingOrders],
	["LaySheet Planner", cuttingLaySheetPlanners],
	["Bulk LaySheets", cuttingBulkLaySheets],
	["Fabric Store section", fabricSection],
	["Cut Panel Store section", cutPanelSection],
]) {
	assert(source.includes("<WorkspaceLoadError"), `${label} has no consistent retry state for capability failures`)
	assert(source.includes('@retry="load"'), `${label} capability failure cannot be retried`)
}
for (const [label, source] of [
	["Cutting Plans", cuttingPlans],
	["Cutting Orders", cuttingOrders],
	["Bulk LaySheets", cuttingBulkLaySheets],
	["LaySheet Planner", cuttingLaySheetPlanners],
]) {
	assert(source.includes('v-else-if="capability?.can_read"'), `${label} still fetches document rows without read permission`)
	assert(source.includes(':retryable="false"'), `${label} has no clear permission-denied state`)
}

assert(documentWorkspace.includes('class="fabric-document-workspace__chrome"'), "Document identity and actions are not grouped into one sticky chrome")
assert(!workOrderDetails.includes("grid-auto-flow: dense"), "Work Order facts can reorder visually around wide fields")
assert(workOrderDetails.includes("comments?") && workOrderDetails.includes("notes?"), "Work Order long-text fact classification misses comment or note fields")
assert(workOrderEditor.includes('v-if="showMatrices"') && workOrderEditor.includes('class="work-order-editor__matrix-prompt"'), "Empty Work Orders still render two full matrix sections before calculation")
assert(workOrderEditor.includes("const showMatrices = computed"), "Work Order matrix visibility is not derived from calculated rows or calculation mode")
assert(cuttingQuantityMatrix.includes("white-space: nowrap") && cuttingQuantityMatrix.includes("flex: 0 0 auto"), "Cutting quantity row-count badges can wrap on mobile")
assert(stockItemComposer.includes('aria-label="Steps: Select, Get Item, Add"') && stockItemComposer.includes("stock-composer__step-number"), "The stock item workflow still uses an unstructured instruction string")
assert(documentWorkspace.includes("min-height: 52px"), "Document identity header is still oversized")
assert(documentWorkspace.includes("min-height: 42px"), "Document command bar is still oversized")
assert(purchaseOrder.includes('class="purchase-order-page__totals"'), "Purchase Order totals are not grouped compactly")
assert(purchaseOrder.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"), "Purchase Order totals are not arranged in a compact grid")
assert(deliveryChallan.includes("delivery-challan-totals"), "Delivery Challan totals are not grouped compactly")
assert(goodsReceivedNote.includes("goods-received-note-totals"), "Goods Received Note totals are not grouped compactly")
assert(deliveryChallan.includes("fabric-document-workspace__metric-group"), "Delivery Challan total metrics are not exposed to the responsive rail contract")
assert(goodsReceivedNote.includes("fabric-document-workspace__metric-group"), "Goods Received Note total metrics are not exposed to the responsive rail contract")
assert(deliveryChallan.includes("currentPostingDefaults") && goodsReceivedNote.includes("currentPostingDefaults"), "New DC and GRN forms can still open with an empty Posting Time")
assert(documentWorkspace.includes(".fabric-document-workspace__metric-group > *"), "Compact document rails can clip grouped metrics")
assert(!departmentCard.includes("department.accent"), "Workspace cards still fragment the shared theme with department-specific colors")
assert(!/accent/i.test(departmentPage) && !/accent/i.test(departmentRegistry), "Department pages still override the shared emerald theme with a per-department accent")
assert(mainStyles.includes("@media (hover: hover)"), "Shell hover motion is not guarded for hover-capable devices")
assert(mainStyles.includes(".department-card {\n\t--accent: var(--erp-accent);\n\tposition: relative;\n\tmin-height: 96px;"), "Department cards still consume too much vertical space")
assert(mainStyles.includes("grid-template-columns: repeat(3, minmax(0, 1fr))"), "Wide administrator workspace still requires avoidable vertical scrolling")
assert(mainStyles.includes(".department-grid {\n\t\tgrid-template-columns: repeat(2, minmax(0, 1fr));") && mainStyles.includes("grid-template-rows: auto 1fr"), "Mobile administrator workspace does not use the compact two-column launcher")
assert(mainStyles.includes(".administrator-page__description {\n\t\tdisplay: none;") && mainStyles.includes("min-height: 104px"), "Mobile administrator home still spends excessive first-viewport height on intro copy and launcher cards")
assert(launcher.includes("@media (max-width: 600px)") && launcher.includes("grid-template-columns: repeat(2, minmax(0, 1fr))") && launcher.includes(".workspace-launcher__body small { display: none; }"), "Department launchers still force long single-column mobile scrolling")
assert(listView.includes(".common-list-view--viewport-bounded :deep(.premium-list-table),\n\t:global(.premium-list-table) {\n\t\tdisplay: none;"), "Mobile list view still renders the desktop table behind its record cards")
assert(fabricReports.includes('class="fabric-reports__header"') && fabricReports.includes("Stock Balance"), "Fabric reports do not expose a visible report identity")
assert(stockBalanceReport.includes("min-height: 44px"), "Stock Balance mobile checkbox labels do not provide a 44px touch target")
assert(linkField.includes('title: committedLabel.value') && linkField.includes("text-overflow: ellipsis"), "Committed LinkField values can still clip without a full-value affordance")
assert(mainStyles.includes("@media (max-width: 1120px)"), "Administrator workspace does not step down cleanly from three columns")
assert(mainStyles.includes(".p-dialog-mask,\n\t.p-dialog-mask *"), "Teleported dialogs are not covered by reduced-motion preferences")
assert(mainStyles.includes("width: 44px;\n\t\tmin-height: 44px"), "Mobile application header actions do not provide a 44px touch target")
assert(enterprise.includes("--erp-shell-header-height: 52px"), "The compact mobile shell height is not defined after enterprise theme tokens")
assert(enterprise.includes("top: var(--erp-shell-header-height)"), "Page editor headers do not remain below the sticky application header")
assert(enterprise.includes(".erp-editor-header > div:first-child > span") && enterprise.includes("padding: 4px var(--erp-space-3)"), "Mobile editor chrome still spends too much viewport height on secondary identity text")
assert(enterprise.includes("min-height: 55px") && enterprise.includes("flex-direction: row") && enterprise.includes("text-overflow: ellipsis"), "Shared mobile document editors still use a tall two-row sticky header")
assert(workOrderEditor.includes(".work-order-editor__header > div:first-child > span { display: none; }") && purchaseOrderEditor.includes(".purchase-order-editor__header > div:first-child > span { display: none; }"), "Fabric editors override the compact mobile header contract")
assert(workOrderEditor.includes("flex-direction: row") && purchaseOrderEditor.includes("flex-direction: row"), "Fabric mobile editors still use a two-row sticky header")
assert(purchaseOrderEditor.includes("@media (max-width: 340px)") && purchaseOrderEditor.includes(".purchase-order-editor__date { grid-column: 1 / -1; }"), "Purchase Order dates remain truncated on narrow phones")
assert(cuttingLaySheetPlannerEditorPage.includes("erp-editor-shell") && cuttingLaySheetPlannerEditorPage.includes("erp-editor-header") && cuttingLaySheetPlannerEditorPage.includes("erp-editor-actions"), "LaySheet Planner does not use the shared compact editor chrome")
assert(!cuttingLaySheetPlannerEditorPage.includes("align-items: flex-start; flex-direction: column"), "LaySheet Planner still forces a tall two-row mobile header")
assert(cuttingOrderPage.includes("@media (max-width: 1050px)") && cuttingOrderPage.includes(".order-record-header { align-items: stretch; flex-direction: column; }"), "Cutting Order record chrome stays overpacked at tablet widths")
assert(documentSaveButton.includes(":disabled=\"loading || disabled") && documentSaveButton.includes("loading ? 'pi pi-spinner pi-spin'"), "Split document save actions remain active without loading feedback during a mutation")
assert(cuttingLaySheetPlanner.includes('const actionBusy = computed') && cuttingLaySheetPlanner.includes(':disabled="actionBusy" @click="load"'), "LaySheet Planner refresh can invalidate an active action and strand its busy state")
assert(cuttingBulkLaySheet.includes(':disabled="Boolean(busy)" @click="loadWorkspace"'), "Bulk LaySheet refresh can invalidate an active action and strand its busy state")
assert(bulkWorkflowRail.includes(':disabled="Boolean(busy)"') && bulkWorkflowRail.includes('if (props.busy || !row.actions?.can_activate)'), "Bulk LaySheet rail remains interactive during an active action")
assert(movementDialog.includes(':busy="busy"') && movementRail.includes('busy: Boolean') && movementRail.includes('if (props.busy || !action?.eligible)'), "Cut Panel Movement rail can race the parent save action")
assert(enterprise.includes("min-width: 44px;\n\t\theight: 44px"), "Mobile dialog header controls do not meet the shared touch target")
assert(cuttingReports.includes("top: var(--erp-shell-header-height)"), "Cutting report tabs collide with the application header")
assert(cuttingReports.includes("<WorkspaceLoadError") && cuttingReports.includes('@retry="load"'), "Cutting report permission failures cannot be retried")
assert(cuttingPlanCpm.includes('title="Cut Panel Movement unavailable"') && cuttingPlanCpm.includes('@retry="load(true)"'), "Cut Panel Movement first-load failures cannot be retried")
assert(cuttingPlanStockTransfers.includes('title="Stock Transfers unavailable"') && cuttingPlanStockTransfers.includes('@retry="load(true)"'), "Stock Transfer first-load failures cannot be retried")
assert(cutPanelStoreReports.includes("top:var(--erp-shell-header-height)"), "Cut Panel Store report tabs collide with the application header")
assert(workOrderEditor.includes(':message="loadFailed ? \'\' : error"') && workOrderEditor.includes('@click="load"'), "Work Order load errors do not use one clear inline Retry state")
assert(purchaseOrderEditor.includes(':message="loadFailed ? \'\' : error"') && purchaseOrderEditor.includes('@click="load"'), "Purchase Order load errors do not use one clear inline Retry state")
assert(cuttingOrderEditor.includes(':message="loadFailed ? \'\' : error"') && cuttingOrderEditor.includes('@retry="load"'), "Cutting Order editor load errors have no clear Retry state")
assert(cuttingPlanEditor.includes(':message="loadFailed ? \'\' : error"') && cuttingPlanEditor.includes('@retry="load"'), "Cutting Plan editor load errors have no clear Retry state")
assert(bulkSetupEditor.includes('v-if="loadFailed"') && bulkSetupEditor.includes('@retry="load"'), "Bulk setup load errors have no clear Retry state")
assert(cuttingLaySheetPlannerEditorPage.includes('v-if="loadFailed"') && cuttingLaySheetPlannerEditorPage.includes('@retry="load"'), "LaySheet Planner editor load errors have no clear Retry state")
assert(cuttingLaySheetPlanner.includes('title="LaySheet Planner unavailable"') && cuttingLaySheetPlanner.includes('@retry="load"'), "LaySheet Planner first-load errors have no clear Retry state")
assert(cuttingBulkLaySheet.includes('title="Bulk LaySheets unavailable"') && cuttingBulkLaySheet.includes('@retry="loadWorkspace"'), "Bulk LaySheets first-load errors have no clear Retry state")
assert(cuttingLaySheetPlanner.includes("let actionSequence = 0") && cuttingLaySheetPlanner.includes("actionIsStale"), "LaySheet Planner action responses can overwrite a newly navigated plan")
assert(cuttingBulkLaySheet.includes("let actionSequence = 0") && cuttingBulkLaySheet.includes("actionIsStale"), "Bulk LaySheet action responses can overwrite a newly navigated document")
assert(workOrderEditor.includes("top: var(--erp-shell-header-height)"), "Work Order editor header still collides with the application shell")
assert(purchaseOrderEditor.includes("top: var(--erp-shell-header-height)"), "Purchase Order editor header still collides with the application shell")
assert(documentWorkspace.includes("min-height: min(620px, calc(100dvh - var(--erp-shell-header-height) - 97px))"), "Fabric document pages can force browser scrolling on short laptop viewports")
assert(documentWorkspace.includes(':message="hasWorkspace ? error : \'\'"') && documentWorkspace.includes('@click="emit(\'reload\')"'), "Fabric document load errors do not use one clear inline Retry state")
assert(cuttingPlanActions.includes("Mark completed cut quantity row"), "Cutting Plan completion checkboxes are unnamed")
assert(cuttingOrderActions.includes("Mark completed cut quantity row"), "Cutting Order completion checkboxes are unnamed")
assert(cuttingOrderActions.includes('<DocumentErrorDialog :message="actionError"'), "Cutting Order mutation failures still use a floating inline message")
assert(cuttingOrderDetailDialog.includes("Use panel row"), "Cutting Order panel default checkboxes are unnamed")
assert(grnCalculatePanel.includes("Use receipt calculation row"), "GRN calculation row checkboxes are unnamed")
for (const [label, source] of [
	["transaction dialog", documentTransactionDialog],
	["Cutting Order editor", cuttingOrderEditor],
	["Cutting Order detail dialog", cuttingOrderDetailDialog],
	["Cutting Plan editor", cuttingPlanEditor],
	["Work Order action panel", workOrderActionPanel],
]) {
	assert(source.includes('class="erp-dialog--sm"'), `${label} does not use the shared compact confirmation dialog`)
	assert(!source.includes("min(440px, calc(100vw"), `${label} still hard-codes its confirmation width`)
}
assert(!movementDialog.includes('<main class="cut-panel-movement-layout__main">'), "Cut Panel Movement dialog contains a nested main landmark")
assert(!movementDialog.includes("writing-mode:vertical-rl") && movementDialog.includes("writing-mode:horizontal-tb"), "Cut Panel Movement transaction source still uses a decorative vertical label")
assert(!movementRail.includes("max-height:calc(100vh - 230px)"), "Cut Panel Movement rail still creates a nested viewport-height scroll region")
for (const [label, source] of [
	["Cut Panel Movement", movementDialog],
	["Cut Bundle Edit", cutBundleDialog],
	["Box Sticker Print", boxStickerDialog],
	["Excel Sticker Print", excelStickerDialog],
]) {
	assert(source.includes("erp-dialog--xl"), `${label} does not use the shared large-dialog scale`)
	assert(!source.includes("width: 'min(96vw"), `${label} still hard-codes a near-full-screen width`)
}
assert(cutBundleDialog.includes('class="cut-bundle-table-scroll" tabindex="0" role="region"'), "Cut Bundle horizontal tables are not keyboard-focusable regions")
assert(cutBundleDialog.includes(':aria-label="`Select bundle'), "Cut Bundle source selectors have no row-specific accessible label")
assert(cutBundleDialog.includes('"aria-label": `Remove output bundle ${index + 1}`'), "Cut Bundle remove controls have no row-specific accessible label")
assert(cutBundleDialog.includes("min-width:44px;height:44px"), "Cut Bundle row controls do not meet the shared touch target")
assert(boxStickerDialog.includes(".box-sticker-preview__canvas{min-height:180px") && boxStickerDialog.includes(".box-sticker-empty{min-height:160px"), "Box Sticker mobile preview still consumes excessive vertical space")
assert(!boxStickerDialog.includes("box-sticker-workspace") && boxStickerDialog.includes("min-width:900px") && boxStickerDialog.includes("text-align:center;text-transform:uppercase"), "Box Sticker preview still squeezes the size table or headers are not centred")
assert(excelStickerDialog.includes(".excel-sticker-preview__canvas{min-height:180px") && excelStickerDialog.includes(".excel-sticker-empty{min-height:160px"), "Excel Sticker mobile preview still consumes excessive vertical space")
assert(cutPanelMovementEditor.includes("erp-check-target"), "Cut Panel Movement native checkboxes do not have usable touch targets")
assert(cutPanelMovementEditor.includes("width:18px;height:18px"), "Cut Panel Movement checkboxes remain too small")
assert(cutPanelMovementEditor.includes(".erp-check-target{display:inline-grid;min-width:44px;min-height:44px"), "Cut Panel Movement inline checkbox labels do not apply their touch target")
assert(enterprise.includes(".p-dialog:is(.erp-entity-dialog, .action-dialog, .laysheet-subdialog") && enterprise.includes(".cut-panel-printer-dialog) .p-dialog-footer .p-button"), "Nested mobile dialog footer actions do not meet the shared touch target")
assert(enterprise.includes(".document-action-strip, .cut-panel-movement-rail__actions, .fabric-document-workspace__commandbar"), "Core mobile document actions do not share the 44px touch target")
assert(enterprise.includes(".document-confirmation-shell, .document-error-dialog"), "Confirmation and error dialog actions do not share the 44px touch target")
assert(movementRail.includes("font-size:var(--erp-font-size-min)"), "Cut Panel Movement rail uses unreadably small status text")
assert(documentErrorDialog.includes('v-if="retryLabel" label="Dismiss"'), "Retryable errors do not offer a clear dismiss action")
assert(documentErrorDialog.includes('ref="primaryAction"') && documentErrorDialog.includes('@show="focusPrimaryAction"'), "The primary recovery action is not explicitly focused")
assert(documentErrorDialog.includes('@hide="restoreFocus"'), "Error dialogs do not restore focus to the invoking control")
for (const [label, source] of [
	["Document transaction", documentTransactionDialog],
	["Purchase Order", purchaseOrderDialog],
	["Fabric stock operation", stockOperationDialog],
	["Delivery Challan return", deliveryChallanReturnDialog],
]) {
	assert(!source.match(/max-height:\s*(?:68|70|72)vh/), `${label} dialog still creates a nested viewport-height scroller`)
}
assert(!workOrderActionPanel.includes("max-height: 58dvh"), "Work Order action tables still create a second vertical scrollbar")
assert(workOrderActionPanel.includes('class="work-order-action-panel erp-entity-dialog"'), "Work Order action panel can clip large tables outside a bounded dialog")
assert(workOrderActionPanel.includes('aria-label="`Use garment row'), "Work Order garment row selectors have no accessible label")
assert(!cutPanelMovementEditor.includes("max-height:360px"), "Cut Panel Movement matrices still create nested vertical scrolling")
assert(documentTransactionDialog.includes("erp-dialog--lg"), "Document transaction dialog does not use the shared large-dialog scale")
assert(purchaseOrderDialog.includes("erp-dialog--lg"), "Purchase Order dialog does not use the shared large-dialog scale")
assert(stockOperationDialog.includes("erp-dialog--xl"), "Fabric stock operation dialog does not use the shared extra-large scale")
assert(deliveryChallanReturnDialog.includes("erp-dialog--lg"), "Delivery Challan return dialog does not use the shared large-dialog scale")
assert(deliveryChallanReturnDialog.includes('role="region" tabindex="0" aria-label="Returnable Delivery Challan quantities"') && deliveryChallanReturnDialog.includes('Return quantity for'), "Delivery Challan return dialog table is not keyboard-accessible and row-labelled")
assert(deliveryChallanReturnPanel.includes('role="region" tabindex="0" aria-label="Delivery Challan return quantities"') && deliveryChallanReturnPanel.includes('Return quantity for'), "Delivery Challan return panel table is not keyboard-accessible and row-labelled")
assert(grnCalculatePanel.includes('role="region" tabindex="0" aria-label="Goods Received Note receivable quantities"') && grnCalculatePanel.includes('quantityInputLabel(row, rowIndex, value)'), "GRN quantity matrix is not keyboard-accessible and cell-labelled")
assert(grnCalculatePanel.includes('.grn-calculate-panel__quantity :deep(.p-inputnumber-input) { height: 44px; min-height: 44px; }'), "GRN calculation inputs remain too small for touch")
assert(deliveryChallanReturnPanel.includes('.delivery-challan-return-panel__table :deep(.p-inputnumber-input) { height: 44px; min-height: 44px; }'), "Delivery return panel inputs remain too small for touch")
assert(deliveryChallanReturnDialog.includes('.dc-return-table :deep(.p-inputnumber-input) { height: 44px; min-height: 44px; }'), "Delivery return dialog inputs remain too small for touch")
assert(documentSaveButton.includes('import SplitButton from "primevue/splitbutton"'), "Frappe-style document save menu is missing")
assert(documentSaveButton.includes(':button-props="{ disabled: loading || disabled || saveDisabled }"'), "Document save primary action does not preserve its independent disabled state")
assert(documentSaveButton.includes(':menu-button-props="{ \'aria-label\': `${saveLabel} options`, disabled: loading || disabled || submitDisabled }"'), "Document save menu has no accessible name or independent disabled state")
for (const [label, source, oldMain] of [
	["Fabric document workspace", documentWorkspace, '<main class="fabric-document-workspace__main">'],
	["Cutting Order", cuttingOrderPage, '<main class="cutting-order-main erp-card">'],
	["Bulk LaySheets", cuttingBulkLaySheet, '<main class="bulk-workspace-main">'],
	["Planner result", plannerPlanWorkspace, '<main class="planner-plan-workspace__result">'],
]) assert(!source.includes(oldMain), `${label} still nests a main landmark inside DepartmentPage`)
for (const [label, source] of [
	["Cutting Order", cuttingOrderEditor],
	["Cutting Plan", cuttingPlanEditor],
	["Fabric stock operation", stockOperationDialog],
]) {
	assert(source.includes("<DocumentSaveButton"), `${label} still renders competing save and submit buttons`)
}
for (const [label, source] of [
	["Cutting Order", cuttingOrderEditor],
	["Cutting Plan", cuttingPlanEditor],
	["Work Order action", workOrderActionPanel],
	["Document transaction", documentTransactionDialog],
	["Purchase Order", purchaseOrderDialog],
	["Fabric stock operation", stockOperationDialog],
	["Delivery Challan return", deliveryChallanReturnDialog],
]) {
	assert(source.includes("<DocumentErrorDialog"), `${label} blocking failures are not presented in the shared popup`)
	assert(!source.includes('<Message v-if="error" severity="error"'), `${label} still duplicates blocking errors inline`)
}
for (const [label, source] of [
	["Cutting Marker", cuttingMarkerDialog],
	["Cutting Lay Sheet", cuttingLaySheetDialog],
	["Bulk Delivery", bulkDeliveryDialog],
	["Bulk Print", bulkPrintDialog],
	["Cutting Order Detail", cuttingOrderDetailDialog],
]) {
	assert(source.includes("<DocumentErrorDialog") && source.includes("actionError.value = reason"), `${label} mutation failures are not presented in the shared popup`)
}
assert(bulkSetupEditor.includes("<DocumentErrorDialog") && bulkSetupEditor.includes("actionError.value = reason"), "Bulk setup save failures are not presented in the shared popup")
assert(bulkActiveLaySheet.includes("<DocumentErrorDialog") && bulkActiveLaySheet.includes("actionError.value = reason"), "Active Bulk LaySheet save failures are not presented in the shared popup")
assert(cuttingBulkLaySheet.includes("<DocumentErrorDialog") && cuttingBulkLaySheet.includes("actionError.value = reason"), "Bulk LaySheet workflow failures are not presented in the shared popup")
assert(!cuttingBulkLaySheet.includes('<Message v-if="dialogError" severity="error"'), "Bulk bundle generation failures remain inline")
assert(cuttingLaySheetDialog.includes('actionError.value = reason.message || "Unable to connect to QZ Tray."'), "LaySheet printer connection failures remain inline")
assert(cuttingPlanActions.includes('<DocumentErrorDialog :message="dialogError"') && !cuttingPlanActions.includes('<Message v-if="dialogError" severity="error"'), "Cutting Plan mutation failures remain inline")
assert(cuttingOrderPage.includes('<DocumentErrorDialog :message="actionError"') && cuttingOrderPage.includes('actionError.value = reason?.message || `Unable to ${action} the Cutting Order.`'), "Cutting Order lifecycle failures remain inline")
assert(cuttingLaySheetPlanner.includes('<DocumentErrorDialog :message="actionError"') && cuttingLaySheetPlanner.includes('actionError.value = reason?.message || "Unable to save Planner inputs."'), "LaySheet Planner mutation failures remain inline")
assert(cuttingLaySheetPlannerEditorPage.includes('<DocumentErrorDialog :message="actionError"') && cuttingLaySheetPlannerEditorPage.includes('actionError.value = reason?.message || "Unable to save the LaySheet Plan."'), "New LaySheet Planner save failures remain inline")
assert(bulkWorkflowRail.includes('class="bulk-workflow-card__actions" @click.stop @keydown.stop'), "Bulk workflow action keys can also activate the parent card")
assert(bulkWorkflowRail.includes('@media (max-width: 1100px)') && bulkWorkflowRail.includes('overflow-y: visible'), "Stacked Bulk workflow retains a nested vertical scrollbar")
assert(cuttingPlanSidebar.includes('.rail-loading, .rail-list { overflow-y: visible; overscroll-behavior: auto; }'), "Stacked Cutting Plan rail retains nested vertical scrolling")
assert(cuttingPlanSidebar.includes('min-width: 44px;') && plannerOrderMatrix.includes('min-height: 44px'), "Responsive Cutting controls do not meet the touch-target contract")
assert(cuttingMarkerDialog.includes(':aria-label="`Ratio for ${row.size}${row.panel ? ` · ${row.panel}` : \'\'}`"') && cuttingMarkerDialog.includes(':aria-label="`Panels for group ${index + 1}`"'), "Marker repeated controls are not row-labelled")
assert(cuttingLaySheetDialog.includes(':aria-label="`Bundle group for ${row.part || `panel ${index + 1}`}`"'), "LaySheet bundle-group controls are not row-labelled")
assert(plannerDeviationTable.includes('role="region" tabindex="0" aria-label="Size deviation results"'), "Planner deviation table is not a named keyboard region")
assert(cuttingCompletedReport.includes('role="region" tabindex="0" :aria-labelledby="sectionHeadingId(sectionIndex)"'), "Completed Cutting report tables are not named keyboard regions")
assert(bulkActiveLaySheet.includes('role="region" tabindex="0" aria-label="Cloth details"') && bulkActiveLaySheet.includes('role="region" tabindex="0" aria-label="Accessory details"'), "Bulk detail tables are not named keyboard regions")
assert(workOrderItemMatrix.includes('role="region" tabindex="0" :aria-label="`${section.name || \'Work Order item\'} quantities`"'), "Work Order item matrices are not named keyboard regions")
assert(cuttingLaySheetDialog.includes("let loadSequence = 0") && cuttingLaySheetDialog.includes("sheet.value = null"), "Lay Sheet navigation can retain a stale record")
assert(cuttingLaySheetDialog.includes('<DocumentStatusBadge :docstatus="sheet.docstatus"'), "Lay Sheet status does not use the shared document status semantics")
assert(!cuttingLaySheetDialog.includes("status-pill--"), "Lay Sheet retains contradictory local status colors")
assert(cuttingOrderDetailDialog.includes(':aria-label="`Attribute row ${index + 1}`"') && cuttingOrderDetailDialog.includes('`Remove ${componentProps.title || "detail"} row ${index + 1}`'), "Cutting Order Detail repeated row controls are not individually named")
assert(workOrderActionPanel.includes('.work-order-action-panel__body :deep(.p-inputnumber-input) { height: 44px; min-height: 44px; }'), "Fabric Work Order action quantities remain undersized on touch screens")
assert(!cuttingLaySheetPlanner.includes("min-height: 660px") && plannerPlanWorkspace.includes("max-height: none") && plannerPlanWorkspace.includes("overflow-y: visible"), "Mobile LaySheet Planner retains nested vertical scrolling")
assert(!workOrderDeliveryMatrix.includes("max-height: 320px") && workOrderDeliveryMatrix.includes("overflow-x: auto"), "Desktop Work Order delivery matrices retain nested vertical scrolling")
assert(!movementDialog.includes("max-height:280px") && movementDialog.includes(".transaction-work-order-loading,.transaction-work-orders{display:grid;gap:7px}"), "Desktop Cut Panel transaction selection retains nested vertical scrolling")
assert(plannerPlanWorkspace.includes('v-if="hasPlanContext"') && plannerPlanWorkspace.includes("const hasPlanContext = computed"), "Empty Planner repeats two large empty states")
assert(plannerStrategies.includes("min-height: 220px") && plannerLayPlan.includes("min-height: 220px"), "Planner empty states remain oversized")
assert(!stockBalanceReport.includes("max-height: 58vh") && stockBalanceReport.includes("@media (max-width: 800px)"), "Stock Balance retains nested vertical scrolling or lacks a responsive option grid")
assert(fabricSection.includes("padding: 2px 0") && cutPanelSection.includes("padding: 2px 0"), "Fabric and Cut Panel sections do not share the Cutting page gutter")
assert(workOrderEditor.includes("min-height: 52px") && workOrderEditor.includes("font-size: 19px"), "Work Order view and edit headers change scale")
assert(purchaseOrderEditor.includes("min-height: 52px") && purchaseOrderEditor.includes("font-size: 19px"), "Purchase Order view and edit headers change scale")
assert(workOrderActivityRail.includes("activity-card--mobile-overflow") && workOrderActivityRail.includes("activity-mobile-toggle"), "Mobile Work Order activity histories are not progressively disclosed")
assert(movementRail.includes("cut-panel-movement-rail__row--mobile-overflow") && movementRail.includes("cut-panel-movement-rail__toggle"), "Mobile Cut Panel Movement histories are not progressively disclosed")
assert(!cuttingOrderPage.includes("min-height: 760px") && cuttingOrderTabs.includes("overflow-y: visible"), "Stacked Cutting Order retains an artificial height or nested scroll")
assert(workOrderEditor.includes("width: 44px; min-width: 44px") && !workOrderEditor.includes("@media (max-width: 420px)"), "Work Order dates do not retain compact paired mobile rows")
assert(purchaseOrderEditor.includes("width: 44px; min-width: 44px") && !purchaseOrderEditor.includes("@media (max-width: 420px)"), "Purchase Order dates do not retain compact paired mobile rows")
for (const selector of [".form-toolbar__actions", ".report-shell__commands", ".planner-record-actions", ".bulk-record-header__actions", ".fabric-document-workspace__header-actions"]) assert(enterprise.includes(selector), `${selector} is missing from the coarse-pointer touch contract`)
assert(dailyProductionReport.includes("min-height: 44px"), "Daily Production mode controls remain undersized on touch screens")
assert(cutPanelStoreReports.includes("min-height:44px"), "Cut Panel report tabs remain undersized on mobile")

console.log("premium UI polish contracts: OK")
