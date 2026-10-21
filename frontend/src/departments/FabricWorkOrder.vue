<template>
	<DepartmentPage title="Work Order" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<section class="fabric-work-order-frame">
			<FabricDocumentWorkspace doctype="YRP Work Order" title="Work Order" :workspace="workspace" :loading="loading" :error="error || actionError" :acting="acting" :show-lifecycle-actions="false" @reload="loadWorkspace(true)" @action="runWorkspaceAction">
				<template #header="{ record, headingId }">
					<div class="work-order-page__identity">
						<div class="work-order-page__title-row">
							<div class="work-order-page__title">
								<div class="work-order-page__meta">
									<span>Work order · {{ record.name }}</span>
									<span class="work-order-page__date"><span>WO date</span><strong>{{ woDate }}</strong></span>
								</div>
								<h1 :id="headingId" :aria-label="[record.lot, record.item || 'Work Order'].filter(Boolean).join(' · ')">
									<span v-if="record.lot" class="work-order-page__lot"><DocumentLink doctype="SD YRP Lot" :name="record.lot" :label="record.lot" /></span>
									<span v-if="record.lot && record.item" class="work-order-page__title-separator" aria-hidden="true">·</span>
									<span><DocumentLink doctype="Item" :name="record.item" :label="record.item || 'Work Order'" /></span>
								</h1>
							</div>
							<DocumentStatusBadge :docstatus="record.docstatus" :label="record.status || statusLabel(record.docstatus)" />
						</div>
					</div>
				</template>

				<template #header-actions>
					<DocumentActionStrip :actions="workOrderActions" />
				</template>

				<template #matrix>
					<Tabs v-model:value="activeTab" class="work-order-tabs erp-tabs">
						<TabList class="work-order-tablist">
							<Tab value="overview">Overview</Tab>
							<Tab v-if="deliverables.length" value="deliverables">Deliverables {{ deliverableCount }}</Tab>
							<Tab v-if="receivables.length" value="receivables">Receivables {{ receivableCount }}</Tab>
							<Tab v-if="showSummary" value="summary">Summary</Tab>
						</TabList>
						<TabPanels class="work-order-panels">
							<TabPanel value="overview"><WorkOrderOverview :details="visibleFields" /></TabPanel>
							<TabPanel v-if="deliverables.length" value="deliverables"><WorkOrderDetails :deliverables="deliverables" :process-cost-view-route-name="processCostViewRouteName" matrices-only /></TabPanel>
							<TabPanel v-if="receivables.length" value="receivables"><WorkOrderDetails :receivables="receivables" :process-cost-view-route-name="processCostViewRouteName" matrices-only /></TabPanel>
							<TabPanel v-if="showSummary" value="summary"><WorkOrderSummary :summary="workspace.summary || {}" :process-cost-view-route-name="processCostViewRouteName" /></TabPanel>
						</TabPanels>
					</Tabs>
				</template>

				<template #rail>
					<QualityWorkOrderInspections v-if="quality && workspace.record?.name" :work-order="workspace.record.name" @can-create="canCreateQualityInspection = $event" />
					<div v-if="railTotals.length" class="work-order-page__totals"><div v-for="total in railTotals" :key="total.fieldname" class="work-order-page__total"><span>{{ total.label }}</span><strong>{{ formatNumber(total.value) }}</strong></div></div>
					<WorkOrderActivityRail ref="activityRail" :work-order="workspace.record?.name || ''" :delivery-challans="deliveryChallans" :goods-received-notes="goodsReceivedNotes" :permissions="workspace.related_permissions || {}" @create="createRelated" @open="openRelatedRow" />
				</template>

			</FabricDocumentWorkspace>
		</section>

		<WorkOrderActionPanel v-model:visible="actionVisible" :mode="actionMode" :work-order="workspace.record || {}" :editor="actionEditor" @changed="actionChanged" />
		<RelatedDocumentWorkspaceDialog v-model:visible="relatedVisible" :doctype="relatedDoctype" :name="relatedName" :source-context="relatedSourceContext" @changed="relatedChanged" @closed="relatedClosed" />
		<DocumentConfirmationDialog v-model:visible="lifecycleConfirmVisible" :title="lifecycleConfirmTitle" :message="lifecycleConfirmMessage" :confirm-label="lifecycleConfirmLabel" :busy="Boolean(acting)" @confirm="confirmLifecycleAction" />
		<FabricStockOperationDialog v-model:visible="materialIssueVisible" operation="stock_entry" :source-context="materialIssueContext" @changed="materialIssueChanged" />
		<Dialog v-model:visible="grnSourceVisible" modal header="Create Goods Received Note" class="fabric-action-dialog erp-dialog--md" :dismissable-mask="false">
			<div class="work-order-grn-source">
				<Message severity="secondary" :closable="false">{{ grnRequiresDeliveryChallan ? "This rework Work Order requires a submitted Delivery Challan." : "Choose the Delivery Challan being received, or continue without one when this receipt is not tied to a dispatch." }}</Message>
				<LinkField v-model="grnDeliveryChallan" :label="grnRequiresDeliveryChallan ? 'Delivery Challan *' : 'Delivery Challan'" doctype="YRP Delivery Challan" :filters="{ work_order: workspace.record?.name, docstatus: 1 }" :show-open-button="false" show-clear />
			</div>
			<template #footer><Button label="Cancel" severity="secondary" text @click="grnSourceVisible = false" /><Button label="Continue to GRN" icon="pi pi-arrow-right" :disabled="grnRequiresDeliveryChallan && !grnDeliveryChallan" @click="openGoodsReceivedNote" /></template>
		</Dialog>
	</DepartmentPage>
