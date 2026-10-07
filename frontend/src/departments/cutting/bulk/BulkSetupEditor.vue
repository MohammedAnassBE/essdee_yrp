<template>
	<section class="bulk-setup-editor erp-card erp-editor-shell" aria-label="Bulk LaySheets setup editor">
		<header class="bulk-setup-editor__header erp-editor-header">
			<div><span>{{ name || "New document" }}</span><h1>{{ name ? "Edit Bulk LaySheets" : "New Bulk LaySheets" }}</h1></div>
			<div class="bulk-setup-editor__actions erp-editor-actions">
				<Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="busy" @click="emit('cancel')" />
				<Button label="Save Setup" icon="pi pi-save" :loading="saving" :disabled="busy || !canSave" @click="saveSetup" />
			</div>
		</header>
		<WorkspaceLoadError v-if="loadFailed" title="Bulk setup unavailable" :message="error" @retry="load" />
		<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
		<div v-if="loading" class="bulk-setup-editor__loading"><Skeleton height="150px" /><Skeleton height="320px" /></div>
		<div v-else-if="!loadFailed" class="bulk-setup-editor__body">
			<section class="bulk-setup-card">
				<header><div><span class="section-kicker">Stock source</span><h2>Bulk setup</h2></div><Tag v-if="setupLocked" value="Locked after LaySheet creation" severity="secondary" rounded /></header>
				<div class="bulk-setup-fields">
					<LinkField v-model="form.main_lot" label="Main Stock Lot *" doctype="SD YRP Lot" :disabled="busy || setupLocked" :show-open-button="false" show-clear />
					<LinkField v-model="form.from_location" label="Stock Location *" doctype="Supplier" :disabled="busy || setupLocked" :show-open-button="false" show-clear />
					<DateField v-model="form.posting_date" label="Posting Date" required :disabled="busy || setupLocked" />
					<LinkField v-model="form.cutting_spreader" label="Cutting Spreader *" doctype="SD YRP Cutting Spreader" :disabled="busy || setupLocked" :show-open-button="false" show-clear />
					<LinkField v-model="form.cutter" label="Cutter *" doctype="SD YRP Cutter" :disabled="busy || setupLocked" :show-open-button="false" show-clear />
				</div>
			</section>

			<section class="bulk-lots-card">
				<header><div><span class="section-kicker">Production split</span><h2>Split Lots</h2></div><Button label="Add Split Lot" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="busy" @click="addRow" /></header>
				<div v-if="form.lot_details.length" class="bulk-lots-table-wrap" role="region" tabindex="0" aria-label="Split Lot setup">
					<table class="bulk-lots-table"><thead><tr><th class="sequence-column">#</th><th>Split Lot</th><th>Cutting Plan</th><th>Cutting Marker</th><th class="actions-column">Actions</th></tr></thead><tbody>
						<tr v-for="(row, index) in form.lot_details" :key="row._row_key" class="bulk-setup-row">
							<td><span class="row-number">{{ index + 1 }}</span></td>
							<td><LinkField v-model="row.lot" doctype="SD YRP Lot" :disabled="busy || Boolean(row.cutting_laysheet)" :show-open-button="false" show-clear @clear="clearRowLot(row)" @select="clearRowLot(row, false)" /></td>
							<td><LinkField v-model="row.cutting_plan" doctype="SD YRP Cutting Plan" :filters="planFilters(row)" :disabled="busy || !row.lot || Boolean(row.cutting_laysheet)" :show-open-button="false" show-clear @clear="row.cutting_marker = ''" @select="row.cutting_marker = ''" /></td>
							<td><LinkField v-model="row.cutting_marker" doctype="SD YRP Cutting Marker" :filters="markerFilters(row)" :disabled="busy || !row.cutting_plan || Boolean(row.cutting_laysheet)" :show-open-button="false" show-clear /></td>
							<td><Button icon="pi pi-trash" aria-label="Remove split lot" severity="danger" text rounded :disabled="busy || Boolean(row.cutting_laysheet)" @click="removeRow(index)" /></td>
						</tr>
					</tbody></table>
				</div>
				<div v-else class="bulk-lots-empty"><i class="pi pi-clone"></i><strong>No split lots yet</strong><span>Add each split lot with its submitted Plan and Marker.</span></div>
			</section>
		</div>
	</section>
	<DocumentErrorDialog :message="actionError" title="Bulk setup could not be saved" @dismiss="actionError = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tag from "primevue/tag"
import { computed, reactive, ref, watch } from "vue"

import { getBulkLaySheetsEditor, saveBulkLaySheets } from "../../../api/cuttingBulkLaySheets.js"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({ name: { type: String, default: "" }, initialPayload: { type: Object, default: null } })
const emit = defineEmits(["saved", "cancel", "loaded"])
const form = reactive({ main_lot: "", from_location: "", posting_date: "", cutting_spreader: "", cutter: "", lot_details: [] })
const permissions = reactive({ can_create: false, can_write: false })
const modified = ref("")
const setupLocked = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref("")
const hasLoaded = ref(false)
const actionError = ref("")
let rowSequence = 0

