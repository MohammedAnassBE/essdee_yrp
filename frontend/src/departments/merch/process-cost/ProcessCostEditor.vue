<template>
	<DepartmentPage title="Process Cost" :back-to="backTo" :back-label="processCostId ? 'Process Cost' : 'Process Costs'" :show-title="false" flat full-width inline-navigation>
		<section class="process-cost-editor erp-workspace">
			<header class="process-cost-editor__header">
				<InlinePageNavigation title-target="process-cost-editor-title" />
				<h1 id="process-cost-editor-title" class="erp-doc-title">{{ processCostId ? 'Edit Process Cost' : 'New Process Cost' }}</h1>
				<Button label="Cancel" severity="secondary" text :disabled="saving" @click="router.push(backTo)" />
				<Button v-if="!loading && !loadError" label="Save" icon="pi pi-check" :loading="saving" :disabled="contextLoading || Boolean(contextError) || hasInvalidCells" @click="save" />
			</header>
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<div v-else-if="loading" class="erp-empty-state">Loading Process Cost…</div>
			<form v-else class="process-cost-editor__body" @submit.prevent="save">
				<section class="process-cost-editor__card">
					<h2>Details</h2>
					<div class="process-cost-editor__fields">
						<template v-for="field in detailFields" :key="field.fieldname">
							<div v-if="field.fieldname === 'item' && context.is_cloth_process" class="process-cost-editor__field">
								<label for="process-cost-cloth-item">Item <span class="erp-required-mark">*</span></label>
								<Select input-id="process-cost-cloth-item" :model-value="form.item" :options="context.item_options || []" option-label="item" option-value="item" :invalid="Boolean(errors.item)" :disabled="saving || contextLoading" fluid @update:model-value="change('item', $event)" />
								<small v-if="errors.item || lookupErrors.item" class="process-cost-editor__error" role="alert">{{ errors.item || lookupErrors.item }}</small>
							</div>
							<div v-else-if="field.read_only" class="process-cost-editor__field">
								<span :id="`process-cost-${field.fieldname}-label`" class="erp-field-label">{{ field.label }} <span v-if="requiredFields.has(field.fieldname)" class="erp-required-mark">*</span></span>
								<output :aria-labelledby="`process-cost-${field.fieldname}-label`" class="process-cost-editor__value">{{ form[field.fieldname] || '—' }}</output>
								<small v-if="errors[field.fieldname]" class="process-cost-editor__error" role="alert">{{ errors[field.fieldname] }}</small>
							</div>
							<FormField v-else :field="field" :model-value="form[field.fieldname]" :reset-version="fieldResetVersion" :form="form" :required="requiredFields.has(field.fieldname)" :error="errors[field.fieldname] || lookupErrors[field.fieldname] || ''" :invalid="Boolean(errors[field.fieldname] || lookupErrors[field.fieldname])" :disabled="isDisabled(field)" :show-open-button="false" show-clear :search-handler="field.fieldname === 'attribute' ? searchAttributes : null" @update:model-value="change(field.fieldname, $event)" />
						</template>
					</div>
					<p class="process-cost-editor__fact">Depends On Attribute: {{ Number(form.depends_on_attribute) ? 'Yes' : 'No' }}</p>
				</section>
				<WorkspaceLoadError v-if="contextError" :message="contextError" :loading="contextLoading" @retry="refreshContext(false)" />
				<div v-if="contextLoading" role="status">Loading Item and Attribute Values…</div>
				<ProcessCostGrid :key="gridVersion" v-model:tiers="form.process_cost_values" :fields="editor.tier_fields" :values="context.attribute_values || []" :attribute="form.attribute || ''" :readonly="saving || contextLoading || Boolean(contextError)" :errors="gridErrors" :message="errors.process_cost_values || ''" />
			</form>
		</section>
		<DocumentConfirmationDialog :visible="Boolean(pendingChange)" title="Regenerate Process Cost Values?" message="Changing this field replaces the entered prices. Continue?" confirm-label="Regenerate" cancel-label="Keep Values" :busy="contextLoading" @update:visible="!$event && cancelChange()" @confirm="confirmChange" />
		<DocumentConfirmationDialog v-model:visible="discardVisible" title="Discard unsaved changes?" message="Your unsaved Process Cost changes will be lost." confirm-label="Discard Changes" cancel-label="Keep Editing" @update:visible="!$event && finishNavigation(false)" @confirm="finishNavigation(true)" />
		<DocumentErrorDialog :message="saveError" title="Process Cost could not be saved" :retry-label="isStale ? 'Reload' : ''" @dismiss="saveError = ''" @retry="reload" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, onBeforeUnmount, provide, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"
