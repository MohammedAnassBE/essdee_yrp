<template>
	<Dialog :visible="visible" modal dismissable-mask maximizable :header="record?.name ? `Cutting Marker · ${record.name}` : 'Create New Marker'" class="marker-dialog" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="marker-loading"><Skeleton v-for="index in 6" :key="index" height="3.2rem" /></div>
		<div v-else class="marker-content">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Message v-if="success" severity="success" :closable="false">{{ success }}</Message>

			<div class="marker-status-row">
				<span class="document-status" :class="`document-status--${statusTone}`">{{ statusLabel }}</span>
				<span v-if="record?.modified" class="modified-text">Updated {{ record.modified }}</span>
			</div>

			<section class="marker-section">
				<h3>Marker Details</h3>
				<div class="marker-fields">
					<label><span>Marker Name *</span><InputText v-model="form.marker_name" :disabled="!canEdit" fluid /></label>
					<label><span>Select Type *</span><Select v-model="form.selected_type" :options="['Machine', 'Manual']" :disabled="!canEdit" fluid /></label>
					<label><span>Length (Meters) *</span><InputNumber v-model="form.length" :min="0" :max-fraction-digits="3" :disabled="!canEdit" fluid /></label>
					<label><span>Width (Inches) *</span><InputNumber v-model="form.width" :min="0" :max-fraction-digits="3" :disabled="!canEdit" fluid /></label>
					<label><span>Total No Of Plys</span><InputNumber v-model="form.total_no_of_plys" :min="0" :disabled="!canEdit" fluid /></label>
					<label><span>Efficiency</span><InputNumber v-model="form.efficiency" :min="0" :max="100" suffix="%" :max-fraction-digits="2" :disabled="!canEdit" fluid /></label>
					<label><span>Required Piece Weight (kg)</span><InputNumber v-model="form.required_piece_weight" :min="0" :max-fraction-digits="4" :disabled="!canEdit" fluid /></label>
				</div>
			</section>

			<section class="marker-section">
				<div class="section-heading"><div><h3>Selected Panels</h3><small>Choose the panels included in this marker.</small></div><Button v-if="canEdit" label="Build Ratios" icon="pi pi-refresh" outlined size="small" :disabled="!form.panels.length" @click="buildRatios" /></div>
				<MultiSelect v-model="form.panels" :options="context.panels || []" filter display="chip" placeholder="Select panels" :disabled="!canEdit" fluid />
			</section>

			<section class="marker-section">
				<div class="section-heading"><div><h3>Size Ratios</h3><small>{{ form.selected_type === 'Machine' ? 'One ratio per size, applied to all selected panels.' : 'Set the ratio for every size and panel.' }}</small></div></div>
				<div v-if="form.ratio_items.length" class="table-scroll">
					<table class="marker-table"><thead><tr><th>Size</th><th v-if="form.selected_type === 'Manual'">Panel</th><th>Ratio</th></tr></thead><tbody><tr v-for="(row, index) in form.ratio_items" :key="`${row.size}-${row.panel || index}`"><td>{{ row.size }}</td><td v-if="form.selected_type === 'Manual'">{{ row.panel }}</td><td><InputNumber v-model="row.ratio" :min="0" :step="0.5" :min-fraction-digits="1" :max-fraction-digits="1" :disabled="!canEdit" fluid /></td></tr></tbody></table>
				</div>
				<div v-else class="empty-note">Select panels, then build the size ratios.</div>
			</section>

			<section v-if="form.panels.length" class="marker-section">
				<div class="section-heading"><div><h3>Panel Groups</h3><small>Every selected panel must belong to one group.</small></div><Button v-if="canEdit" label="Add Group" icon="pi pi-plus" text size="small" @click="addGroup" /></div>
				<div class="group-list">
					<div v-for="(group, index) in form.group_items" :key="group.id ?? index" class="group-row">
						<span>Group {{ index + 1 }}</span>
						<MultiSelect v-model="group.selected" :options="form.panels" display="chip" :disabled="!canEdit" fluid />
						<Button v-if="canEdit" icon="pi pi-trash" severity="danger" text rounded aria-label="Remove group" @click="form.group_items.splice(index, 1)" />
					</div>
				</div>
			</section>
		</div>

		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
			<DocumentPrintButton v-if="record?.permissions?.can_print" doctype="SD YRP Cutting Marker" :name="record.name" :formats="record.print_formats || []" :disabled="saving" />
			<Button v-if="record?.permissions?.can_cancel" label="Cancel Marker" icon="pi pi-ban" severity="danger" outlined :loading="saving" @click="cancelMarker" />
			<Button v-if="canEdit" label="Save Draft" icon="pi pi-save" severity="secondary" outlined :loading="saving && saveMode === 'draft'" @click="save(false)" />
			<Button v-if="canSubmit" label="Save & Submit" icon="pi pi-check" :loading="saving && saveMode === 'submit'" @click="save(true)" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import MultiSelect from "primevue/multiselect"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { callMethod } from "../../api/frappe.js"
