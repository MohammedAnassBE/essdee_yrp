<template>
	<DepartmentPage title="Production Order" back-to="/sales/production-orders" back-label="Production Orders" :show-title="false" flat full-width inline-navigation>
		<section class="ppo-page-frame">
			<FabricDocumentWorkspace doctype="YRP Production Order" title="Production Order" :workspace="workspace" :loading="loading" :error="error" :acting="acting" :show-lifecycle-actions="false" compact-mobile-rail @reload="load(true)">
				<template #header="{ record, headingId }">
					<div class="ppo-page__identity">
						<div class="ppo-page__title"><span>Production order · {{ record.name }}</span><h1 :id="headingId">{{ record.item || "Production Order" }}</h1></div>
						<DocumentStatusBadge :docstatus="record.docstatus" :label="record.status || statusLabel(record.docstatus)" />
					</div>
				</template>
				<template #header-actions><DocumentActionStrip :actions="actions" /></template>
				<template #fields>
					<Tabs v-model:value="activeTab" class="ppo-tabs erp-tabs">
						<TabList>
							<Tab value="details">Details</Tab>
							<Tab value="transfers">Quantity Transferred <span>{{ workspace.histories?.transfers?.length || 0 }}</span></Tab>
						</TabList>
						<TabPanels>
							<TabPanel value="details">
								<div class="ppo-details">
									<ProductionOrderOverview :fields="workspace.fields || []" />
									<ProductionOrderMatrix :rows="workspace.matrix || []" :ordered="workspace.ordered || []" lot-clickable @open-lot="openLotOcr" />
									<section v-if="dateActivity.length" class="ppo-activity erp-card"><header><span>DATE CHANGES</span><h2>Schedule history</h2></header><div v-for="entry in dateActivity" :key="entry.key"><strong>{{ entry.label }}</strong><span>{{ entry.value }}</span></div></section>
								</div>
							</TabPanel>
							<TabPanel value="transfers"><ProductionOrderTransferHistory :rows="workspace.histories?.transfers || []" /></TabPanel>
						</TabPanels>
					</Tabs>
				</template>
				<template #rail>
					<div class="ppo-page__metric"><span>Total quantity</span><strong>{{ formatNumber(workspace.record?.total_quantity) }}</strong><small>pieces</small></div>
					<div class="ppo-page__metric"><span>Delivery date</span><strong>{{ formatDate(workspace.record?.delivery_date) }}</strong></div>
					<div class="ppo-page__metric"><span>Lead time</span><strong>{{ workspace.record?.lead_time_given || 0 }} days</strong></div>
					<div v-if="workspace.linked_lots?.length" class="ppo-page__lots"><span>Linked Lots</span><strong v-for="lot in workspace.linked_lots" :key="lot">{{ lot }}</strong></div>
				</template>
			</FabricDocumentWorkspace>
		</section>

		<ProductionOrderActionDialog v-model:visible="actionVisible" :mode="actionMode" :matrix="workspace.matrix || []" :busy="Boolean(acting)" @submit="submitAction" />
		<ProductionOrderLotOcrDialog v-model:visible="lotOcrVisible" :production-order="workspace.record?.name || ''" :lot="selectedLot" :item="workspace.record?.item || ''" />
		<DocumentConfirmationDialog v-model:visible="confirmVisible" :title="confirmTitle" :message="confirmMessage" :confirm-label="confirmLabel" :busy="Boolean(acting)" @confirm="confirmAction" />
	</DepartmentPage>
</template>

<script setup>
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { executeProductionOrderCommand, getProductionOrderWorkspace } from "../../api/sales.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../fabric-store/FabricDocumentWorkspace.vue"
import ProductionOrderActionDialog from "./ProductionOrderActionDialog.vue"
import ProductionOrderLotOcrDialog from "./ProductionOrderLotOcrDialog.vue"
import ProductionOrderMatrix from "./ProductionOrderMatrix.vue"
import ProductionOrderOverview from "./ProductionOrderOverview.vue"
import ProductionOrderTransferHistory from "./ProductionOrderTransferHistory.vue"