import { getDoc } from "../../../api/frappe.js"
import { getProcessCostEditor, getProcessCostGrid, saveProcessCost, searchProcessCostAttributes } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import FormField from "../../../components/common/FormField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import { ENTRY_GRID_INVALID_KEY } from "../../../components/common/entryGrid.js"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import InlinePageNavigation from "../../../components/navigation/InlinePageNavigation.vue"
import ProcessCostGrid from "./ProcessCostGrid.vue"
import { PROCESS_COST_DETAILS, PROCESS_COST_LIST_PATH, mergeProcessCostRows, processCostFieldError, processCostPath, validateProcessCostRows } from "./processCostViews.js"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../../../utils/newDocumentDefaults.js"

const props = defineProps({ processCostId: { type: String, default: "" } })
const route = useRoute()
const router = useRouter()
const editor = ref({})
const form = reactive({ process_cost_values: [] })
const context = ref({})
const loading = ref(true)
const contextLoading = ref(false)
const contextError = ref("")
const saving = ref(false)
const loadError = ref("")
const saveError = ref("")
const isStale = ref(false)
const errors = ref({})
const lookupErrors = ref({})
const gridErrors = ref({})
const pendingChange = ref(null)
const fieldResetVersion = ref(0)
const gridVersion = ref(0)
const discardVisible = ref(false)
const cleanSignature = ref("")
const invalidGrids = reactive({})
const hasInvalidCells = computed(() => Object.values(invalidGrids).some(Boolean))
provide(ENTRY_GRID_INVALID_KEY, { report: (id, count) => { invalidGrids[id] = count } })
const requiredFields = new Set(["lot", "process_name", "item", "uom", "supplier", "from_date", "tax_slab"])
const backTo = computed(() => props.processCostId ? processCostPath(props.processCostId) : PROCESS_COST_LIST_PATH)
const dirty = computed(() => !loading.value && JSON.stringify(form) !== cleanSignature.value)
const detailFields = computed(() => PROCESS_COST_DETAILS.map((key) => {
	const field = editor.value.fields?.find((field) => field.fieldname === key)
	return { ...field, read_only: ["item", "uom", "supplier_name"].includes(key) ? 1 : 0,
		link_filters: key === "tax_slab" ? { enabled: 1 } : {},
		description: key === "attribute" && (!form.lot || !form.process_name) ? "Select Lot and Process first" : "",
	}
}))
let requestSequence = 0
let contextSequence = 0
let supplierSequence = 0
let allowNavigation = false
let resolveNavigation = null
const takenDefaults = takeNewDocumentDefaults("YRP Process Cost")
let filterDefaults = props.processCostId || route.query.duplicate_from || route.query.lot ? {} : takenDefaults

function isDisabled(field) {
	if (saving.value || contextLoading.value || field.read_only) return true
	return field.fieldname === "attribute" && (!form.lot || !form.process_name || !form.item)
}
async function searchAttributes(text) {
	const sequence = contextSequence
	const result = await searchProcessCostAttributes(form, text)
	if (sequence !== contextSequence) return []
	lookupErrors.value = result.field_errors || {}
	return result.options || []
}
async function load() {
	const sequence = ++requestSequence
	++contextSequence
	++supplierSequence
	loading.value = true
	contextLoading.value = false
	loadError.value = ""
	contextError.value = ""
	errors.value = {}
	lookupErrors.value = {}
	gridErrors.value = {}
	try {
		const duplicateFrom = props.processCostId ? null : route.query.duplicate_from || null
		const result = await getProcessCostEditor(props.processCostId || null, route.query.lot || filterDefaults.lot || null, duplicateFrom)
		if (sequence !== requestSequence) return
		editor.value = result
		context.value = result.context
		lookupErrors.value = result.context.field_errors || {}
		Object.assign(form, result.values)
		form.process_cost_values = mergeProcessCostRows(result.context.attribute_values, result.values.process_cost_values, form.attribute)
		gridVersion.value++
		fieldResetVersion.value++
		cleanSignature.value = duplicateFrom ? "" : JSON.stringify(form)
		applyFilterDefaults()
	} catch (reason) { if (sequence === requestSequence) loadError.value = reason.message }
	finally { if (sequence === requestSequence) loading.value = false }
}

