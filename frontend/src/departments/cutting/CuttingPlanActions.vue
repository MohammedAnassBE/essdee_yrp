<template>
	<div v-if="hasActions" class="plan-actions" role="group" aria-label="Cutting Plan actions">
		<Button
			class="plan-actions-trigger"
			label="More Actions"
			icon="pi pi-chevron-down"
			icon-pos="right"
			severity="secondary"
			outlined
			:loading="Boolean(busy)"
			aria-haspopup="menu"
			aria-controls="cutting-plan-more-actions"
			:aria-expanded="moreActionsOpen"
			@click="toggleMoreActions"
		/>
		<Menu
			id="cutting-plan-more-actions"
			ref="moreActionsMenu"
			:model="moreActionItems"
			popup
			:base-z-index="5000"
			class="plan-actions-menu"
			@show="moreActionsOpen = true"
			@hide="moreActionsOpen = false"
		/>
	</div>

	<Teleport to="body">
		<Message v-if="feedback" class="plan-action-feedback" :severity="feedbackSeverity" :closable="true" @close="feedback = ''">{{ feedback }}</Message>
	</Teleport>

	<Dialog v-model:visible="completedReportOpen" modal dismissable-mask maximizable header="Completed Cut Quantity" class="action-dialog action-dialog--wide completed-report-dialog">
		<div ref="completedReportCapture" class="completed-report-capture">
			<CuttingCompletedReport
				:doc="doc"
				:groups="data.completed_items"
				:generated-at="completedReportGeneratedAt"
			/>
		</div>
		<div
			v-if="completedCopyFeedback"
			class="completed-copy-feedback"
			:class="{ 'completed-copy-feedback--error': completedCopyError }"
			role="status"
			aria-live="polite"
		>
			<i :class="completedCopyError ? 'pi pi-exclamation-circle' : 'pi pi-check-circle'" aria-hidden="true" />
			{{ completedCopyFeedback }}
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="completedReportOpen = false" />
			<Button label="Copy" icon="pi pi-copy" :loading="copyingCompleted" @click="copyCompletedReport" />
		</template>
	</Dialog>

	<Dialog v-model:visible="completedOpen" modal dismissable-mask maximizable header="Update Completed Cut Quantity" class="action-dialog action-dialog--wide">
		<div class="dialog-stack">
			<div v-for="(group, groupIndex) in completedDraft" :key="groupIndex" class="dialog-table-wrap">
				<div v-if="panelNames(group).length" class="panel-note"><strong>Panels</strong> {{ panelNames(group).join(", ") }}</div>
				<div class="table-scroll" role="region" tabindex="0" :aria-label="`Completed cut quantity group ${groupIndex + 1}`">
					<table class="action-table">
						<thead><tr><th>S.No.</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="size in group.primary_attribute_values || []" :key="size">{{ size }}</th><th>Completed</th></tr></thead>
						<tbody><tr v-for="(row, rowIndex) in group.items || []" :key="rowIndex"><td>{{ rowIndex + 1 }}</td><td v-for="attribute in group.attributes || []" :key="attribute">{{ row.attributes?.[attribute] || '—' }}</td><td v-for="size in group.primary_attribute_values || []" :key="size">{{ quantity(row.values?.[size]) }}</td><td><Checkbox v-model="row.completed" binary :aria-label="`Mark completed cut quantity row ${rowIndex + 1} in group ${groupIndex + 1}`" /></td></tr></tbody>
					</table>
				</div>
			</div>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="completedOpen = false" />
			<Button label="Save Completed" icon="pi pi-check" :loading="busy === 'completed'" @click="saveCompleted" />
		</template>
	</Dialog>

	<Dialog v-model:visible="recutOpen" modal dismissable-mask :header="recutType === 'Print Panel' ? 'Add Print Panel Details' : 'Add Recut Fabric Details'" class="action-dialog action-dialog--wide">
		<div class="dialog-stack">
			<div class="recut-form">
				<label><span>Cloth Type</span><Select v-model="recutForm.cloth_type" :options="recutOptions.cloth_type" fluid /></label>
				<label><span>Colour</span><Select v-model="recutForm.colour" :options="recutOptions.colour" filter fluid /></label>
				<label><span>Dia</span><Select v-model="recutForm.dia" :options="recutOptions.dia" filter fluid /></label>
				<label><span>Shade</span><InputText v-model="recutForm.shade" fluid /></label>
				<label><span>Weight in Kg</span><InputNumber v-model="recutForm.weight" :min="0" :max-fraction-digits="3" fluid /></label>
				<label><span>No of Rolls</span><InputNumber v-model="recutForm.no_of_rolls" :min="0" fluid /></label>
				<label v-if="recutType === 'Print Panel'"><span>Panel Count</span><InputNumber v-model="recutForm.panel_count" :min="0" fluid /></label>
				<div class="recut-form__button"><Button label="Add Item" icon="pi pi-plus" outlined @click="addRecutRow" /></div>
			</div>
			<div v-if="recutRows.length" class="table-scroll" role="region" tabindex="0" :aria-label="recutType === 'Print Panel' ? 'Print panel rows' : 'Recut fabric rows'">
				<table class="action-table"><thead><tr><th>S.No.</th><th>Cloth Type</th><th>Colour</th><th>Dia</th><th>Shade</th><th>Weight</th><th>Rolls</th><th v-if="recutType === 'Print Panel'">Panel Count</th><th></th></tr></thead><tbody><tr v-for="(row, index) in recutRows" :key="index"><td>{{ index + 1 }}</td><td>{{ row.cloth_type }}</td><td>{{ row.colour }}</td><td>{{ row.dia }}</td><td>{{ row.shade }}</td><td>{{ row.weight }}</td><td>{{ row.no_of_rolls }}</td><td v-if="recutType === 'Print Panel'">{{ row.panel_count }}</td><td><Button icon="pi pi-trash" severity="danger" text rounded aria-label="Remove row" @click="recutRows.splice(index, 1)" /></td></tr></tbody></table>
			</div>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="recutOpen = false" />
			<Button :label="recutType === 'Print Panel' ? 'Create Print Panel' : 'Create Recut'" icon="pi pi-check" :disabled="!recutRows.length" :loading="busy === 'recut'" @click="saveRecut" />
		</template>
	</Dialog>

	<Dialog v-model:visible="lotTransferOpen" modal dismissable-mask header="Create Lot Transfer" class="action-dialog action-dialog--small">
		<div class="dialog-stack">
			<label class="dialog-field"><span>Target Lot</span><LinkField v-model="targetLot" doctype="SD YRP Lot" :filters="{ name: ['!=', doc.lot] }" /></label>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="lotTransferOpen = false" />
			<Button label="Create Lot Transfer" icon="pi pi-arrow-right-arrow-left" :disabled="!targetLot" :loading="busy === 'transfer'" @click="saveLotTransfer" />
		</template>
	</Dialog>

	<Dialog v-model:visible="approvalOpen" modal dismissable-mask header="Change Approval Grammage" class="action-dialog action-dialog--small">
		<div class="dialog-stack">
			<label class="dialog-field"><span>Grammage Allowance (kg)</span><InputNumber v-model="approvalTolerance" :min="0.0001" :min-fraction-digits="4" :max-fraction-digits="4" fluid /></label>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="approvalOpen = false" />
			<Button label="Update" icon="pi pi-check" :disabled="!approvalTolerance" :loading="busy === 'approval'" @click="saveApproval" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="dialogError" title="Cutting Plan action failed" @dismiss="dialogError = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Menu from "primevue/menu"
