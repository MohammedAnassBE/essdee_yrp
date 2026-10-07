<template>
	<Dialog :visible="visible" modal dismissable-mask maximizable :header="record?.name ? `Cutting Marker · ${record.name}` : 'Create New Marker'" class="marker-dialog erp-entity-dialog" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="marker-loading"><Skeleton v-for="index in 6" :key="index" height="3.2rem" /></div>
		<div v-else class="marker-content">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Message v-if="success" severity="success" :closable="false">{{ success }}</Message>

			<div class="marker-status-row">
				<DocumentStatusBadge :docstatus="record?.docstatus" :label="statusLabel" />
				<span v-if="record?.modified" class="modified-text">Updated {{ formatDate(record.modified, true) }}</span>
			</div>

			<template v-if="canEdit">
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
				<div v-if="form.ratio_items.length" class="table-scroll" role="region" tabindex="0" aria-label="Editable marker size ratios">
					<table class="marker-table"><thead><tr><th>Size</th><th v-if="form.selected_type === 'Manual'">Panel</th><th>Ratio</th></tr></thead><tbody><tr v-for="(row, index) in form.ratio_items" :key="`${row.size}-${row.panel || index}`"><td>{{ row.size }}</td><td v-if="form.selected_type === 'Manual'">{{ row.panel }}</td><td><InputNumber v-model="row.ratio" :aria-label="`Ratio for ${row.size}${row.panel ? ` · ${row.panel}` : ''}`" :min="0" :step="0.5" :min-fraction-digits="1" :max-fraction-digits="1" :disabled="!canEdit" fluid /></td></tr></tbody></table>
				</div>
				<div v-else class="empty-note">Select panels, then build the size ratios.</div>
			</section>

			<section v-if="form.panels.length" class="marker-section">
				<div class="section-heading"><div><h3>Panel Groups</h3><small>Every selected panel must belong to one group.</small></div><Button v-if="canEdit" label="Add Group" icon="pi pi-plus" text size="small" @click="addGroup" /></div>
				<div class="group-list">
					<div v-for="(group, index) in form.group_items" :key="group.id ?? index" class="group-row">
						<span>Group {{ index + 1 }}</span>
						<MultiSelect v-model="group.selected" :aria-label="`Panels for group ${index + 1}`" :options="form.panels" display="chip" :disabled="!canEdit" fluid />
						<Button v-if="canEdit" icon="pi pi-trash" severity="danger" text rounded :aria-label="`Remove group ${index + 1}`" @click="form.group_items.splice(index, 1)" />
					</div>
				</div>
			</section>
			</template>

			<template v-else-if="record">
				<section class="marker-section marker-read-view">
					<h3>Marker Details</h3>
					<div class="marker-read-grid">
						<div v-for="item in readOnlyDetails" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div>
					</div>
				</section>
				<section class="marker-section marker-read-view">
					<div class="section-heading"><div><h3>Selected Panels</h3><small>{{ form.panels.length }} panels</small></div></div>
					<div class="marker-chip-list"><span v-for="panel in form.panels" :key="panel">{{ panel }}</span></div>
				</section>
				<section class="marker-section marker-read-view">
					<div class="section-heading"><div><h3>Size Ratios</h3><small>{{ form.selected_type === 'Machine' ? 'Ratio by size' : 'Ratio by size and panel' }}</small></div></div>
					<div v-if="form.ratio_items.length" class="table-scroll" role="region" tabindex="0" aria-label="Marker size ratios">
						<table class="marker-table"><thead><tr><th>Size</th><th v-if="form.selected_type === 'Manual'">Panel</th><th class="number-cell">Ratio</th></tr></thead><tbody><tr v-for="(row, index) in form.ratio_items" :key="`${row.size}-${row.panel || index}`"><td>{{ row.size }}</td><td v-if="form.selected_type === 'Manual'">{{ row.panel }}</td><td class="number-cell"><strong>{{ Number(row.ratio || 0).toFixed(1) }}</strong></td></tr></tbody></table>
					</div>
					<div v-else class="empty-note">No size ratios.</div>
				</section>
				<section v-if="form.group_items.length" class="marker-section marker-read-view">
					<div class="section-heading"><div><h3>Panel Groups</h3><small>{{ form.group_items.length }} groups</small></div></div>
					<div class="marker-group-summary"><div v-for="(group, index) in form.group_items" :key="group.id ?? index"><strong>Group {{ index + 1 }}</strong><span>{{ (group.selected || []).join(', ') || '—' }}</span></div></div>
				</section>
			</template>
		</div>

		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
			<DocumentPrintButton v-if="record?.permissions?.can_print" doctype="SD YRP Cutting Marker" :name="record.name" :formats="record.print_formats || []" :disabled="saving" />
			<Button v-if="record?.permissions?.can_cancel" label="Cancel Marker" icon="pi pi-ban" severity="danger" outlined :loading="saving" @click="cancelMarker" />
			<DocumentSaveButton :show-save="canEdit" :show-submit="canSubmit" :loading="saving" @save="save(false)" @submit="save(true)" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="actionError" title="Cutting Marker action failed" @dismiss="actionError = ''" />
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
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import DocumentPrintButton from "./DocumentPrintButton.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	cuttingPlan: { type: String, default: "" },
	parentDoctype: { type: String, default: "SD YRP Cutting Plan" },
	parentName: { type: String, default: "" },
	markerName: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()