const route = useRoute()
const router = useRouter()
const workspace = ref({})
const loading = ref(true)
const error = ref("")
const acting = ref("")
const activeTab = ref("details")
const actionVisible = ref(false)
const actionMode = ref("")
const lotOcrVisible = ref(false)
const selectedLot = ref("")
const confirmVisible = ref(false)
const pendingConfirm = ref("")
let loadSequence = 0

const dialogModes = new Set(["request_changes", "update_price", "change_dates", "change_status", "update_quantity_ratio", "transfer_quantity", "create_lot", "link_lot"])
const iconMap = { save: "pi pi-pencil", request_ppo_approval: "pi pi-send", approve_ppo: "pi pi-check-circle", request_changes: "pi pi-undo", update_price: "pi pi-indian-rupee", change_dates: "pi pi-calendar", change_status: "pi pi-sync", update_quantity_ratio: "pi pi-sliders-h", approve_quantity_ratio: "pi pi-check", approve_status: "pi pi-check", transfer_quantity: "pi pi-arrow-right-arrow-left", approve_transfer: "pi pi-check", create_lot: "pi pi-plus", link_lot: "pi pi-link", reopen: "pi pi-lock-open", cancel: "pi pi-ban", delete: "pi pi-trash", amend: "pi pi-copy" }
const priority = ["approve_ppo", "request_ppo_approval", "approve_quantity_ratio", "approve_status", "approve_transfer", "save", "update_quantity_ratio", "update_price", "change_dates", "change_status", "transfer_quantity", "create_lot", "link_lot", "reopen", "request_changes", "cancel", "amend", "delete"]
const actions = computed(() => priority.flatMap((key) => {
	const capability = workspace.value.capabilities?.[key]
	if (!capability?.allowed) return []
	return [{ key, label: capability.label, icon: iconMap[key], primary: key === priority.find((candidate) => workspace.value.capabilities?.[candidate]?.allowed), menuOnly: ["cancel", "delete", "amend", "reopen", "create_lot", "link_lot"].includes(key), command: () => beginAction(key) }]
}))
const dateActivity = computed(() => (workspace.value.histories?.dates || []).map((row, index) => ({
	key: `date-${index}`,
	label: row.date_field || "Date changed",
	value: `${formatDate(row.previous_date || row.old_date)} → ${formatDate(row.new_date)}${row.reason ? ` · ${row.reason}` : ""}`,
})))
const confirmTitle = computed(() => ({ cancel: "Cancel Production Order?", delete: "Delete Production Order?", amend: "Create an amendment?", approve_ppo: "Approve this PPO?", approve_quantity_ratio: "Approve quantity & ratio?", approve_status: "Approve status change?", approve_transfer: "Approve quantity transfer?", reopen: "Reopen Production Order?", request_ppo_approval: "Send for PPO approval?" }[pendingConfirm.value] || "Confirm action"))
const confirmLabel = computed(() => workspace.value.capabilities?.[pendingConfirm.value]?.label || "Continue")
const confirmMessage = computed(() => `${confirmLabel.value} for ${workspace.value.record?.name || "this Production Order"}? Existing workflow validations will be applied.`)

