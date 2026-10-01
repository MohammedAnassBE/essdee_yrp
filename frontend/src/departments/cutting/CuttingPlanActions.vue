<template>
	<section class="plan-actions plan-command-bar erp-command-bar" aria-label="Cutting Plan commands">
		<div class="plan-actions__buttons">
			<Button v-if="permissions.can_run_plan_actions" class="primary-command" label="Generate" icon="pi pi-sparkles" size="small" :loading="busy === 'generate'" @click="runPlanAction('generate')" />
			<Button v-if="permissions.can_run_plan_actions" label="Fetch Received Cloth" icon="pi pi-download" text size="small" :loading="busy === 'fetch'" @click="runPlanAction('fetch')" />
			<Button v-if="permissions.can_run_plan_actions" label="Calculate LaySheets" icon="pi pi-calculator" text size="small" :loading="busy === 'calculate'" @click="runPlanAction('calculate')" />
			<Button label="Get Completed" icon="pi pi-chart-bar" text size="small" @click="emit('show-summary')" />
			<Button v-if="permissions.can_update_completed" label="Update Completed" icon="pi pi-check-square" text size="small" @click="openCompleted" />
			<Button v-if="permissions.can_create_recut" label="Update Recut" icon="pi pi-replay" text size="small" @click="openRecut('Recut')" />
			<Button v-if="permissions.can_create_recut" label="Update Print Panel" icon="pi pi-print" text size="small" @click="openRecut('Print Panel')" />
			<Button v-if="permissions.can_create_lot_transfer" label="Lot Transfer" icon="pi pi-arrow-right-arrow-left" text size="small" @click="lotTransferOpen = true" />
			<Button v-if="permissions.can_change_approval_grammage" label="Approval" icon="pi pi-shield" text size="small" @click="openApproval" />
		</div>
	</section>

	<Message v-if="feedback" :severity="feedbackSeverity" :closable="true" @close="feedback = ''">{{ feedback }}</Message>

	<Dialog v-model:visible="completedOpen" modal dismissable-mask maximizable header="Update Completed Cut Quantity" class="action-dialog action-dialog--wide">
		<div class="dialog-stack">
			<div v-for="(group, groupIndex) in completedDraft" :key="groupIndex" class="dialog-table-wrap">
				<div v-if="panelNames(group).length" class="panel-note"><strong>Panels</strong> {{ panelNames(group).join(", ") }}</div>
				<div class="table-scroll">
					<table class="action-table">
						<thead><tr><th>S.No.</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="size in group.primary_attribute_values || []" :key="size">{{ size }}</th><th>Completed</th></tr></thead>
						<tbody><tr v-for="(row, rowIndex) in group.items || []" :key="rowIndex"><td>{{ rowIndex + 1 }}</td><td v-for="attribute in group.attributes || []" :key="attribute">{{ row.attributes?.[attribute] || '—' }}</td><td v-for="size in group.primary_attribute_values || []" :key="size">{{ quantity(row.values?.[size]) }}</td><td><Checkbox v-model="row.completed" binary /></td></tr></tbody>
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
			<Message v-if="dialogError" severity="error" :closable="false">{{ dialogError }}</Message>
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
			<div v-if="recutRows.length" class="table-scroll">
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
			<Message v-if="dialogError" severity="error" :closable="false">{{ dialogError }}</Message>
			<label class="dialog-field"><span>Target Lot</span><LinkField v-model="targetLot" doctype="SD YRP Lot" :filters="{ name: ['!=', doc.lot] }" /></label>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="lotTransferOpen = false" />
			<Button label="Create Lot Transfer" icon="pi pi-arrow-right-arrow-left" :disabled="!targetLot" :loading="busy === 'transfer'" @click="saveLotTransfer" />
		</template>
	</Dialog>

	<Dialog v-model:visible="approvalOpen" modal dismissable-mask header="Change Approval Grammage" class="action-dialog action-dialog--small">
		<div class="dialog-stack">
			<Message v-if="dialogError" severity="error" :closable="false">{{ dialogError }}</Message>
			<label class="dialog-field"><span>Grammage Allowance (kg)</span><InputNumber v-model="approvalTolerance" :min="0.0001" :min-fraction-digits="4" :max-fraction-digits="4" fluid /></label>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="approvalOpen = false" />
			<Button label="Update" icon="pi pi-check" :disabled="!approvalTolerance" :loading="busy === 'approval'" @click="saveApproval" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import { computed, reactive, ref } from "vue"