import DocumentPrintButton from "./DocumentPrintButton.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	cuttingPlan: { type: String, required: true },
	markerName: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "changed"])

const loading = ref(false)
const saving = ref(false)
const saveMode = ref("")
const error = ref("")
const success = ref("")
const record = ref(null)
const context = ref({ panels: [], sizes: [] })
const form = reactive(emptyForm())

const canEdit = computed(() => record.value ? Boolean(record.value.permissions?.can_write) : Boolean(context.value.can_create))
const canSubmit = computed(() => canEdit.value && Boolean(record.value ? record.value.permissions?.can_submit : context.value.can_submit))
const statusLabel = computed(() => ["Draft", "Submitted", "Cancelled"][Number(record.value?.docstatus || 0)] || "Draft")
const statusTone = computed(() => ["draft", "submitted", "cancelled"][Number(record.value?.docstatus || 0)] || "draft")

watch(
	() => [props.visible, props.markerName, props.cuttingPlan],
	([visible]) => { if (visible) load() },
)

async function load() {
	loading.value = true
	error.value = ""
	success.value = ""
	try {
		const data = await callMethod(markerMethod("get_web_marker"), {
			cutting_plan: props.cuttingPlan,
			marker: props.markerName || undefined,
		})
		record.value = data?.marker || null
		context.value = data?.context || { panels: [], sizes: [] }
		replaceForm(record.value ? recordForm(record.value) : emptyForm())
	} catch (reason) {
		error.value = reason.message || "Unable to load the Cutting Marker."
	} finally {
		loading.value = false
	}
}

function buildRatios() {
	error.value = ""
	const oldValues = new Map(form.ratio_items.map((row) => [`${row.size}|${row.panel || ''}`, Number(row.ratio || 0)]))
	if (form.selected_type === "Manual") {
		form.ratio_items = (context.value.sizes || []).flatMap((size) =>
			form.panels.map((panel) => ({ size, panel, ratio: oldValues.get(`${size}|${panel}`) || 0 })),
		)
	} else {
		form.ratio_items = (context.value.sizes || []).map((size) => ({
			size,
			ratio: oldValues.get(`${size}|`) || oldRatioForSize(size),
		}))
	}
	form.group_items = form.panels.map((panel, index) => ({ id: index, selected: [panel] }))
}

function oldRatioForSize(size) {
	return Number(form.ratio_items.find((row) => row.size === size)?.ratio || 0)
}

function addGroup() {
	form.group_items.push({ id: Date.now(), selected: [] })
}

async function save(submit) {
	error.value = ""
	success.value = ""
	if (!validate()) return
	saving.value = true
	saveMode.value = submit ? "submit" : "draft"
	try {
		const saved = await callMethod(markerMethod("save_web_marker"), {
			cutting_plan: props.cuttingPlan,
			marker: record.value?.name || undefined,
			values: form,
			submit,
		})
		record.value = saved
		replaceForm(recordForm(saved))
		success.value = submit ? "Marker submitted." : "Draft marker saved."
		emit("changed", saved)
		if (submit) emit("update:visible", false)
	} catch (reason) {
		error.value = reason.message || "Unable to save the Cutting Marker."
	} finally {
		saving.value = false
		saveMode.value = ""
	}
}

async function cancelMarker() {
	if (!window.confirm(`Cancel Cutting Marker ${record.value?.name}?`)) return
	saving.value = true
	error.value = ""
	try {
		const changed = await callMethod(markerMethod("change_web_marker_status"), {
			cutting_plan: props.cuttingPlan,
			marker: record.value.name,
			action: "cancel",
		})
		record.value = changed
		emit("changed", changed)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason.message || "Unable to cancel the Cutting Marker."
	} finally {
		saving.value = false
	}
}