</template>

<script setup>
import DocumentLink from "../components/common/DocumentLink.vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, nextTick, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { executeWorkOrderCommand, getWorkOrderEditor, getWorkOrderWorkspace } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import LinkField from "../components/common/LinkField.vue"
import DocumentActionStrip from "../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../components/documents/DocumentConfirmationDialog.vue"
import DocumentStatusBadge from "../components/documents/DocumentStatusBadge.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import { hasDocumentDisplayValue } from "../utils/documentValues.js"
import FabricDocumentWorkspace from "./fabric-store/FabricDocumentWorkspace.vue"
import FabricStockOperationDialog from "./fabric-store/FabricStockOperationDialog.vue"
import RelatedDocumentWorkspaceDialog from "./fabric-store/RelatedDocumentWorkspaceDialog.vue"
import WorkOrderActionPanel from "./fabric-store/WorkOrderActionPanel.vue"
import WorkOrderActivityRail from "./fabric-store/WorkOrderActivityRail.vue"
import WorkOrderDetails from "./fabric-store/WorkOrderDetails.vue"
import WorkOrderOverview from "./fabric-store/WorkOrderOverview.vue"
import WorkOrderSummary from "./fabric-store/WorkOrderSummary.vue"
import QualityWorkOrderInspections from "./quality/components/QualityWorkOrderInspections.vue"

const props = defineProps({
	backTo: { type: String, default: "/fabric-store/work-orders" },
	backLabel: { type: String, default: "Work Orders" },
	viewRouteName: { type: String, default: "fabric-work-order" },
	newRouteName: { type: String, default: "fabric-work-order-new" },
	editRouteName: { type: String, default: "fabric-work-order-edit" },
	processCostViewRouteName: { type: String, default: "" },
	showEditorActions: { type: Boolean, default: true },
	quality: { type: Boolean, default: false },
})

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const acting = ref("")
const error = ref("")
const actionError = ref("")
const activeTab = ref("overview")
const workspace = ref({})
const canCreateQualityInspection = ref(false)
const actionVisible = ref(false)
const actionMode = ref("")
const actionEditor = ref({})
const actionSourceId = ref("")
const relatedVisible = ref(false)
const relatedDoctype = ref("YRP Delivery Challan")
const relatedName = ref("")
const relatedSourceContext = ref({})
const activityRail = ref(null)
const materialIssueVisible = ref(false)
const materialIssueContext = ref({})
const grnSourceVisible = ref(false)
const grnDeliveryChallan = ref("")
const grnRequiresDeliveryChallan = ref(false)
const lifecycleConfirmVisible = ref(false)
const pendingLifecycleCommand = ref("")
let loadSequence = 0
let actionSequence = 0
const headerFieldnames = new Set(["status", "wo_date", "item", "lot"])