const loading = ref(false)
const saving = ref(false)
const saveMode = ref("")
const error = ref("")
const actionError = ref("")
const success = ref("")
const record = ref(null)
const context = ref({ panels: [], sizes: [] })
const form = reactive(emptyForm())
const resolvedParentName = computed(() => props.parentName || props.cuttingPlan)
const resolvedParentField = computed(() => props.parentDoctype === "SD YRP Cutting Order" ? "cutting_order" : "cutting_plan")
const parentArgs = computed(() => ({ [resolvedParentField.value]: resolvedParentName.value }))

const canEdit = computed(() => record.value ? Boolean(record.value.permissions?.can_write) : Boolean(context.value.can_create))
const canSubmit = computed(() => canEdit.value && Boolean(record.value ? record.value.permissions?.can_submit : context.value.can_submit))
const statusLabel = computed(() => ["Draft", "Submitted", "Cancelled"][Number(record.value?.docstatus || 0)] || "Draft")
const readOnlyDetails = computed(() => [
	["Marker Name", form.marker_name],
	["Select Type", form.selected_type],
	["Length", `${formatNumber(form.length, 3)} m`],
	["Width", `${formatNumber(form.width, 3)} in`],
	["Total No Of Plys", display(form.total_no_of_plys)],
	["Efficiency", form.efficiency === null ? "—" : `${formatNumber(form.efficiency, 2)}%`],
	["Required Piece Weight", form.required_piece_weight === null ? "—" : `${formatNumber(form.required_piece_weight, 4)} kg`],
].map(([label, value]) => ({ label, value })))

watch(
	() => [props.visible, props.markerName, resolvedParentName.value],
	([visible]) => { if (visible) load() },
)

async function load() {
	loading.value = true
	error.value = ""
	actionError.value = ""
	success.value = ""
	try {
		const data = await callMethod(markerMethod("get_web_marker"), {
			...parentArgs.value,
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
	form.group_items = reconcileGroups(form.group_items, form.panels)
}

function reconcileGroups(groups, panels) {
	const available = new Set(panels)
	const kept = (groups || [])
		.map((group, index) => ({ ...group, id: group.id ?? index, selected: (group.selected || []).filter((panel) => available.has(panel)) }))
		.filter((group) => group.selected.length)
	const assigned = new Set(kept.flatMap((group) => group.selected))
	const additions = panels.filter((panel) => !assigned.has(panel)).map((panel, index) => ({ id: `new-${index}-${panel}`, selected: [panel] }))
	return [...kept, ...additions]
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
			...parentArgs.value,
			marker: record.value?.name || undefined,
			values: form,
			submit,
			expected_modified: record.value?.modified || undefined,
		})
		record.value = saved
		replaceForm(recordForm(saved))
		success.value = submit ? "Marker submitted." : "Draft marker saved."
		emit("changed", saved)
		if (submit) emit("update:visible", false)
	} catch (reason) {
		actionError.value = reason.message || "Unable to save the Cutting Marker."
	} finally {
		saving.value = false
		saveMode.value = ""
	}
}

