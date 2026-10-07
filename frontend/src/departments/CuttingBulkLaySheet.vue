<template>
	<DepartmentPage title="Bulk LaySheets" accent="#059669" back-to="/cutting/bulk-lay-sheets" back-label="Bulk LaySheets" :show-title="false" flat full-width>
		<div class="bulk-workspace erp-workspace">
			<div v-if="loading && !workspace.record" class="bulk-workspace__loading"><Skeleton height="76px" /><Skeleton height="560px" /></div>
			<template v-else>
				<header class="bulk-record-header erp-card">
					<div class="bulk-record-identity">
						<div class="bulk-record-title"><h1>Bulk LaySheets</h1><span>{{ bulkName }}</span></div>
						<div class="bulk-record-meta">
							<Tag :value="record.status || 'Setup'" :severity="statusSeverity(record.status)" rounded />
							<span class="bulk-header-fact bulk-header-fact--lot" :title="record.main_lot || 'No Main Lot'"><small>Main Lot</small><strong>{{ record.main_lot || "—" }}</strong></span>
							<span class="bulk-header-fact bulk-header-fact--location" :title="record.from_location || 'No Location'"><small>Location</small><strong>{{ record.from_location || "—" }}</strong></span>
						</div>
					</div>
					<div class="bulk-record-header__actions">
						<Button v-if="workspace.permissions?.can_write && !workspace.setup_locked" label="Edit Setup" icon="pi pi-pencil" severity="secondary" outlined size="small" @click="editSetupOpen = true" />
						<BulkActions :actions="workspace.bulk_actions" :busy="busy" @action="runBulkAction" />
						<Button icon="pi pi-refresh" aria-label="Refresh Bulk LaySheets" severity="secondary" text rounded :loading="loading" @click="loadWorkspace" />
					</div>
				</header>
				<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
				<Message v-if="feedback" severity="success" closable @close="feedback = ''">{{ feedback }}</Message>
				<section class="bulk-setup-summary erp-card" aria-label="Bulk setup summary"><div v-for="item in setupSummary" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value || "—" }}</strong></div></section>
				<div class="bulk-workspace-layout">
					<main class="bulk-workspace-main">
						<div class="bulk-workspace-main__scroll">
							<BulkActiveLaySheet ref="activeEditor" :bulk-name="bulkName" :row="activeRow" :data="workspace.active_laysheet" :modified="workspace.active_laysheet?.context?.modified" :can-write="workspace.permissions?.laysheet?.can_write" @saved="applyWorkspace" />
							<BulkBundleTable :rows="workspace.bundles || []" />
						</div>
					</main>
					<BulkWorkflowRail :rows="workspace.rows || []" :active-lay-sheet="record.active_cutting_laysheet" :busy="busy" @select="selectRow" @action="runRowAction" />
				</div>
			</template>
		</div>
	</DepartmentPage>

	<Dialog v-model:visible="editSetupOpen" modal dismissable-mask maximizable header="Edit Bulk Setup" class="bulk-setup-dialog"><BulkSetupEditor :name="bulkName" @saved="setupSaved" @cancel="editSetupOpen = false" /></Dialog>

	<Dialog v-model:visible="generateOpen" modal dismissable-mask :header="`Generate Bundles · ${actionRow?.lot || ''}`" class="bulk-generate-dialog">
		<div class="generate-form">
			<Message v-if="dialogError" severity="error" :closable="false">{{ dialogError }}</Message>
			<DateField v-model="generation.bundle_generated_date" label="Bundle Generated Date" required />
			<div class="generate-form__numbers"><label><span>Maximum No of Plys</span><InputNumber v-model="generation.maximum_no_of_plys" :min="1" fluid /></label><label><span>Maximum Allow Percent</span><InputNumber v-model="generation.maximum_allow_percentage" :min="0" suffix="%" fluid /></label></div>
			<div class="generate-table-wrap"><table><thead><tr><th>Panel</th><th>Bundle Group</th></tr></thead><tbody><tr v-for="item in generation.groups" :key="item.part"><td>{{ item.part }}</td><td><InputNumber v-model="item.value" :min="1" fluid /></td></tr></tbody></table></div>
		</div>
		<template #footer><Button label="Close" severity="secondary" text :disabled="busy === 'generate'" @click="generateOpen = false" /><Button label="Generate Bundles" icon="pi pi-box" :loading="busy === 'generate'" :disabled="!generation.bundle_generated_date || !generation.groups.length" @click="generate" /></template>
	</Dialog>

	<BulkDeliveryDialog v-model:visible="deliveryOpen" :bulk-name="bulkName" :row="actionRow" :bulk-mode="bulkDelivery" @saved="actionSaved($event, bulkDelivery ? 'Delivery Challans created.' : 'Delivery Challan created and submitted.')" />
	<BulkPrintDialog v-model:visible="printOpen" :bulk-name="bulkName" :row="actionRow" @printed="actionSaved($event, 'Labels printed successfully.')" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tag from "primevue/tag"
