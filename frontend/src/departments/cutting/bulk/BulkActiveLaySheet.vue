<template>
	<section class="bulk-active-sheet data-panel">
		<header>
			<div><span>Active split lot</span><h2>{{ row?.lot || "LaySheet editor" }} <small v-if="context.name">· {{ context.name }}</small></h2></div>
			<div class="bulk-active-sheet__header-actions"><Tag v-if="context.status" :value="context.status" :severity="statusSeverity(context.status)" rounded /><Button v-if="canEdit" label="Save Changes" icon="pi pi-save" size="small" :loading="saving" :disabled="!dirty" @click="saveIfDirty" /></div>
		</header>
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<Message v-if="context.read_only" severity="info" :closable="false">Stock processing has started. Cloth and accessory entries are locked.</Message>
		<div v-if="context.name" class="bulk-active-sheet__body">
			<section class="detail-block">
				<header><div><h3>Cloth Details</h3><span>{{ clothRows.length }} rows</span></div><Button v-if="canEdit" label="Add Cloth" icon="pi pi-plus" size="small" severity="secondary" outlined @click="openCloth()" /></header>
				<div v-if="clothRows.length" class="detail-table-scroll"><table><thead><tr><th>#</th><th>Cloth</th><th>Cloth Type</th><th>Colour</th><th>Dia</th><th>Shade</th><th class="numeric">Weight</th><th class="numeric">Rolls</th><th class="numeric">Bits</th><th class="numeric">Used</th><th class="numeric">Balance</th><th v-if="canEdit">Actions</th></tr></thead><tbody><tr v-for="(item, index) in clothRows" :key="item.name || index"><td>{{ index + 1 }}</td><td>{{ item.cloth_item_variant || "—" }}</td><td>{{ item.cloth_type || "—" }}</td><td>{{ display(item.colour) }}</td><td>{{ display(item.actual_dia || item.dia) }}</td><td>{{ item.shade || "—" }}</td><td class="numeric">{{ number(item.weight) }}</td><td class="numeric">{{ item.no_of_rolls || 0 }}</td><td class="numeric">{{ item.no_of_bits || 0 }}</td><td class="numeric">{{ number(item.used_weight) }}</td><td class="numeric">{{ number(item.balance_weight) }}</td><td v-if="canEdit" class="row-actions"><Button icon="pi pi-pencil" severity="secondary" text rounded aria-label="Edit cloth" @click="openCloth(item, index)" /><Button icon="pi pi-trash" severity="danger" text rounded aria-label="Delete cloth" @click="removeCloth(index)" /></td></tr></tbody></table></div>
				<div v-else class="detail-empty">No cloth details entered.</div>
			</section>
			<section class="detail-block">
				<header><div><h3>Accessory Details</h3><span>{{ accessoryRows.length }} rows</span></div><Button v-if="canEdit" label="Add Accessory" icon="pi pi-plus" size="small" severity="secondary" outlined @click="openAccessory()" /></header>
				<div v-if="accessoryRows.length" class="detail-table-scroll"><table><thead><tr><th>#</th><th>Accessory</th><th>Cloth</th><th>Cloth Type</th><th>Colour</th><th>Dia</th><th>Shade</th><th class="numeric">Weight</th><th class="numeric">Rolls</th><th v-if="canEdit">Actions</th></tr></thead><tbody><tr v-for="(item, index) in accessoryRows" :key="item.name || index"><td>{{ index + 1 }}</td><td>{{ item.accessory || "—" }}</td><td>{{ item.cloth_item_variant || "—" }}</td><td>{{ item.cloth_type || "—" }}</td><td>{{ display(item.colour) }}</td><td>{{ display(item.actual_dia || item.dia) }}</td><td>{{ item.shade || "—" }}</td><td class="numeric">{{ number(item.weight) }}</td><td class="numeric">{{ item.no_of_rolls || 0 }}</td><td v-if="canEdit" class="row-actions"><Button icon="pi pi-pencil" severity="secondary" text rounded aria-label="Edit accessory" @click="openAccessory(item, index)" /><Button icon="pi pi-trash" severity="danger" text rounded aria-label="Delete accessory" @click="removeAccessory(index)" /></td></tr></tbody></table></div>
				<div v-else class="detail-empty">No accessory details entered.</div>
			</section>
		</div>
		<div v-else class="active-empty"><i class="pi pi-arrow-right"></i><strong>Select a split lot</strong><span>Choose a LaySheet from the workflow rail to continue.</span></div>
	</section>

	<Dialog v-model:visible="clothDialog" modal dismissable-mask :header="clothIndex < 0 ? 'Add Cloth Detail' : 'Edit Cloth Detail'" class="bulk-detail-dialog">
		<div class="bulk-detail-form">
			<label><span>Cloth Item Variant</span><InputText v-model="clothForm.cloth_item_variant" fluid /></label><label><span>Cloth Type *</span><InputText v-model="clothForm.cloth_type" fluid /></label><label><span>Colour *</span><InputText v-model="clothForm.colour" fluid @change="loadSetFields()" /></label><label><span>Dia *</span><InputText v-model="clothForm.dia" fluid /></label><label><span>Actual Dia *</span><InputText v-model="clothForm.actual_dia" fluid /></label><label><span>Shade *</span><InputText v-model="clothForm.shade" fluid /></label><label><span>Fabric Type *</span><Select v-model="clothForm.fabric_type" :options="['Open Width', 'Tubler']" fluid /></label><label><span>Weight (kg) *</span><InputNumber v-model="clothForm.weight" :min="0" :max-fraction-digits="3" fluid /></label><label><span>Balance Weight (kg)</span><InputNumber v-model="clothForm.balance_weight" :min="0" :max-fraction-digits="3" fluid /></label><label><span>No of Rolls</span><InputNumber v-model="clothForm.no_of_rolls" :min="0" fluid /></label><label><span>No of Bits</span><InputNumber v-model="clothForm.no_of_bits" :min="0" fluid /></label><label><span>End Bit Weight (kg)</span><InputNumber v-model="clothForm.end_bit_weight" :min="0" :max-fraction-digits="3" fluid /></label><label v-for="field in visibleSetFields" :key="field.fieldname"><span>{{ field.label }} *</span><Select v-if="field.fieldtype === 'Select'" v-model="clothForm.set_combination[field.fieldname]" :options="fieldOptions(field)" :disabled="hasFieldDefault(field)" filter fluid /><InputText v-else v-model="clothForm.set_combination[field.fieldname]" :disabled="hasFieldDefault(field)" fluid /></label>
		</div>
		<template #footer><Button label="Close" severity="secondary" text @click="clothDialog = false" /><Button :label="clothIndex < 0 ? 'Add Cloth' : 'Update Cloth'" icon="pi pi-check" @click="saveCloth" /></template>
	</Dialog>

	<Dialog v-model:visible="accessoryDialog" modal dismissable-mask :header="accessoryIndex < 0 ? 'Add Accessory Detail' : 'Edit Accessory Detail'" class="bulk-detail-dialog">
		<div class="bulk-detail-form">
			<label><span>Accessory *</span><InputText v-model="accessoryForm.accessory" fluid /></label><label><span>Cloth Item Variant</span><InputText v-model="accessoryForm.cloth_item_variant" fluid /></label><label><span>Cloth Type *</span><InputText v-model="accessoryForm.cloth_type" fluid /></label><label><span>Colour *</span><InputText v-model="accessoryForm.colour" fluid /></label><label><span>Dia *</span><InputText v-model="accessoryForm.dia" fluid /></label><label><span>Actual Dia *</span><InputText v-model="accessoryForm.actual_dia" fluid /></label><label><span>Shade *</span><InputText v-model="accessoryForm.shade" fluid /></label><label><span>Weight (kg) *</span><InputNumber v-model="accessoryForm.weight" :min="0" :max-fraction-digits="3" fluid /></label><label><span>No of Rolls</span><InputNumber v-model="accessoryForm.no_of_rolls" :min="0" fluid /></label>
		</div>
		<template #footer><Button label="Close" severity="secondary" text @click="accessoryDialog = false" /><Button :label="accessoryIndex < 0 ? 'Add Accessory' : 'Update Accessory'" icon="pi pi-check" @click="saveAccessory" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Tag from "primevue/tag"