const capabilities = computed(() => workspace.value.capabilities || {})
const overviewLabels = { process_name: "Process", supplier: "Job worker", supplier_name: "Job worker" }
const visibleFields = computed(() => {
	const fields = workspace.value.fields?.length ? workspace.value.fields : workspace.value.details || []
	const hasSupplierName = fields.some((field) => field?.fieldname === "supplier_name" && hasDocumentDisplayValue(field.value))
	const byFieldname = new Map()
	for (const field of [...fields, ...(workspace.value.dimensions || [])]) {
		if (!field?.fieldname || field.hidden || headerFieldnames.has(field.fieldname) || byFieldname.has(field.fieldname) || !hasDocumentDisplayValue(field.value)) continue
		if (field.fieldname === "supplier" && hasSupplierName) continue
		byFieldname.set(field.fieldname, overviewLabels[field.fieldname] ? { ...field, label: overviewLabels[field.fieldname] } : field)
	}
	return [...byFieldname.values()]
})
const fieldValues = computed(() => new Map(
	[...(workspace.value.fields || workspace.value.details || []), ...(workspace.value.dimensions || [])]
		.filter((field) => field?.fieldname)
		.map((field) => [field.fieldname, field.value]),
))
const railTotals = computed(() => workspace.value.totals || [])
const woDate = computed(() => formatDate(fieldValues.value.get("wo_date")))
const deliverables = computed(() => workspace.value.matrices?.deliverables || workspace.value.deliverables || [])
const receivables = computed(() => workspace.value.matrices?.receivables || workspace.value.receivables || [])
const deliverableCount = computed(() => itemCount(deliverables.value))
const receivableCount = computed(() => itemCount(receivables.value))
const deliveryChallans = computed(() => workspace.value.related?.delivery_challans || workspace.value.delivery_challans || [])
const goodsReceivedNotes = computed(() => workspace.value.related?.goods_received_notes || workspace.value.goods_received_notes || [])
const showSummary = computed(() => Boolean(
	Number(workspace.value.record?.docstatus) === 1
	&& !workspace.value.record?.is_rework
	&& (workspace.value.summary?.item_detail?.length || workspace.value.summary?.deliverables?.length),
))
const workOrderActions = computed(() => {
	const busy = Boolean(acting.value)
	const actions = []
	if (props.quality && Number(workspace.value.record?.docstatus) === 1 && canCreateQualityInspection.value) {
		actions.push({ key: "new_quality_inspection", label: "New Quality Inspection", icon: "pi pi-verified", disabled: busy,
			command: () => router.push({ path: "/quality/inspections/new", query: { against_id: workspace.value.record.name } }),
		})
	}
	const add = (key, fallback, icon, command, options = {}) => {
		if (!props.showEditorActions && ["save", "amend"].includes(key)) return
		if (!capabilities.value[key]) return
		actions.push({
			key,
			label: capabilityLabel(key, fallback),
			icon,
			command,
			disabled: busy || Boolean(options.disabled),
			disabledReason: options.disabledReason || "",
			loading: acting.value === key,
			menuOnly: Boolean(options.menuOnly),
		})
	}
	add("create_delivery_challan", "Make DC", "pi pi-truck", () => openRelated("YRP Delivery Challan", "", capabilities.value.create_delivery_challan.source_context))
	add("create_goods_received_note", "Make GRN", "pi pi-plus", beginGoodsReceivedNote)
	add("calculate_garment", "Calculate Items", "pi pi-calculator", () => openAction("calculate_garment"))
	add("calculate_fabric", "Calculate Fabric Deliverables", "pi pi-calculator", () => openAction("calculate_fabric"))
	add("create_cutting_plan", "Make Cutting Plan", "pi pi-scissors", openCuttingPlan)
	add("save", "Edit", "pi pi-pencil", editWorkOrder)
	add("submit", "Submit", "pi pi-check", () => requestLifecycleAction("submit"))
	add("cancel", "Cancel Document", "pi pi-ban", () => requestLifecycleAction("cancel"), { menuOnly: true })
	add("amend", "Amend", "pi pi-copy", () => requestLifecycleAction("amend"), { menuOnly: true })
	if (props.showEditorActions && workspace.value.permissions?.can_create) actions.push({ key: "duplicate", label: "Duplicate", icon: "pi pi-clone", command: duplicateWorkOrder, disabled: busy, loading: false, menuOnly: true })
	add("create_debit", "Create Debit", "pi pi-wallet", () => openAction("create_debit"), { menuOnly: true })
	add("create_rework", "Create Rework", "pi pi-replay", () => openAction("create_rework"), { menuOnly: true })
	add("calculate_pieces", "Calculate Pieces", "pi pi-calculator", () => openAction("calculate_pieces"), { menuOnly: true })
	add("change_delivery_date", "Change Delivery Date", "pi pi-calendar", () => openAction("change_delivery_date"), { menuOnly: true })
	add("change_item", "Change Item", "pi pi-sync", () => openAction("change_item"), { menuOnly: true })
	add("request_close", "Request Close", "pi pi-lock", () => openAction("request_close"), { menuOnly: true })
	add("close", "Close", "pi pi-lock", () => openAction("close"), { menuOnly: true })
	add("approve_close", "Approve Close", "pi pi-check-circle", () => openAction("approve_close"), { menuOnly: true })
	add("create_material_issue", "Material Issue", "pi pi-sign-out", openMaterialIssue, { menuOnly: true })
	add("create_recut", "Create Recut", "pi pi-clone", () => openAction("create_recut"), { menuOnly: true })
	add("create_sewing_plan", "Create Sewing Plan", "pi pi-plus", () => openAction("create_sewing_plan"), { menuOnly: true })
	add("open_sewing_plan", "Open Sewing Plan", "pi pi-arrow-up-right", openSewingPlan, { menuOnly: true })
	const submittedDcExists = deliveryChallans.value.some((row) => Number(row.docstatus) === 1)
	const primaryKey = capabilities.value.submit && deliverables.value.length
		? "submit"
		: capabilities.value.calculate_garment ? "calculate_garment"
			: capabilities.value.calculate_fabric ? "calculate_fabric"
				: capabilities.value.approve_close
		? "approve_close"
		: submittedDcExists && capabilities.value.create_goods_received_note
			? "create_goods_received_note"
			: capabilities.value.create_delivery_challan
				? "create_delivery_challan"
				: capabilities.value.create_goods_received_note ? "create_goods_received_note" : capabilities.value.amend ? "amend" : ""
	const preferredKey = actions.some(({ key }) => key === "new_quality_inspection") ? "new_quality_inspection" : primaryKey
	return actions.map((action) => ({ ...action, primary: action.key === preferredKey }))
})