import { callMethod } from "../../api/frappe.js"
import LinkField from "../../components/common/LinkField.vue"

const props = defineProps({
	doc: { type: Object, required: true },
	data: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["refresh", "show-summary"])

const permissions = computed(() => props.data.permissions || {})
const busy = ref("")
const feedback = ref("")
const feedbackSeverity = ref("success")
const dialogError = ref("")
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

const methods = {
	generate: ["get_cloth1", { cutting_plan: props.doc.name }, "Cloth details generated."],
	fetch: ["fetch_received_cloth", { docname: props.doc.name }, "Received cloth refreshed."],
	calculate: ["calculate_laysheets", { cutting_plan: props.doc.name }, "LaySheet calculation queued."],
}

async function runPlanAction(action) {
	const [method, args, success] = methods[action]
	busy.value = action
	clearFeedback()
	try {
		await callMethod(planMethod(method), args)
		showFeedback(success)
		emit("refresh")
	} catch (reason) {
		showFeedback(reason.message || "Unable to complete the action.", "error")
	} finally {
		busy.value = ""
	}
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
		showFeedback(reason.message || "Unable to update completed quantities.", "error")
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
		})
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
</script>

<style scoped>
.plan-actions {
	display: flex;
	align-items: center;
	min-width: 0;
	padding: 4px 0;
}

.plan-actions__buttons {
	display: flex;
	align-items: center;
	gap: 4px;
	width: 100%;
	min-width: 0;
	overflow-x: auto;
	scrollbar-width: thin;
}

.plan-actions__buttons :deep(.p-button) {
	flex: 0 0 auto;
	min-height: var(--erp-control-height-compact);
	padding: 0.4rem 0.52rem;
	color: var(--erp-text-muted);
	background: transparent;
	border: 1px solid transparent;
	border-radius: var(--erp-control-radius);
	font-size: var(--erp-font-size-min);
	font-weight: 650;
	box-shadow: none;
}

.plan-actions__buttons :deep(.p-button-icon) {
	font-size: 0.78rem;
}

.plan-actions__buttons :deep(.p-button:not(.primary-command):hover) {
	color: var(--erp-accent-hover);
	background: var(--erp-accent-soft);
	border-color: color-mix(in srgb, var(--erp-accent) 20%, white);
	box-shadow: none;
}

.plan-actions__buttons :deep(.primary-command.p-button) {
	padding-inline: 0.7rem;
	color: #fff;
	background: var(--erp-accent);
	border-color: var(--erp-accent);
	box-shadow: 0 3px 10px color-mix(in srgb, var(--erp-accent) 18%, transparent);
}

.plan-actions__buttons :deep(.primary-command.p-button:hover) {
	background: var(--erp-accent-hover);
	border-color: var(--erp-accent-hover);
}

.dialog-stack { display: grid; gap: 14px; }
.dialog-table-wrap { display: grid; gap: 8px; }
.panel-note { color: #59675f; font-size: 0.78rem; }
.table-scroll { overflow-x: auto; border: 1px solid #e0e7e3; border-radius: 9px; }
.action-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 0.78rem; }
.action-table th, .action-table td { padding: 8px 10px; border-right: 1px solid #e4e9e6; border-bottom: 1px solid #e4e9e6; text-align: left; }
.action-table th { color: #4d5d54; background: #f6f9f7; font-size: 0.71rem; white-space: nowrap; }
.action-table tr:last-child td { border-bottom: 0; }
.action-table th:last-child, .action-table td:last-child { border-right: 0; }
.recut-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.recut-form label, .dialog-field { display: grid; gap: 5px; color: #4c5a52; font-size: 0.76rem; font-weight: 700; }
.recut-form__button { display: flex; align-items: end; }

:global(.action-dialog) { width: min(94vw, 980px); }
:global(.action-dialog--small) { width: min(92vw, 480px); }

@media (max-width: 760px) {
	.plan-actions__buttons { width: 100%; }
	.recut-form { grid-template-columns: 1fr; }
}
</style>