import { computed, reactive, ref, watch } from "vue"

import { saveBulkActiveEditor } from "../../../api/cuttingBulkLaySheets.js"
import { callMethod } from "../../../api/frappe.js"

const props = defineProps({ bulkName: { type: String, required: true }, row: { type: Object, default: null }, data: { type: Object, default: null }, modified: { type: String, default: "" }, canWrite: Boolean })
const emit = defineEmits(["saved", "dirty-change"])
const clothRows = ref([])
const accessoryRows = ref([])
const cleanSignature = ref("")
const saving = ref(false)
const error = ref("")
const clothDialog = ref(false)
const clothIndex = ref(-1)
const clothForm = reactive(emptyCloth())
const accessoryDialog = ref(false)
const accessoryIndex = ref(-1)
const accessoryForm = reactive(emptyAccessory())
const setFields = ref([])
let setFieldsSequence = 0
const context = computed(() => props.data?.context || {})
const canEdit = computed(() => Boolean(context.value.name && props.canWrite && !context.value.read_only))
const visibleSetFields = computed(() => setFields.value.filter((field) => !field.hidden))
const signature = computed(() => JSON.stringify({ cloth: clothRows.value, accessory: accessoryRows.value }))
const dirty = computed(() => signature.value !== cleanSignature.value)