async function cancelMarker() {
	return confirmAction({
		header: "Cancel Cutting Marker?",
		message: `Cancel Cutting Marker ${record.value?.name}? This changes the document status and cannot be undone here.`,
		acceptLabel: "Cancel Marker",
		acceptIcon: "pi pi-ban",
		accept: performCancelMarker,
	})
}

async function performCancelMarker() {
	saving.value = true
	error.value = ""
	try {
		const changed = await callMethod(markerMethod("change_web_marker_status"), {
			...parentArgs.value,
			marker: record.value.name,
			action: "cancel",
		})
		record.value = changed
		emit("changed", changed)
		emit("update:visible", false)
	} catch (reason) {
		actionError.value = reason.message || "Unable to cancel the Cutting Marker."
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
	if (!form.ratio_items.length || (!context.value.is_manual_entry && !form.ratio_items.some((row) => Number(row.ratio || 0) > 0))) {
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

function display(value) { return value === null || value === undefined || value === "" ? "—" : value }
function formatNumber(value, precision) { return value === null || value === undefined || value === "" ? "—" : Number(value).toLocaleString("en-IN", { minimumFractionDigits: precision, maximumFractionDigits: precision }) }
function formatDate(value, includeTime = false) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!match) return value || "—"; const date = `${match[3]}-${match[2]}-${match[1]}`; return includeTime && match[4] ? `${date} · ${match[4]}:${match[5]}` : date }

function markerMethod(name) {
	return `essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker.${name}`
}
</script>

<style scoped>
.marker-loading { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.marker-content { display: grid; gap: 14px; }
.marker-status-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.document-status { padding: 4px 9px; border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 800; }
.document-status--draft { color: var(--erp-warning); background: var(--erp-warning-soft); }
.document-status--submitted { color: var(--erp-accent-dark); background: var(--erp-success-soft); }
.document-status--cancelled { color: var(--erp-danger); background: var(--erp-danger-soft); }
.modified-text { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.marker-section { display: grid; gap: 12px; padding: 14px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.marker-section h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.marker-section small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.marker-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; }
.marker-fields label { display: grid; gap: 5px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading > div { display: grid; gap: 3px; }
.table-scroll { overflow-x: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.table-scroll:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.marker-table { width: 100%; min-width: 500px; border-collapse: collapse; font-size: 13px; }
.marker-table th, .marker-table td { padding: 8px 10px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); text-align: left; }
.marker-table th { color: var(--erp-text-secondary); background: var(--erp-surface-muted); font-size: var(--erp-font-size-min); }
.marker-table tr:last-child td { border-bottom: 0; }
.marker-table th:last-child, .marker-table td:last-child { border-right: 0; }
.empty-note { display: grid; place-items: center; min-height: 64px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); background: var(--erp-surface-soft); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }
.group-list { display: grid; gap: 8px; }
.group-row { display: grid; grid-template-columns: 72px minmax(0, 1fr) 38px; align-items: center; gap: 8px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 700; }
.marker-read-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.marker-read-grid > div { display: grid; min-height: 58px; align-content: center; gap: 4px; padding: 10px 12px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.marker-read-grid span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; text-transform: uppercase; }
.marker-read-grid strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); overflow-wrap: anywhere; }
.marker-chip-list { display: flex; flex-wrap: wrap; gap: 6px; }
.marker-chip-list span { padding: 4px 9px; color: var(--erp-text); background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 700; }
.marker-group-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.marker-group-summary > div { display: grid; gap: 3px; padding: 9px 11px; background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.marker-group-summary strong { color: var(--erp-accent-strong); font-size: var(--erp-font-size-min); text-transform: uppercase; }
.marker-group-summary span { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.number-cell { text-align: right !important; font-variant-numeric: tabular-nums; }
:global(.marker-dialog) { width: min(95vw, 1050px); }

@media (max-width: 700px) {
	.marker-loading, .marker-fields { grid-template-columns: 1fr; }
	.marker-read-grid, .marker-group-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.marker-read-grid > div { min-height: 50px; padding: 8px 9px; }
	.group-row { grid-template-columns: 1fr 38px; }
	.group-row > span { grid-column: 1 / -1; }
	.table-scroll { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); }
}
</style>