async function load(refresh = false) {
	const id = String(route.params.productionOrderId || "")
	const sequence = ++loadSequence
	if (!refresh) { loading.value = true; workspace.value = {} }
	else acting.value = "reload"
	error.value = ""
	try {
		const payload = await getProductionOrderWorkspace(id) || {}
		if (sequence === loadSequence && id === String(route.params.productionOrderId || "")) workspace.value = payload
	} catch (reason) { if (sequence === loadSequence) error.value = reason?.message || "Unable to load this Production Order." }
	finally { if (sequence === loadSequence) { loading.value = false; acting.value = "" } }
}
function openLotOcr(lot) { selectedLot.value = lot; lotOcrVisible.value = true }
function beginAction(command) {
	if (command === "save") return router.push({ name: "sales-production-order-edit", params: { productionOrderId: workspace.value.record.name }, state: preserveListNavigationState(workspace.value.record.name, workspace.value.record.modified) })
	if (dialogModes.has(command)) { actionMode.value = command; actionVisible.value = true; return }
	pendingConfirm.value = command; confirmVisible.value = true
}
async function submitAction(payload) { actionVisible.value = false; await runCommand(actionMode.value, payload) }
async function confirmAction() { const command = pendingConfirm.value; confirmVisible.value = false; pendingConfirm.value = ""; if (command) await runCommand(command) }
async function runCommand(command, payload = {}) {
	const source = workspace.value.record
	acting.value = command; error.value = ""
	try {
		const result = await executeProductionOrderCommand(source.name, command, payload, source.modified) || {}
		if (result.deleted) { await router.replace({ name: "sales-production-orders" }); return }
		workspace.value = result
		const name = result.record?.name || source.name
		if (name !== route.params.productionOrderId) await router.replace({ name: "sales-production-order", params: { productionOrderId: name }, state: preserveListNavigationState(name) })
	} catch (reason) { error.value = reason?.message || `Unable to ${command.replaceAll("_", " ")} this Production Order.` }
	finally { acting.value = "" }
}
function statusLabel(docstatus) { return Number(docstatus) === 1 ? "Submitted" : Number(docstatus) === 2 ? "Cancelled" : "Draft" }
function formatNumber(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function formatDate(value) { if (!value) return "—"; const [year, month, day] = String(value).slice(0, 10).split("-"); return day ? `${day}-${month}-${year}` : value }
watch(() => route.params.productionOrderId, () => { lotOcrVisible.value = false; selectedLot.value = ""; load(false) }, { immediate: true })
</script>

<style scoped>
.ppo-page-frame { width: 100%; max-width: 1840px; min-width: 0; margin: 0 auto var(--erp-space-3); padding: 0 clamp(2px, .7vw, 10px); }
.ppo-page__identity { display: flex; min-width: 0; align-items: center; gap: 12px; padding-block: 4px; }
.ppo-page__title { display: grid; min-width: 0; gap: 2px; }
.ppo-page__title > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .035em; text-transform: uppercase; }
.ppo-page__title h1 { max-width: min(980px, 70vw); margin: 0; overflow: hidden; color: var(--erp-text); font-size: clamp(19px, 1.45vw, 24px); letter-spacing: -.025em; text-overflow: ellipsis; white-space: nowrap; }
.ppo-page__metric { display: grid; min-height: 72px; align-content: center; gap: 3px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); }
.ppo-page__metric span, .ppo-page__metric small, .ppo-page__lots > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .035em; text-transform: uppercase; }
.ppo-page__metric strong { color: var(--erp-accent-hover); font-size: 19px; font-variant-numeric: tabular-nums; }
.ppo-page__lots { display: grid; gap: 5px; padding: 12px 13px; }
.ppo-page__lots strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.ppo-tabs :deep(.p-tablist-tab-list) { padding-inline: 2px; }
.ppo-tabs :deep(.p-tab span) { margin-left: 5px; padding: 2px 6px; color: var(--erp-text-muted); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.ppo-tabs :deep(.p-tabpanels) { padding: 12px 0 0; background: transparent; }
.ppo-details { display: grid; min-width: 0; gap: 12px; }
.ppo-activity { overflow: hidden; border-color: var(--erp-border); }
.ppo-activity > header { padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.ppo-activity > header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 740; letter-spacing: .05em; }
.ppo-activity h2 { margin: 2px 0 0; font-size: 15px; }
.ppo-activity > div { display: grid; grid-template-columns: minmax(150px, .35fr) 1fr; gap: 10px; padding: 9px 13px; border-bottom: 1px solid var(--erp-border); font-size: var(--erp-font-size-caption); }
.ppo-activity > div:last-child { border-bottom: 0; }
.ppo-activity > div span { color: var(--erp-text-secondary); }
</style>