function clone(value) { return JSON.parse(JSON.stringify(value ?? [])) }
function applyData() {
	clothRows.value = clone(props.data?.item_details?.cloth_items || [])
	accessoryRows.value = clone(props.data?.item_accessories || [])
	cleanSignature.value = signature.value
	error.value = ""
}
watch(() => props.data, applyData, { immediate: true })
watch(signature, () => emit("dirty-change", dirty.value))
function emptyCloth() { return { cloth_item_variant: "", cloth_type: "", colour: "", dia: "", actual_dia: "", shade: "", fabric_type: "Open Width", weight: 0, balance_weight: 0, no_of_rolls: 0, no_of_bits: 0, end_bit_weight: 0, comments: "", items_json: {}, set_combination: {} } }
function emptyAccessory() { return { accessory: "", cloth_item_variant: "", cloth_type: "", colour: "", dia: "", actual_dia: "", shade: "", weight: 0, no_of_rolls: 0 } }
async function openCloth(row = null, index = -1) { clothIndex.value = index; Object.assign(clothForm, emptyCloth(), clone(row || {}), { set_combination: parseObject(row?.set_combination) }); clothDialog.value = true; await loadSetFields(parseObject(row?.set_combination)) }
async function loadSetFields(existing = null) {
	const sequence = ++setFieldsSequence
	setFields.value = []
	clothForm.set_combination = {}
	if (!clothForm.colour || !context.value.cutting_marker) return
	try {
		const result = await callMethod("essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_input_fields", { cutting_marker: context.value.cutting_marker, colour: clothForm.colour, select_attributes: props.data?.editor?.attributes || { colour: [clothForm.colour] } })
		if (sequence !== setFieldsSequence) return
		const current = existing || {}
		const values = {}
		for (const field of result?.input_fields || []) {
			const options = fieldOptions(field)
			values[field.fieldname] = Object.hasOwn(current, field.fieldname) ? current[field.fieldname] : field.default ?? (options.length === 1 ? options[0] : "")
		}
		setFields.value = result?.input_fields || []
		clothForm.set_combination = values
	} catch (reason) { error.value = reason?.message || "Unable to load set details." }
}
function saveCloth() { if (!clothForm.cloth_type || !clothForm.colour || !clothForm.actual_dia || !clothForm.shade || !clothForm.fabric_type || visibleSetFields.value.some((field) => !hasValue(clothForm.set_combination[field.fieldname]))) return; const row = clone(clothForm); if (clothIndex.value < 0) clothRows.value.push(row); else clothRows.value.splice(clothIndex.value, 1, { ...clothRows.value[clothIndex.value], ...row }); clothDialog.value = false }
function removeCloth(index) { clothRows.value.splice(index, 1) }
function openAccessory(row = null, index = -1) { accessoryIndex.value = index; Object.assign(accessoryForm, emptyAccessory(), clone(row || {})); accessoryDialog.value = true }
function saveAccessory() { if (!accessoryForm.accessory || !accessoryForm.cloth_type || !accessoryForm.colour || !accessoryForm.actual_dia || !accessoryForm.shade) return; const row = clone(accessoryForm); if (accessoryIndex.value < 0) accessoryRows.value.push(row); else accessoryRows.value.splice(accessoryIndex.value, 1, { ...accessoryRows.value[accessoryIndex.value], ...row }); accessoryDialog.value = false }
function removeAccessory(index) { accessoryRows.value.splice(index, 1) }
async function saveIfDirty() {
	if (!dirty.value || !canEdit.value) return null
	saving.value = true; error.value = ""
	try { const workspace = await saveBulkActiveEditor(props.bulkName, props.row.name, clothRows.value, accessoryRows.value, props.modified); cleanSignature.value = signature.value; emit("saved", workspace); return workspace }
	catch (reason) { error.value = reason?.message || "Unable to save LaySheet details."; throw reason }
	finally { saving.value = false }
}
function display(value) { return (value?.value ?? value) || "—" }
function hasValue(value) { return value !== null && value !== undefined && value !== "" }
function parseObject(value) { if (!value) return {}; if (typeof value === "object" && !Array.isArray(value)) return { ...value }; try { const parsed = JSON.parse(value); return typeof parsed === "string" ? JSON.parse(parsed) : parsed || {} } catch { return {} } }
function fieldOptions(field) { return Array.isArray(field.options) ? field.options : String(field.options || "").split("\n").map((value) => value.trim()).filter(Boolean) }
function hasFieldDefault(field) { return field.default !== undefined && field.default !== null && field.default !== "" }
function number(value) { const parsed = Number(value || 0); return parsed ? parsed.toLocaleString(undefined, { maximumFractionDigits: 3 }) : "0" }
function statusSeverity(status) { if (status === "Label Printed") return "success"; if (status === "Bundles Generated") return "info"; if (status === "Approval Pending") return "warn"; return "secondary" }
defineExpose({ saveIfDirty, dirty })
</script>