function validate() {
	if (!form.marker_name || !form.length || !form.width) {
		error.value = "Enter the marker name, length, and width."
		return false
	}
	if (!form.panels.length) {
		error.value = "Select at least one panel."
		return false
	}
	if (!form.ratio_items.length || !form.ratio_items.some((row) => Number(row.ratio || 0) > 0)) {
		error.value = "Build the ratios and enter the ratio values."
		return false
	}
	const grouped = form.group_items.flatMap((group) => group.selected || [])
	if (grouped.length !== form.panels.length || new Set(grouped).size !== form.panels.length || form.panels.some((panel) => !grouped.includes(panel))) {
		error.value = "Place every selected panel in exactly one panel group."
		return false
	}
	return true
}

function recordForm(item) {
	return {
		marker_name: item.marker_name || "",
		length: numberOrNull(item.length),
		width: numberOrNull(item.width),
		total_no_of_plys: numberOrNull(item.total_no_of_plys),
		efficiency: numberOrNull(item.efficiency),
		required_piece_weight: numberOrNull(item.required_piece_weight),
		selected_type: item.selected_type || "Machine",
		panels: [...(item.panels || [])],
		ratio_items: clone(item.ratio_items || []),
		group_items: clone(item.group_items || []).map((group, index) => ({ ...group, id: group.id ?? index, selected: [...(group.selected || group.defaultList || [])] })),
	}
}

function emptyForm() {
	return { marker_name: "", length: null, width: null, total_no_of_plys: null, efficiency: null, required_piece_weight: null, selected_type: "Machine", panels: [], ratio_items: [], group_items: [] }
}

function replaceForm(values) {
	Object.assign(form, emptyForm(), clone(values))
}

function numberOrNull(value) {
	return value === null || value === undefined || value === "" ? null : Number(value)
}

function clone(value) {
	return JSON.parse(JSON.stringify(value || []))
}

function markerMethod(name) {
	return `essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker.${name}`
}
</script>

<style scoped>
.marker-loading { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.marker-content { display: grid; gap: 14px; }
.marker-status-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.document-status { padding: 4px 9px; border-radius: 999px; font-size: 0.7rem; font-weight: 800; }
.document-status--draft { color: #705913; background: #fff7cf; }
.document-status--submitted { color: #236441; background: #e3f5e9; }
.document-status--cancelled { color: #9a3434; background: #fde8e8; }
.modified-text { color: #7a867f; font-size: 0.7rem; }
.marker-section { display: grid; gap: 12px; padding: 14px; border: 1px solid #e0e7e3; border-radius: 12px; background: #fff; }
.marker-section h3 { margin: 0; color: #315f48; font-size: 0.9rem; }
.marker-section small { color: #7a867f; font-size: 0.72rem; }
.marker-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; }
.marker-fields label { display: grid; gap: 5px; color: #4b5951; font-size: 0.75rem; font-weight: 700; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading > div { display: grid; gap: 3px; }
.table-scroll { overflow-x: auto; border: 1px solid #e2e8e4; border-radius: 9px; }
.marker-table { width: 100%; min-width: 500px; border-collapse: collapse; font-size: 0.78rem; }
.marker-table th, .marker-table td { padding: 8px 10px; border-right: 1px solid #e4e9e6; border-bottom: 1px solid #e4e9e6; text-align: left; }
.marker-table th { color: #4b5a51; background: #f6f9f7; font-size: 0.71rem; }
.marker-table tr:last-child td { border-bottom: 0; }
.marker-table th:last-child, .marker-table td:last-child { border-right: 0; }
.empty-note { display: grid; place-items: center; min-height: 64px; color: #7b8780; font-size: 0.77rem; background: #fafcfb; border: 1px dashed #dce4df; border-radius: 9px; }
.group-list { display: grid; gap: 8px; }
.group-row { display: grid; grid-template-columns: 72px minmax(0, 1fr) 38px; align-items: center; gap: 8px; color: #536158; font-size: 0.75rem; font-weight: 700; }
:global(.marker-dialog) { width: min(95vw, 1050px); }

@media (max-width: 700px) {
	.marker-loading, .marker-fields { grid-template-columns: 1fr; }
	.group-row { grid-template-columns: 1fr 38px; }
	.group-row > span { grid-column: 1 / -1; }
}
</style>