async function loadWorkspace(refresh = false) {
	const requestedId = String(route.params.workOrderId || "")
	const sequence = ++loadSequence
	actionSequence += 1
	if (!refresh) {
		acting.value = ""
		actionVisible.value = false
		actionSourceId.value = ""
		relatedVisible.value = false
		relatedName.value = ""
		relatedSourceContext.value = {}
		materialIssueVisible.value = false
		materialIssueContext.value = {}
		grnSourceVisible.value = false
		grnDeliveryChallan.value = ""
		lifecycleConfirmVisible.value = false
		pendingLifecycleCommand.value = ""
	}
	if (!refresh) loading.value = true
	else acting.value = "reload"
	error.value = ""
	if (!refresh) {
		workspace.value = {}
		canCreateQualityInspection.value = false
		actionError.value = ""
	}
	try {
		const data = await getWorkOrderWorkspace(requestedId) || {}
		if (sequence === loadSequence && requestedId === String(route.params.workOrderId || "")) workspace.value = data
	}
	catch (reason) {
		if (sequence === loadSequence) error.value = reason?.message || "Unable to load this Work Order."
	}
	finally {
		if (sequence === loadSequence) { loading.value = false; acting.value = "" }
	}
}
function capabilityLabel(name, fallback) { return capabilities.value[name]?.label || fallback }
function statusLabel(docstatus) { return Number(docstatus) === 1 ? "Submitted" : Number(docstatus) === 2 ? "Cancelled" : "Draft" }
function formatNumber(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function formatDate(value) { if (!value) return "—"; const [year, month, day] = String(value).slice(0, 10).split("-"); return day ? `${day}-${month}-${year}` : value }
function itemCount(groups) { return groups.reduce((count, group) => count + (group.items?.length || 0), 0) }
function editWorkOrder() { router.push({ name: props.editRouteName, params: { workOrderId: workspace.value.record.name }, state: preserveListNavigationState(workspace.value.record.name, workspace.value.record.modified) }) }
function duplicateWorkOrder() { router.push({ name: props.newRouteName, query: { duplicate_from: workspace.value.record.name } }) }
const lifecycleConfirmTitle = computed(() => pendingLifecycleCommand.value === "submit" ? "Submit Work Order?" : pendingLifecycleCommand.value === "cancel" ? "Cancel Work Order?" : "Amend Work Order?")
const lifecycleConfirmLabel = computed(() => pendingLifecycleCommand.value === "submit" ? "Submit" : pendingLifecycleCommand.value === "cancel" ? "Cancel Work Order" : "Create Amendment")
const lifecycleConfirmMessage = computed(() => pendingLifecycleCommand.value === "submit" ? `Permanently submit ${workspace.value.record?.name}?` : pendingLifecycleCommand.value === "cancel" ? `Cancel ${workspace.value.record?.name}? This keeps the document for audit but stops further processing.` : `Create a new draft amendment from ${workspace.value.record?.name}?`)
async function runWorkspaceAction(action) { if (action === "save") return editWorkOrder(); if (["submit", "cancel", "amend"].includes(action)) return requestLifecycleAction(action); return openAction(action) }
function requestLifecycleAction(command) { pendingLifecycleCommand.value = command; lifecycleConfirmVisible.value = true }
async function confirmLifecycleAction() { const command = pendingLifecycleCommand.value; lifecycleConfirmVisible.value = false; pendingLifecycleCommand.value = ""; if (command) await runLifecycleAction(command) }
async function runLifecycleAction(command) {
	const requestedId = String(route.params.workOrderId || "")
	const source = workspace.value.record
	const sequence = ++actionSequence
	acting.value = command; actionError.value = ""
	try {
		const result = await executeWorkOrderCommand(source.name, command, {}, source.modified) || {}
		if (sequence !== actionSequence || requestedId !== String(route.params.workOrderId || "")) return
		const name = result.record?.name || source.name
		workspace.value = result
		if (name !== requestedId) await router.replace({ name: props.viewRouteName, params: { workOrderId: name }, state: preserveListNavigationState(name) })
	}
	catch (reason) { if (sequence === actionSequence && requestedId === String(route.params.workOrderId || "")) actionError.value = reason?.message || `Unable to ${command} this Work Order.` }
	finally { if (sequence === actionSequence) acting.value = "" }
}
async function openAction(mode) {
	actionError.value = ""
	actionSourceId.value = String(route.params.workOrderId || "")
	if (["calculate_garment", "calculate_fabric"].includes(mode)) {
		const requestedId = actionSourceId.value
		const sequence = ++actionSequence
		acting.value = mode
		try {
			const result = await getWorkOrderEditor(workspace.value.record.name) || {}
			if (sequence !== actionSequence || requestedId !== String(route.params.workOrderId || "")) return
			actionEditor.value = result
		}
		catch (reason) { if (sequence === actionSequence && requestedId === String(route.params.workOrderId || "")) actionError.value = reason?.message || "Unable to load the Work Order calculation."; return }
		finally { if (sequence === actionSequence) acting.value = "" }
	} else actionEditor.value = {}
	if (actionSourceId.value !== String(route.params.workOrderId || "")) return
	actionMode.value = mode; actionVisible.value = true
}
async function actionChanged(result) {
	if (actionSourceId.value && actionSourceId.value !== String(route.params.workOrderId || "")) return
	if (!result?.record) return loadWorkspace(true)
	const resultName = result.record.name
	workspace.value = result
	if (resultName && resultName !== route.params.workOrderId) await router.replace({ name: props.viewRouteName, params: { workOrderId: resultName }, state: preserveListNavigationState(resultName) })
}
function openRelated(doctype, name = "", sourceContext = {}) { relatedDoctype.value = doctype; relatedName.value = name; relatedSourceContext.value = { ...(sourceContext || {}) }; relatedVisible.value = true }
function createRelated(type) {
	if (type === "goods_received_note") return beginGoodsReceivedNote()
	const capability = capabilities.value.create_delivery_challan
	openRelated("YRP Delivery Challan", "", capability?.source_context || { work_order: workspace.value.record.name })
}
function openRelatedRow({ type, row }) { openRelated(type === "delivery_challan" ? "YRP Delivery Challan" : "YRP Goods Received Note", row.name) }
async function relatedChanged() { await loadWorkspace(true) }
function relatedClosed() {
	relatedVisible.value = false
	nextTick(() => activityRail.value?.reopenExpanded?.())
}
function openCuttingPlan() { router.push({ name: "cutting-plan-new", query: capabilities.value.create_cutting_plan?.source_context || {} }) }
function openMaterialIssue() { materialIssueContext.value = { ...(capabilities.value.create_material_issue?.source_context || {}) }; materialIssueVisible.value = true }
async function materialIssueChanged() { materialIssueVisible.value = false; await loadWorkspace(true) }
function beginGoodsReceivedNote() {
	const capability = capabilities.value.create_goods_received_note || {}
	const submitted = deliveryChallans.value.filter((row) => Number(row.docstatus) === 1)
	grnRequiresDeliveryChallan.value = Boolean(capability.requires_delivery_challan || workspace.value.record?.is_rework)
	grnDeliveryChallan.value = submitted.length === 1 ? submitted[0].name : ""
	grnSourceVisible.value = true
}
function openGoodsReceivedNote() {
	if (grnRequiresDeliveryChallan.value && !grnDeliveryChallan.value) return
	const source = { ...(capabilities.value.create_goods_received_note?.source_context || { work_order: workspace.value.record.name }) }
	if (grnDeliveryChallan.value) source.delivery_challan = grnDeliveryChallan.value
	grnSourceVisible.value = false
	openRelated("YRP Goods Received Note", "", source)
}
function openSewingPlan() {
	const capability = capabilities.value.open_sewing_plan || {}
	if (capability.name) router.push({ path: "/sewing/plans", query: { ...(capability.source_context || {}), tab: "data-entry" } })
}

watch(() => [route.params.workOrderId, props.quality], () => loadWorkspace(false), { immediate: true })
</script>

<style scoped>
.fabric-work-order-frame { width: 100%; min-width: 0; margin: 0 0 var(--erp-space-3); }
.work-order-page__identity { display: grid; width: 100%; min-width: 0; padding-block: 5px; }
.work-order-page__title-row { display: flex; min-width: 0; align-items: center; gap: 12px; }
.work-order-page__title { display: grid; min-width: 0; gap: 3px; }
.work-order-page__meta { display: flex; min-width: 0; align-items: center; gap: 12px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .035em; text-transform: uppercase; }
.work-order-page__date { display: inline-flex; align-items: center; gap: 5px; padding-left: 12px; border-left: 1px solid var(--erp-border); }
.work-order-page__date strong { color: var(--erp-text); font-weight: 780; font-variant-numeric: tabular-nums; }
.work-order-page__identity h1 { display: flex; max-width: min(1080px, 73vw); min-width: 0; align-items: baseline; gap: 7px; margin: 0; overflow: hidden; color: var(--erp-text); font-size: clamp(19px, 1.45vw, 24px); line-height: 1.12; letter-spacing: -.025em; white-space: nowrap; }
.work-order-page__identity h1 > span:last-child { overflow: hidden; text-overflow: ellipsis; }
.work-order-page__lot { flex: 0 0 auto; color: var(--erp-accent-hover); font-variant-numeric: tabular-nums; }
.work-order-page__title-separator { flex: 0 0 auto; color: var(--erp-text-muted); font-weight: 500; }
.work-order-page__total span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.work-order-tabs { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.work-order-tablist { position: sticky; z-index: var(--erp-layer-sticky); top: 0; background: var(--erp-surface); }
.work-order-panels { padding: var(--erp-space-3); background: color-mix(in srgb, var(--erp-bg) 72%, var(--erp-surface)); }
.work-order-panels :deep(.p-tabpanel) { padding: 0; }
.work-order-page__totals { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.work-order-page__total { display: grid; min-height: 66px; align-content: center; gap: 3px; padding: 9px 11px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); box-shadow: inset 3px 0 0 color-mix(in srgb, var(--erp-accent) 58%, var(--erp-surface)); }
.work-order-page__total strong { color: var(--erp-accent-hover); font-size: 17px; font-weight: 780; }
.work-order-grn-source { display: grid; gap: var(--erp-space-3); }
@media (max-width: 900px) { .work-order-page__totals, :deep(.work-order-activity-rail) { grid-column: 1 / -1; } }
@media (max-width: 650px) { .fabric-work-order-frame { margin-bottom: 0; } .work-order-page__identity { width: 100%; } .work-order-page__meta { align-items: flex-start; flex-direction: column; gap: 2px; } .work-order-page__date { padding-left: 0; border-left: 0; } .work-order-page__identity h1 { max-width: calc(100vw - 132px); } .work-order-page__totals { grid-template-columns: repeat(2, minmax(0, 1fr)); } .work-order-panels { padding: var(--erp-space-2); } }
</style>