<style scoped>
.data-panel { min-width: 0; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); overflow: hidden; }.bulk-active-sheet > header { display: flex; min-height: 67px; padding: 11px 13px; align-items: center; justify-content: space-between; gap: 12px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }.bulk-active-sheet > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.bulk-active-sheet > header h2 { margin: 2px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }.bulk-active-sheet > header h2 small { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 600; }.bulk-active-sheet__header-actions { display: flex; align-items: center; gap: 7px; }.bulk-active-sheet > :deep(.p-message) { margin: 10px 12px 0; }
.bulk-active-sheet__body { display: grid; padding: 12px; gap: 12px; }.detail-block { min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); overflow: hidden; }.detail-block > header { display: flex; padding: 8px 10px; align-items: center; justify-content: space-between; gap: 10px; background: var(--erp-surface-muted); border-bottom: 1px solid var(--erp-border); }.detail-block > header div { display: flex; align-items: baseline; gap: 7px; }.detail-block h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-caption); }.detail-block > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.detail-table-scroll { max-height: 280px; overflow: auto; }.detail-block table { width: 100%; min-width: 980px; border-collapse: collapse; }.detail-block th, .detail-block td { padding: 7px 8px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }.detail-block th { position: sticky; z-index: 1; top: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface); }.detail-block td { color: var(--erp-text); font-size: var(--erp-font-size-min); }.detail-block th:last-child, .detail-block td:last-child { border-right: 0; }.detail-block tbody tr:last-child td { border-bottom: 0; }.numeric { text-align: right !important; font-variant-numeric: tabular-nums; }.row-actions { display: flex; justify-content: center; gap: 2px; }.detail-empty { padding: 22px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); text-align: center; }.active-empty { display: grid; min-height: 300px; place-content: center; justify-items: center; gap: 7px; color: var(--erp-text-muted); text-align: center; }.active-empty i { color: var(--erp-accent); font-size: 1.5rem; }.active-empty strong { color: var(--erp-text); }
.bulk-detail-form { display: grid; width: min(760px, calc(100vw - 72px)); grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; }.bulk-detail-form label { display: grid; gap: 6px; }.bulk-detail-form label span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
@media (max-width: 620px) { .bulk-active-sheet > header { align-items: flex-start; flex-direction: column; }.bulk-detail-form { width: min(500px, calc(100vw - 52px)); grid-template-columns: 1fr; } }
</style>