const busy = computed(() => loading.value || saving.value)
const loadFailed = computed(() => Boolean(error.value && !hasLoaded.value))
const canSave = computed(() => {
	const permitted = props.name ? permissions.can_write : permissions.can_create
	return Boolean(permitted && form.main_lot && form.from_location && form.posting_date && form.cutting_spreader && form.cutter && form.lot_details.length && form.lot_details.every((row) => row.lot && row.cutting_plan && row.cutting_marker))
})

function clone(value) { return JSON.parse(JSON.stringify(value ?? null)) }
function rowKey(row) { return row.name || `new-row-${++rowSequence}` }
function applyPayload(payload) {
	const record = payload?.record || {}
	for (const key of ["main_lot", "from_location", "posting_date", "cutting_spreader", "cutter"]) form[key] = record[key] || ""
	form.lot_details = (record.lot_details || []).map((row) => ({ ...clone(row), _row_key: rowKey(row) }))
	Object.assign(permissions, payload?.permissions || {})
	modified.value = record.modified || ""
	setupLocked.value = Boolean(payload?.setup_locked)
	hasLoaded.value = true
	emit("loaded", payload)
}
async function load() {
	loading.value = true; error.value = ""
	try { applyPayload(props.initialPayload || await getBulkLaySheetsEditor(props.name)) }
	catch (reason) { error.value = reason?.message || "Unable to load Bulk LaySheets setup." }
	finally { loading.value = false }
}
function addRow() { form.lot_details.push({ _row_key: `new-row-${++rowSequence}`, name: "", lot: "", cutting_plan: "", cutting_marker: "" }) }
function removeRow(index) { form.lot_details.splice(index, 1) }
function clearRowLot(row, clearLot = true) { if (clearLot) row.lot = ""; row.cutting_plan = ""; row.cutting_marker = "" }
function planFilters(row) { return { lot: row.lot || "", docstatus: 1, cp_status: ["!=", "Completed"] } }
function markerFilters(row) { return { cutting_plan: row.cutting_plan || "", docstatus: 1 } }
async function saveSetup() {
	saving.value = true; actionError.value = ""
	try {
		const payload = await saveBulkLaySheets({
			main_lot: form.main_lot, from_location: form.from_location, posting_date: form.posting_date,
			cutting_spreader: form.cutting_spreader, cutter: form.cutter,
			lot_details: form.lot_details.map(({ _row_key, ...row }) => ({ ...row, name: row.name || undefined })),
		}, { name: props.name, expectedModified: modified.value })
		emit("saved", payload)
	} catch (reason) { actionError.value = reason?.message || "Unable to save Bulk LaySheets setup." }
	finally { saving.value = false }
}

watch(() => props.name, load, { immediate: true })
</script>

<style scoped>
.bulk-setup-editor { display: flex; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); flex-direction: column; gap: var(--erp-space-3); }
.bulk-setup-card > header, .bulk-lots-card > header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.bulk-setup-editor__header span, .section-kicker { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .045em; text-transform: uppercase; }
.bulk-setup-editor__header h1 { margin: 3px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -.025em; }
.bulk-setup-editor__loading, .bulk-setup-editor__body { display: grid; gap: var(--erp-space-3); }
.bulk-setup-card, .bulk-lots-card { padding: var(--erp-space-4); background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.bulk-setup-card h2, .bulk-lots-card h2 { margin: 3px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.bulk-setup-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); margin-top: var(--erp-space-4); }
.bulk-lots-table-wrap { margin-top: var(--erp-space-3); overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.bulk-lots-table-wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.bulk-lots-table { width: 100%; min-width: 980px; border-collapse: collapse; }
.bulk-lots-table th { padding: 9px 10px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); text-align: left; background: var(--erp-surface-muted); border-bottom: 1px solid var(--erp-border); }
.bulk-lots-table td { padding: 9px 10px; vertical-align: middle; border-bottom: 1px solid var(--erp-border); }
.bulk-lots-table tbody tr:last-child td { border-bottom: 0; }
.sequence-column { width: 44px; }.actions-column { width: 64px; text-align: center !important; }.row-number { display: inline-grid; width: 24px; height: 24px; place-items: center; color: var(--erp-accent); font-size: var(--erp-font-size-min); font-weight: 760; background: var(--erp-accent-soft); border-radius: 50%; }
.bulk-lots-empty { display: grid; min-height: 190px; margin-top: var(--erp-space-3); place-content: center; justify-items: center; gap: 7px; color: var(--erp-text-muted); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }.bulk-lots-empty i { color: var(--erp-accent); font-size: 1.5rem; }.bulk-lots-empty strong { color: var(--erp-text); }
@media (max-width: 900px) { .bulk-setup-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .bulk-setup-card, .bulk-lots-card { padding: var(--erp-space-3); }.bulk-setup-fields { grid-template-columns: 1fr; }.bulk-lots-table-wrap { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } }
</style>