import Message from "primevue/message"
import Select from "primevue/select"
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"

import { callMethod } from "../../api/frappe.js"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import CuttingCompletedReport from "./CuttingCompletedReport.vue"
import { copyElementAsImage } from "../../components/reports/copyElementAsImage.js"

const props = defineProps({
	doc: { type: Object, required: true },
	data: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["refresh"])

const permissions = computed(() => props.data.permissions || {})
const busy = ref("")
const feedback = ref("")
const feedbackSeverity = ref("success")
let feedbackTimer
watch(feedback, (message) => {
	window.clearTimeout(feedbackTimer)
	if (message) feedbackTimer = window.setTimeout(() => { feedback.value = "" }, 4000)
})
onBeforeUnmount(() => window.clearTimeout(feedbackTimer))
const dialogError = ref("")
const completedReportOpen = ref(false)
const completedReportGeneratedAt = ref("")
const completedReportCapture = ref(null)
const copyingCompleted = ref(false)
const completedCopyFeedback = ref("")
const completedCopyError = ref(false)
const completedOpen = ref(false)
const completedDraft = ref([])
const recutOpen = ref(false)
const recutType = ref("Recut")
const recutRows = ref([])
const recutOptions = reactive({ cloth_type: [], colour: [], dia: [] })
const recutForm = reactive(emptyRecutForm())
const lotTransferOpen = ref(false)
const targetLot = ref("")
const approvalOpen = ref(false)
const approvalTolerance = ref(0)
const moreActionsMenu = ref(null)
const moreActionsOpen = ref(false)
const moreActionItems = computed(() => {
	const disabled = Boolean(busy.value)
	const groups = [
		permissions.value.can_run_plan_actions ? [
			{ label: "Generate", icon: "pi pi-play", disabled, command: () => runPlanAction("generate") },
			{ label: "Fetch Received Cloth", icon: "pi pi-download", disabled, command: () => runPlanAction("fetch") },
			{ label: "Calculate LaySheets", icon: "pi pi-calculator", disabled, command: () => runPlanAction("calculate") },
		] : [],
		[
			{ label: "Get Completed", icon: "pi pi-chart-bar", disabled, command: openCompletedReport },
			permissions.value.can_update_completed
				? { label: "Update Completed", icon: "pi pi-check-square", disabled, command: openCompleted }
				: null,
		].filter(Boolean),
		[
			permissions.value.can_create_recut
				? { label: "Update Recut", icon: "pi pi-replay", disabled, command: () => openRecut("Recut") }
				: null,
			permissions.value.can_create_recut
				? { label: "Update Print Panel", icon: "pi pi-print", disabled, command: () => openRecut("Print Panel") }
				: null,
			permissions.value.can_create_lot_transfer
				? { label: "Lot Transfer", icon: "pi pi-arrow-right-arrow-left", disabled, command: () => { lotTransferOpen.value = true } }
				: null,
			permissions.value.can_change_approval_grammage
				? { label: "Approval", icon: "pi pi-shield", disabled, command: openApproval }
				: null,
		].filter(Boolean),
	].filter((group) => group.length)

	return groups.flatMap((group, index) => index ? [{ separator: true }, ...group] : group)
})
const hasActions = computed(() => moreActionItems.value.some((item) => !item.separator))

const planActions = {
	generate: ["get_cloth1", "cutting_plan", "Cloth details generated."],
	fetch: ["fetch_received_cloth", "docname", "Received cloth refreshed."],
	calculate: ["calculate_laysheets", "cutting_plan", "LaySheet calculation queued."],
}

async function runPlanAction(action) {
	const [method, nameArgument, success] = planActions[action]
	const args = { [nameArgument]: props.doc.name }
	busy.value = action
	clearFeedback()
	try {
		await callMethod(planMethod(method), args)
		showFeedback(success)
		emit("refresh")
	} catch (reason) {
		dialogError.value = reason.message || "Unable to complete the action."
	} finally {
		busy.value = ""
	}
}

function openCompletedReport() {
	completedReportGeneratedAt.value = formatCompletionTimestamp(new Date())
	completedCopyFeedback.value = ""
	completedCopyError.value = false
	completedReportOpen.value = true
}

async function copyCompletedReport() {
	if (copyingCompleted.value) return
	copyingCompleted.value = true
	completedCopyFeedback.value = ""
	completedCopyError.value = false
	let exportCapture = null
	try {
		exportCapture = createCompletedReportExport(completedReportCapture.value)
		await new Promise((resolve) => window.requestAnimationFrame(resolve))
		await copyElementAsImage(exportCapture.element)
		completedCopyFeedback.value = "Completed quantities copied to clipboard."
	} catch (reason) {
		dialogError.value = reason?.message || "Unable to copy the completed quantities."
	} finally {
		exportCapture?.host.remove()
		copyingCompleted.value = false
	}
}

function createCompletedReportExport(source) {
	if (!source) throw new Error("Nothing available to copy.")
	const tableWidths = Array.from(source.querySelectorAll(".completed-report__table-wrap"), (element) => element.scrollWidth)
	const exportWidth = Math.max(source.clientWidth, source.scrollWidth, ...tableWidths)
	const clone = source.cloneNode(true)
	const host = document.createElement("div")
	clone.classList.add("completed-report-capture--export")
	Object.assign(clone.style, {
		width: `${exportWidth}px`,
		maxWidth: "none",
	})
	clone.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"))
	clone.querySelectorAll("[aria-labelledby]").forEach((element) => element.removeAttribute("aria-labelledby"))
	clone.querySelectorAll(".completed-report__table-wrap").forEach((element) => {
		element.style.overflow = "visible"
	})
	host.className = "completed-report-export-host"
	host.setAttribute("aria-hidden", "true")
	Object.assign(host.style, {
		position: "fixed",
		left: "-100000px",
		top: "0",
		width: `${exportWidth}px`,
		pointerEvents: "none",
	})
	host.appendChild(clone)
	;(document.querySelector(".app-shell") || document.body).appendChild(host)
	return { element: clone, host }
}

function formatCompletionTimestamp(value) {
	const pad = (part) => String(part).padStart(2, "0")
	return `${pad(value.getDate())}-${pad(value.getMonth() + 1)}-${value.getFullYear()} · ${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
}

function openCompleted() {
	completedDraft.value = clone(normaliseGroups(props.data.completed_items))
	completedOpen.value = true
}

async function saveCompleted() {
	busy.value = "completed"
	try {
		await callMethod(planMethod("update_web_completed_items"), {
			cutting_plan: props.doc.name,
			completed_items: completedDraft.value,
		})
		completedOpen.value = false
		showFeedback("Completed quantities updated.")
		emit("refresh")
	} catch (reason) {
		dialogError.value = reason.message || "Unable to update completed quantities."
	} finally {
		busy.value = ""
	}
}

async function openRecut(type) {
	recutType.value = type
	recutRows.value = []
	Object.assign(recutForm, emptyRecutForm())
	dialogError.value = ""
	recutOpen.value = true
	try {
		const options = await callMethod(laysheetMethod("get_select_attributes"), { cutting_plan: props.doc.name })
		recutOptions.cloth_type = Array.from(options?.cloth_type || [])
		recutOptions.colour = Array.from(options?.colour || [])
		recutOptions.dia = Array.from(options?.dia || [])
	} catch (reason) {
		dialogError.value = reason.message || "Unable to load cloth options."
	}
}

function addRecutRow() {
	dialogError.value = ""
	const required = ["cloth_type", "colour", "dia", "shade", "weight", "no_of_rolls"]
	if (recutType.value === "Print Panel") required.push("panel_count")
	if (required.some((key) => recutForm[key] === null || recutForm[key] === undefined || recutForm[key] === "")) {
		dialogError.value = "Enter all values before adding the item."
		return
	}
	recutRows.value.push({ ...recutForm })
	Object.assign(recutForm, emptyRecutForm())
}

async function saveRecut() {
	busy.value = "recut"
	dialogError.value = ""
	try {
		await callMethod(planMethod("create_recut_print_panel"), {
			cutting_plan: props.doc.name,
			type: recutType.value,
			item_details: recutRows.value,
		})
		recutOpen.value = false
		showFeedback(`${recutType.value} created.`)
		emit("refresh")
	} catch (reason) {
		dialogError.value = reason.message || `Unable to create ${recutType.value}.`
	} finally {
		busy.value = ""
	}
}

async function saveLotTransfer() {
	busy.value = "transfer"
	dialogError.value = ""
	try {
		const name = await callMethod(planMethod("create_balance_lot_transfer"), {
			cutting_plan: props.doc.name,
			to_lot: targetLot.value,
		})
		lotTransferOpen.value = false
		targetLot.value = ""
		showFeedback(`Lot Transfer ${name} created.`)
		emit("refresh")
	} catch (reason) {
		dialogError.value = reason.message || "Unable to create the Lot Transfer."
	} finally {
		busy.value = ""
	}
}

function openApproval() {
	approvalTolerance.value = Number(props.doc.piece_weight_tolerance || 0)
	dialogError.value = ""
	approvalOpen.value = true
}

async function saveApproval() {
	busy.value = "approval"
	dialogError.value = ""
	try {
		await callMethod(planMethod("change_approval_grammage"), {
			doc_name: props.doc.name,
			piece_weight_tolerance: approvalTolerance.value,
		}, { silent: true })
		approvalOpen.value = false
		showFeedback("Approval grammage updated.")
		emit("refresh")
	} catch (reason) {
		dialogError.value = reason.message || "Unable to update approval grammage."
	} finally {
		busy.value = ""
	}
}

function normaliseGroups(value) {
	if (Array.isArray(value)) return value
	if (value?.items) return [value]
	if (value && typeof value === "object") return Object.values(value).filter((group) => group?.items)
	return []
}

function panelNames(group) {
	const panels = group?.[group?.stiching_attr]
	return Array.isArray(panels) ? panels : []
}

function quantity(value) {
	if (value && typeof value === "object") return Object.values(value).reduce((sum, item) => sum + Number(item || 0), 0) || "—"
	return Number(value || 0) || "—"
}

function emptyRecutForm() {
	return { cloth_type: "", colour: "", dia: "", shade: "", weight: null, no_of_rolls: null, panel_count: null }
}

function clone(value) {
	return JSON.parse(JSON.stringify(value || []))
}

function planMethod(name) {
	return `essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.${name}`
}

function laysheetMethod(name) {
	return `essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.${name}`
}

function clearFeedback() {
	feedback.value = ""
	dialogError.value = ""
}

function showFeedback(message, severity = "success") {
	feedback.value = message
	feedbackSeverity.value = severity
}

function toggleMoreActions(event) {
	moreActionsMenu.value?.toggle(event)
}
</script>

<style scoped>
.plan-actions {
	display: flex;
	align-items: center;
	min-width: 0;
}

.plan-actions :deep(.plan-actions-trigger.p-button:focus-visible) {
	outline: 2px solid color-mix(in srgb, var(--erp-accent) 45%, white);
	outline-offset: 2px;
}

.plan-actions :deep(.plan-actions-trigger .p-button-label) {
	white-space: nowrap;
}

.plan-action-feedback {
	pointer-events: none;
	position: fixed;
	z-index: 6100;
	top: 72px;
	left: 50%;
	width: min(92vw, 560px);
	margin: 0;
	transform: translateX(-50%);
	box-shadow: var(--erp-shadow-dialog);
}

.plan-action-feedback :deep(.p-message-close-button) { pointer-events: auto; }

:global(.plan-actions-menu.p-menu) {
	width: 252px;
	padding: 6px;
	font-family: var(--erp-font-family);
	font-size: var(--erp-font-size-caption);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border-strong);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-dialog);
}

:global(.plan-actions-menu .p-menu-item-content) {
	border-radius: 7px;
}

:global(.plan-actions-menu .p-menu-item-link) {
	gap: 9px;
	padding: 9px 10px;
	color: var(--erp-text);
}

:global(.plan-actions-menu .p-menu-item-icon) {
	color: var(--erp-text-muted);
	font-size: 0.82rem;
}

:global(.plan-actions-menu .p-menu-item-content:hover) {
	background: var(--erp-accent-soft);
}

:global(.plan-actions-menu .p-menu-separator) {
	margin: 5px 4px;
	border-color: var(--erp-border);
}

.dialog-stack { display: grid; gap: 14px; }
.dialog-table-wrap { display: grid; gap: 8px; }
.panel-note { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.table-scroll { overflow-x: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.table-scroll:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.action-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.action-table th, .action-table td { padding: 8px 10px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); text-align: left; }
.action-table th { color: var(--erp-text-secondary); background: var(--erp-surface-muted); font-size: var(--erp-font-size-min); white-space: nowrap; }
.action-table tr:last-child td { border-bottom: 0; }
.action-table th:last-child, .action-table td:last-child { border-right: 0; }
.recut-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.recut-form label, .dialog-field { display: grid; gap: 5px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 700; }
.recut-form__button { display: flex; align-items: end; }

:global(.action-dialog) { width: min(94vw, 980px); }
:global(.action-dialog--small) { width: min(92vw, 480px); }

.completed-copy-feedback {
	display: flex;
	align-items: center;
	gap: 7px;
	margin-top: 10px;
	padding: 8px 10px;
	color: var(--erp-success-text);
	background: var(--erp-success-soft);
	border: 1px solid color-mix(in srgb, var(--erp-success) 25%, var(--erp-border));
	border-radius: var(--erp-control-radius);
	font-size: var(--erp-font-size-caption);
	font-weight: 650;
}

.completed-copy-feedback--error {
	color: var(--erp-danger);
	background: var(--erp-danger-soft);
	border-color: color-mix(in srgb, var(--erp-danger) 28%, var(--erp-border));
}

@media (max-width: 760px) {
	.recut-form { grid-template-columns: 1fr; }
	.table-scroll { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); }
}
</style>