/** Fills list filter values the editor left empty; the server-loaded Lot context, Item and UOM stay computed. */
function applyFilterDefaults() {
	const editable = new Set(PROCESS_COST_DETAILS.filter((key) => !["lot", "item", "uom", "supplier_name"].includes(key)))
	const defaults = Object.fromEntries(Object.entries(filterDefaults).filter(([key]) => editable.has(key)))
	filterDefaults = {}
	const filled = withNewDocumentDefaults(form, defaults)
	const changed = Object.keys(defaults).filter((key) => filled[key] !== form[key])
	for (const key of changed) form[key] = filled[key]
	if (changed.includes("supplier")) updateSupplier(form.supplier)
	if (form.lot && changed.some((key) => ["process_name", "attribute"].includes(key))) refreshContext(true)
}
function change(key, value) {
	if (["lot", "process_name", "item", "attribute"].includes(key)) {
		if (value === form[key]) return
		if (form.process_cost_values.some((row) => Number(row.price) > 0)) { pendingChange.value = { key, value }; return }
		applyChange(key, value)
		return
	}
	form[key] = value
	delete errors.value[key]
	if (key === "supplier") updateSupplier(value)
}
function confirmChange() {
	const { key, value } = pendingChange.value
	pendingChange.value = null
	applyChange(key, value)
}
function cancelChange() { pendingChange.value = null; fieldResetVersion.value++ }
function applyChange(key, value) {
	form[key] = value
	if (key !== "attribute") form.attribute = ""
	if (["lot", "process_name"].includes(key)) form.item = null
	errors.value = {}
	lookupErrors.value = {}
	gridErrors.value = {}
	refreshContext(true)
}
async function updateSupplier(name) {
	const sequence = ++supplierSequence
	form.supplier_name = ""
	if (!name) return
	try {
		const supplier = await getDoc("Supplier", name)
		if (sequence === supplierSequence) form.supplier_name = supplier.supplier_name
	} catch (reason) { if (sequence === supplierSequence) errors.value.supplier = reason.message }
}
async function refreshContext(reset) {
	const sequence = ++contextSequence
	contextLoading.value = true
	contextError.value = ""
	try {
		const result = await getProcessCostGrid(form)
		if (sequence !== contextSequence) return
		context.value = result
		lookupErrors.value = result.field_errors || {}
		form.item = result.item
		form.uom = result.uom
		form.process_cost_values = mergeProcessCostRows(result.attribute_values, reset ? [] : form.process_cost_values, form.attribute)
		gridVersion.value++
	} catch (reason) { if (sequence === contextSequence) contextError.value = reason.message }
	finally { if (sequence === contextSequence) contextLoading.value = false }
}

function validate() {
	errors.value = {}
	for (const field of detailFields.value) {
		if (requiredFields.has(field.fieldname) && !form[field.fieldname]) errors.value[field.fieldname] = `${field.label} is required.`
	}
	const grid = validateProcessCostRows(form.process_cost_values, form.attribute, context.value.attribute_values || [])
	gridErrors.value = grid.cells
	if (grid.message) errors.value.process_cost_values = grid.message
	return !Object.keys(errors.value).length && !Object.keys(grid.cells).length
}
async function save() {
	if (isSaveBlocked() || !validate()) return
	saving.value = true
	saveError.value = ""
	try {
		const result = await saveProcessCost(form, props.processCostId || null, editor.value.modified)
		allowNavigation = true
		await router.push(processCostPath(result.record.name))
	} catch (reason) { showSaveError(reason) }
	finally { saving.value = false }
}
function isSaveBlocked() { return saving.value || contextLoading.value || Boolean(contextError.value) || hasInvalidCells.value }
function showSaveError(reason) {
	const parsed = processCostFieldError(reason, editor.value.fields)
	errors.value = parsed.field_errors
	if (parsed.row != null) gridErrors.value = { [`tier-${parsed.row}`]: { [parsed.column || "price"]: Object.values(parsed.field_errors)[0] } }
	isStale.value = reason.exc_type === "TimestampMismatchError" || /changed after you opened|Reload the record/.test(reason.message)
	saveError.value = parsed.message || Object.values(parsed.field_errors).join("\n")
}
function reload() { saveError.value = ""; load() }
function guardNavigation() {
	if (saving.value) return false
	if (allowNavigation || !dirty.value) return true
	discardVisible.value = true
	return new Promise((resolve) => { resolveNavigation = resolve })
}
function finishNavigation(allowed) {
	const resolve = resolveNavigation
	resolveNavigation = null
	discardVisible.value = false
	resolve?.(allowed)
}
function beforeUnload(event) {
	if (!dirty.value) return
	event.preventDefault()
	event.returnValue = ""
}
onBeforeRouteLeave(() => allowNavigation ? true : guardNavigation())
onBeforeRouteUpdate(guardNavigation)
window.addEventListener("beforeunload", beforeUnload)
onBeforeUnmount(() => { ++requestSequence; ++contextSequence; ++supplierSequence; window.removeEventListener("beforeunload", beforeUnload); finishNavigation(false) })
watch(() => [props.processCostId, route.query.lot, route.query.duplicate_from], load, { immediate: true })
</script>

<style scoped>
.process-cost-editor { min-width: 0; padding: clamp(12px, 2vw, 24px); }
.process-cost-editor__header { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 20px; }
.process-cost-editor__header h1 { flex: 1; min-width: 180px; }
.process-cost-editor__body { display: grid; min-width: 0; gap: 18px; }
.process-cost-editor__card { min-width: 0; padding: 18px; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.process-cost-editor__card h2 { margin: 0 0 18px; font-size: 16px; }
.process-cost-editor__fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 24px; }
.process-cost-editor__field { min-width: 0; display: grid; gap: 6px; }
.process-cost-editor__value { min-height: 38px; display: flex; align-items: center; overflow-wrap: anywhere; }
.process-cost-editor__error { color: var(--erp-danger); }
.process-cost-editor__fact { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
@media (max-width: 650px) { .process-cost-editor__fields { grid-template-columns: minmax(0, 1fr); } }
</style>