import { computed, reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"

import {
	activateBulkLaySheet, approveBulkGrammage, createBulkLaySheets, createBulkRowTransfer,
	createSharedBulkTransfer, generateBulkBundles, getBulkLaySheetsWorkspace, getBulkMarkerParts,
	submitBulkRowDelivery, submitBulkRowTransfer, submitSharedBulkTransfer,
} from "../api/cuttingBulkLaySheets.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import DateField from "../components/common/DateField.vue"
import { useActionConfirmation } from "../utils/useActionConfirmation.js"
import BulkActions from "./cutting/bulk/BulkActions.vue"
import BulkActiveLaySheet from "./cutting/bulk/BulkActiveLaySheet.vue"
import BulkBundleTable from "./cutting/bulk/BulkBundleTable.vue"
import BulkDeliveryDialog from "./cutting/bulk/BulkDeliveryDialog.vue"
import BulkPrintDialog from "./cutting/bulk/BulkPrintDialog.vue"
import BulkSetupEditor from "./cutting/bulk/BulkSetupEditor.vue"
import BulkWorkflowRail from "./cutting/bulk/BulkWorkflowRail.vue"

const route = useRoute()
const confirmAction = useActionConfirmation()
const bulkName = computed(() => String(route.params.bulkLaySheetsId || ""))
const workspace = ref({})
const loading = ref(true)
const error = ref("")
const feedback = ref("")
const busy = ref("")
const activeEditor = ref(null)
const editSetupOpen = ref(false)
const generateOpen = ref(false)
const deliveryOpen = ref(false)
const bulkDelivery = ref(false)
const printOpen = ref(false)
const actionRow = ref(null)
const dialogError = ref("")
const generation = reactive({ bundle_generated_date: today(), maximum_no_of_plys: null, maximum_allow_percentage: null, groups: [] })
let loadSequence = 0
const record = computed(() => workspace.value.record || {})
const activeRow = computed(() => (workspace.value.rows || []).find((row) => row.cutting_laysheet === record.value.active_cutting_laysheet) || null)
const setupSummary = computed(() => [
	{ label: "Posting Date", value: formatDate(record.value.posting_date) }, { label: "Cutting Spreader", value: record.value.cutting_spreader }, { label: "Cutter", value: record.value.cutter },
])

async function loadWorkspace() {
	const sequence = ++loadSequence; loading.value = true; error.value = ""
	try { const payload = await getBulkLaySheetsWorkspace(bulkName.value); if (sequence === loadSequence) workspace.value = payload || {} }
	catch (reason) { if (sequence === loadSequence) error.value = reason?.message || "Unable to load Bulk LaySheets." }
	finally { if (sequence === loadSequence) loading.value = false }
}
function applyWorkspace(payload) { workspace.value = payload?.workspace || payload || workspace.value }
async function persistActive() { await activeEditor.value?.saveIfDirty?.() }
async function selectRow(row) {
	if (!row.cutting_laysheet || row.cutting_laysheet === record.value.active_cutting_laysheet) return
	busy.value = `select:${row.name}`; error.value = ""
	try { await persistActive(); applyWorkspace(await activateBulkLaySheet(bulkName.value, row.cutting_laysheet)) }
	catch (reason) { error.value = reason?.message || "Unable to open the selected LaySheet." }
	finally { busy.value = "" }
}
async function withAction(key, action, success) {
	busy.value = key; error.value = ""; feedback.value = ""
	try { await persistActive(); const payload = await action(); applyWorkspace(payload); feedback.value = success }
	catch (reason) { error.value = reason?.message || "Unable to complete the workflow action." }
	finally { busy.value = "" }
}
async function runBulkAction(action) {
	if (action === "create-laysheets") return withAction(action, () => createBulkLaySheets(bulkName.value), "LaySheets created.")
	if (action === "create-bulk-transfer") return withAction(action, () => createSharedBulkTransfer(bulkName.value), "Bulk Lot Transfer created.")
	if (action === "submit-bulk-transfer") return confirmAction({
		header: "Submit shared Lot Transfer?",
		message: "Submit the shared Lot Transfer? This finalizes the document.",
		acceptLabel: "Submit Transfer",
		rejectLabel: "Keep Draft",
		acceptSeverity: "primary",
		acceptIcon: "pi pi-check",
		accept: () => withAction(action, () => submitSharedBulkTransfer(bulkName.value), "Bulk Lot Transfer submitted."),
	})
	if (action === "create-bulk-dc") { await persistActive(); actionRow.value = null; bulkDelivery.value = true; deliveryOpen.value = true }
}
async function runRowAction({ action, row }) {
	actionRow.value = row
	if (action === "generate") return openGenerate(row)
	if (action === "create-transfer") return withAction(`${action}:${row.name}`, () => createBulkRowTransfer(bulkName.value, row.name), `Lot Transfer created for ${row.lot}.`)
	if (action === "submit-transfer") return confirmAction({
		header: "Submit Lot Transfer?",
		message: `Submit Lot Transfer ${row.lot_transfer}? This finalizes the document.`,
		acceptLabel: "Submit Transfer",
		rejectLabel: "Keep Draft",
		acceptSeverity: "primary",
		acceptIcon: "pi pi-check",
		accept: () => withAction(`${action}:${row.name}`, () => submitBulkRowTransfer(bulkName.value, row.name), `Lot Transfer submitted for ${row.lot}.`),
	})
	if (action === "create-dc") { await persistActive(); bulkDelivery.value = false; deliveryOpen.value = true; return }
	if (action === "submit-dc") return confirmAction({
		header: "Submit Delivery Challan?",
		message: `Submit Delivery Challan ${row.delivery_challan}? This finalizes the document.`,
		acceptLabel: "Submit Delivery Challan",
		rejectLabel: "Keep Draft",
		acceptSeverity: "primary",
		acceptIcon: "pi pi-check",
		accept: () => withAction(`${action}:${row.name}`, () => submitBulkRowDelivery(bulkName.value, row.name), `Delivery Challan submitted for ${row.lot}.`),
	})
	if (action === "approve") return withAction(`${action}:${row.name}`, () => approveBulkGrammage(bulkName.value, row.name), `Grammage approved for ${row.lot}.`)
	if (action === "print") { await persistActive(); printOpen.value = true }
}
async function openGenerate(row) {
	dialogError.value = ""; busy.value = `generate-open:${row.name}`
	try {
		await persistActive()
		if (row.cutting_laysheet !== record.value.active_cutting_laysheet) applyWorkspace(await activateBulkLaySheet(bulkName.value, row.cutting_laysheet))
		actionRow.value = row
		generation.bundle_generated_date = today(); generation.maximum_no_of_plys = null; generation.maximum_allow_percentage = null
		generation.groups = (await getBulkMarkerParts(row.cutting_marker) || []).map((item) => ({ part: item.part, value: Number(item.value || 1) }))
		generateOpen.value = true
	} catch (reason) { error.value = reason?.message || "Unable to prepare bundle generation." }
	finally { busy.value = "" }
}
async function generate() {
	busy.value = "generate"; dialogError.value = ""
	try { const payload = await generateBulkBundles(bulkName.value, actionRow.value.name, generation); applyWorkspace(payload); generateOpen.value = false; feedback.value = `Bundles generated for ${actionRow.value.lot}.` }
	catch (reason) { dialogError.value = reason?.message || "Unable to generate bundles." }
	finally { busy.value = "" }
}
function actionSaved(payload, message) { applyWorkspace(payload); feedback.value = message }
function setupSaved(payload) { applyWorkspace(payload); editSetupOpen.value = false; feedback.value = "Bulk setup updated." }
function today() { const value = new Date(); const pad = (part) => String(part).padStart(2, "0"); return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}` }
function formatDate(value) { if (!value) return ""; const [year, month, day] = String(value).split("-"); return day && month && year ? `${day}-${month}-${year}` : value }
function statusSeverity(status) { if (status === "Completed") return "success"; if (status === "Ready to Print") return "info"; if (["Lay Sheets Created", "In Progress"].includes(status)) return "warn"; return "secondary" }
watch(bulkName, loadWorkspace, { immediate: true })
</script>

<style scoped>
.bulk-workspace { display: flex; width: 100%; max-width: 1900px; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 82px); margin: 0 auto; flex-direction: column; gap: 10px; }.bulk-workspace__loading { display: grid; gap: 10px; }
.bulk-record-header { display: flex; min-height: 66px; padding: 11px 14px; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }.bulk-record-identity, .bulk-record-header__actions, .bulk-record-meta { display: flex; align-items: center; gap: 10px; }.bulk-record-title { display: grid; gap: 3px; min-width: 0; }.bulk-record-identity h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -.025em; }.bulk-record-title > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 600; }.bulk-header-fact { display: grid; min-width: 106px; max-width: 220px; gap: 2px; padding-left: 11px; border-left: 1px solid var(--erp-border); }.bulk-header-fact small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .035em; line-height: 1; text-transform: uppercase; }.bulk-header-fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 730; text-overflow: ellipsis; white-space: nowrap; }
.bulk-setup-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); overflow: hidden; }.bulk-setup-summary > div { display: grid; min-width: 0; padding: 9px 12px; gap: 2px; border-right: 1px solid var(--erp-border); }.bulk-setup-summary > div:last-child { border-right: 0; }.bulk-setup-summary span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 680; text-transform: uppercase; }.bulk-setup-summary strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.bulk-workspace-layout { display: grid; min-height: 0; height: calc(100dvh - var(--erp-shell-header-height) - 296px); grid-template-columns: minmax(0, 4fr) minmax(280px, 1fr); gap: 10px; }.bulk-workspace-main { min-width: 0; min-height: 0; overflow: hidden; }.bulk-workspace-main__scroll { display: grid; height: 100%; padding-right: 2px; overflow-y: auto; align-content: start; gap: 10px; }
.generate-form { display: grid; width: min(640px, calc(100vw - 64px)); gap: 13px; }.generate-form__numbers { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.generate-form label { display: grid; gap: 6px; }.generate-form label span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }.generate-table-wrap { max-height: 310px; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }.generate-table-wrap table { width: 100%; border-collapse: collapse; }.generate-table-wrap th, .generate-table-wrap td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--erp-border); }.generate-table-wrap th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface-muted); }.generate-table-wrap tr:last-child td { border-bottom: 0; }
:deep(.bulk-setup-dialog) { width: min(1260px, calc(100vw - 32px)); }:deep(.bulk-setup-dialog .p-dialog-content) { padding: 0; }
@media (max-width: 1100px) { .bulk-workspace-layout { height: auto; grid-template-columns: 1fr; }.bulk-workflow-rail { max-height: 520px; } }
@media (max-width: 850px) { .bulk-record-header { align-items: flex-start; flex-direction: column; }.bulk-record-header__actions { flex-wrap: wrap; } }
@media (max-width: 700px) { .bulk-record-identity { align-items: flex-start; flex-direction: column; }.bulk-record-meta { flex-wrap: wrap; }.bulk-header-fact:first-of-type { padding-left: 0; border-left: 0; }.bulk-setup-summary { grid-template-columns: 1fr; }.bulk-setup-summary > div { border-right: 0; border-bottom: 1px solid var(--erp-border); }.bulk-setup-summary > div:last-child { border-bottom: 0; }.generate-form__numbers { grid-template-columns: 1fr; } }
</style>
