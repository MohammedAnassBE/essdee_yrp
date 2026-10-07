<template>
	<section class="work-order-editor erp-card erp-editor-shell" aria-label="Work Order editor" :aria-busy="loading">
		<header class="work-order-editor__header erp-editor-header">
			<div><span>{{ name || (duplicateFrom ? `Duplicate of ${duplicateFrom}` : "New document") }}</span><h1>{{ name ? "Edit Work Order" : "New Work Order" }}</h1></div>
			<div class="work-order-editor__actions erp-editor-actions">
				<Button label="Cancel" severity="secondary" text :disabled="busy" @click="requestCancel" />
				<Button v-if="calculationMode" :label="calculationLabel" icon="pi pi-calculator" severity="secondary" outlined :disabled="busy" @click="openCalculation" />
				<Button v-if="canDraft" label="Save" icon="pi pi-save" :loading="saving === 'draft'" :disabled="busy || !canSave" @click="save(false)" />
			</div>
		</header>

		<Message v-if="error && !loadFailed" severity="error" :closable="false">{{ error }}</Message>
		<div v-if="loading" class="work-order-editor__loading" role="status" aria-live="polite" aria-label="Loading Work Order editor"><Skeleton height="170px" /><Skeleton height="420px" /></div>
		<section v-else-if="loadFailed" class="work-order-editor__recovery" role="alert"><i class="pi pi-cloud-times" aria-hidden="true" /><div><strong>Work Order could not be loaded</strong><span>{{ error }}</span></div><Button label="Retry" icon="pi pi-refresh" severity="secondary" outlined @click="load" /></section>
		<div v-else class="work-order-editor__body">
			<section class="work-order-editor__section">
				<header><div><span>Setup</span><h2>Work Order details</h2></div><small>Process, Item and Lot define the calculation source.</small></header>
				<div class="work-order-editor__fields">
					<div class="work-order-editor__group-title"><span>Source</span><strong>Production source</strong></div>
					<LinkField input-id="field-process_name-value" :key="`process-${sourceRevision}`" :model-value="form.process_name" :label="fieldLabel('process_name', 'Process')" doctype="YRP Process" :required="isRequired('process_name')" :show-open-button="false" show-clear :disabled="busy || isReadOnly('process_name')" @update:model-value="changeSource('process_name', $event)" />
					<LinkField input-id="field-lot-value" :key="`lot-${sourceRevision}`" :model-value="form.lot" :label="fieldLabel('lot', 'Lot')" doctype="SD YRP Lot" :required="isRequired('lot')" :show-open-button="false" show-clear :disabled="busy || isReadOnly('lot')" @update:model-value="changeSource('lot', $event)" />
					<LinkField input-id="field-item-value" :key="`item-${sourceRevision}`" :model-value="form.item" :label="fieldLabel('item', 'Item')" doctype="Item" :required="isRequired('item')" :search-handler="searchAllowedItems" :show-open-button="false" show-clear :disabled="busy || isReadOnly('item') || !selectionContext.options?.length" @update:model-value="changeItem" />
					<LinkField v-model="form.production_detail" :label="fieldLabel('production_detail', 'Production detail')" doctype="YRP Item Production Detail" :required="isRequired('production_detail')" :show-open-button="false" :disabled="true" />

					<div class="work-order-editor__group-title"><span>Route</span><strong>Parties & locations</strong></div>
					<LinkField :model-value="form.supplier" :label="fieldLabel('supplier', 'Supplier')" doctype="Supplier" :required="isRequired('supplier')" :show-open-button="false" show-clear :disabled="busy || isReadOnly('supplier')" @update:model-value="changeSupplier" />
					<LinkField v-model="form.supplier_address" :label="fieldLabel('supplier_address', 'Supplier address')" doctype="Address" :required="isRequired('supplier_address')" :search-handler="searchSupplierAddresses" :show-open-button="false" show-clear :disabled="busy || isReadOnly('supplier_address') || !form.supplier" @update:model-value="markDirty" />
					<LinkField :model-value="form.delivery_location" :label="fieldLabel('delivery_location', 'Delivery location')" doctype="Supplier" :required="isRequired('delivery_location')" :show-open-button="false" show-clear :disabled="busy || isReadOnly('delivery_location')" @update:model-value="changeDeliveryLocation" />
					<LinkField v-model="form.delivery_address" :label="fieldLabel('delivery_address', 'Delivery address')" doctype="Address" :required="isRequired('delivery_address')" :search-handler="searchDeliveryAddresses" :show-open-button="false" show-clear :disabled="busy || isReadOnly('delivery_address') || !form.delivery_location" @update:model-value="markDirty" />

					<div class="work-order-editor__group-title"><span>Schedule</span><strong>Planning dates</strong></div>
					<DateField v-model="form.wo_date" class="work-order-editor__schedule-field" :label="fieldLabel('wo_date', 'Work Order date', false)" :required="isRequired('wo_date')" :disabled="busy || isReadOnly('wo_date')" @update:model-value="markDirty" />
					<DateField v-model="form.planned_start_date" class="work-order-editor__schedule-field" :label="fieldLabel('planned_start_date', 'Planned start', false)" :required="isRequired('planned_start_date')" :disabled="busy || isReadOnly('planned_start_date')" @update:model-value="markDirty" />
					<DateField v-model="form.planned_end_date" class="work-order-editor__schedule-field" :label="fieldLabel('planned_end_date', 'Planned end', false)" :required="isRequired('planned_end_date')" :disabled="busy || isReadOnly('planned_end_date')" @update:model-value="markDirty" />
					<DateField v-model="form.expected_delivery_date" class="work-order-editor__schedule-field" :label="fieldLabel('expected_delivery_date', 'Expected delivery', false)" :required="isRequired('expected_delivery_date')" :disabled="busy || isReadOnly('expected_delivery_date')" @update:model-value="markDirty" />

					<div class="work-order-editor__group-title"><span>Controls</span><strong>Terms & notes</strong></div>
					<LinkField v-model="form.terms_and_condition" :label="fieldLabel('terms_and_condition', 'Terms and condition')" doctype="YRP Terms and Condition" :required="isRequired('terms_and_condition')" :show-open-button="false" show-clear :disabled="busy || isReadOnly('terms_and_condition')" @update:model-value="markDirty" />
					<label class="work-order-editor__check"><Checkbox v-model="noReceivables" binary input-id="wo-no-receivables" :disabled="busy || isReadOnly('no_receivables')" @change="markDirty" /><span>{{ fieldLabel('no_receivables', 'No receivables expected', false) }}</span></label>
					<label class="work-order-editor__comments"><span>Comments</span><Textarea v-model="form.comments" rows="2" auto-resize fluid :disabled="busy" @input="markDirty" /></label>
				</div>
			</section>

			<section class="work-order-editor__section work-order-editor__matrix-section"><header><div><span>Inputs</span><h2>Deliverables</h2></div><small>Calculated rows remain grouped through the Work Order controller.</small></header><WorkOrderItemMatrix :groups="deliverableDetails" /></section>
			<section v-if="!noReceivables" class="work-order-editor__section work-order-editor__matrix-section"><header><div><span>Outputs</span><h2>Receivables</h2></div></header><WorkOrderItemMatrix :groups="receivableDetails" /></section>
			<section v-if="editor.calculated_items?.length" class="work-order-editor__section"><header><div><span>Source-owned</span><h2>Calculated items</h2></div><small>{{ editor.calculated_items.length }} rows</small></header><div class="work-order-editor__calculated"><div v-for="(row, index) in editor.calculated_items" :key="row.name || index"><strong>{{ row.item_variant || row.item || row.name }}</strong><span>{{ calculatedRowText(row) }}</span></div></div></section>
		</div>

		<WorkOrderActionPanel v-model:visible="actionVisible" :mode="calculationMode" :work-order="{ name, modified: editor.modified }" :editor="editor" @changed="calculationChanged" />
		<DocumentConfirmationDialog v-model:visible="sourceConfirmVisible" :title="sourceConfirmTitle" :message="sourceConfirmMessage" cancel-label="Keep Current Value" confirm-label="Clear Rows & Continue" :busy="saving === 'source'" :return-focus-selector="sourceReturnFocusSelector" @update:visible="sourceConfirmationVisibilityChanged" @confirm="confirmSourceChange" />
		<Dialog v-model:visible="discardVisible" header="Discard unsaved changes?" modal :closable="false" :style="{ width: 'min(440px, calc(100vw - 32px))' }"><p class="work-order-editor__discard-copy">Your unsaved Work Order changes will be lost.</p><template #footer><Button label="Keep Editing" severity="secondary" text @click="keepEditing" /><Button label="Discard Changes" severity="danger" @click="discardChanges" /></template></Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import { useToast } from "primevue/usetoast"
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave } from "vue-router"

import { getWorkOrderEditor, getWorkOrderSelectionContext, saveWorkOrder } from "../../api/fabricStore.js"
import { searchLinkedDocument } from "../../api/frappe.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import WorkOrderActionPanel from "./WorkOrderActionPanel.vue"
import WorkOrderItemMatrix from "./WorkOrderItemMatrix.vue"

const props = defineProps({ name: { type: String, default: "" }, source: { type: Object, default: () => ({}) } })
const emit = defineEmits(["saved", "cancel"])
const toast = useToast()
const loading = ref(true)
const saving = ref("")
const error = ref("")
const loadFailed = ref(false)
const editor = ref({})
const form = reactive({})
const deliverableDetails = ref([])
const receivableDetails = ref([])
const selectionContext = ref({})
const dirty = ref(false)
const sourceRevision = ref(0)
const discardVisible = ref(false)
const actionVisible = ref(false)
const pendingCancel = ref(false)
const sourceConfirmVisible = ref(false)
const pendingSourceChange = ref(null)
let allowNavigation = false
let pendingNavigation = null

const busy = computed(() => loading.value || Boolean(saving.value))
const noReceivables = computed({ get: () => Boolean(Number(form.no_receivables)), set: (value) => { form.no_receivables = value ? 1 : 0 } })
const canDraft = computed(() => props.name ? Boolean(editor.value.permissions?.can_write) : Boolean(editor.value.permissions?.can_create))
const standardFieldnames = new Set(["supplier", "process_name", "lot", "item", "production_detail", "wo_date", "planned_start_date", "planned_end_date", "expected_delivery_date", "delivery_location", "supplier_address", "delivery_address", "terms_and_condition", "no_receivables", "comments"])
const fieldMetadata = computed(() => new Map((editor.value.fields || []).map((field) => [field.fieldname, field])))
const canSave = computed(() => {
	const fallbackRequired = ["supplier", "process_name", "lot", "item", "production_detail", "wo_date"]
	const requiredFields = editor.value.fields?.length
		? editor.value.fields.filter((field) => isRequired(field.fieldname)).map((field) => field.fieldname)
		: fallbackRequired
	return [...new Set(requiredFields)].every((fieldname) => hasValue(form[fieldname]))
})
const hasRows = computed(() => deliverableDetails.value.some((group) => group.items?.length) && (noReceivables.value || receivableDetails.value.some((group) => group.items?.length)))
const calculationMode = computed(() => editor.value.calculation_contexts?.fabric ? "calculate_fabric" : editor.value.calculation_contexts?.garment ? "calculate_garment" : "")
const calculationLabel = computed(() => calculationMode.value === "calculate_fabric" ? "Calculate Fabric Deliverables" : "Calculate Items")
const duplicateFrom = computed(() => String(props.source?.duplicate_from || ""))
const sourceConfirmTitle = computed(() => `Change ${pendingSourceChange.value?.label || "source"}?`)
const sourceConfirmMessage = computed(() => `Changing ${pendingSourceChange.value?.label || "this source"} will clear the calculated deliverable and receivable rows. This keeps the Work Order consistent with its new source.`)
const sourceReturnFocusSelector = computed(() => pendingSourceChange.value?.kind === "item" ? "#field-item-value" : pendingSourceChange.value?.fieldname ? `#field-${pendingSourceChange.value.fieldname}-value` : "")

function clone(value) { return JSON.parse(JSON.stringify(value ?? [])) }
function hasValue(value) { return value !== null && value !== undefined && String(value).trim() !== "" }
function evaluateCondition(condition, fallback = false) {
	if (!condition) return fallback
	const expression = String(condition).replace(/^eval:/, "").trim()
	const direct = expression.match(/^(!)?doc\.([A-Za-z0-9_]+)$/)
	if (!direct) return fallback
	const value = Boolean(form[direct[2]] ?? editor.value.condition_values?.[direct[2]])
	return direct[1] ? !value : value
}
function isRequired(fieldname) {
	const field = fieldMetadata.value.get(fieldname) || {}
	return Boolean(field.reqd) || evaluateCondition(field.mandatory_depends_on)
}
function isReadOnly(fieldname) {
	const field = fieldMetadata.value.get(fieldname) || {}
	return Boolean(field.read_only) || evaluateCondition(field.read_only_depends_on)
}
function fieldLabel(fieldname, fallback, showRequired = true) {
	const label = fieldMetadata.value.get(fieldname)?.label || fallback
	return `${label}${showRequired && isRequired(fieldname) ? " *" : ""}`
}
async function load() {
	loading.value = true; loadFailed.value = false; error.value = ""
	try {
		editor.value = await getWorkOrderEditor(props.name, props.source) || {}
		for (const key of Object.keys(form)) delete form[key]
		Object.assign(form, editor.value.values || {})
		deliverableDetails.value = clone(editor.value.deliverable_details)
		receivableDetails.value = clone(editor.value.receivable_details)
		selectionContext.value = clone(editor.value.selection_context || {})
		dirty.value = false
	} catch (reason) { loadFailed.value = true; error.value = reason?.message || "Unable to load the Work Order editor." }
	finally { loading.value = false }
}
function markDirty() { if (!loading.value) dirty.value = true }
function changeSupplier(value) { if (value === form.supplier) return; form.supplier = value || ""; form.supplier_address = ""; markDirty() }
function changeDeliveryLocation(value) { if (value === form.delivery_location) return; form.delivery_location = value || ""; form.delivery_address = ""; markDirty() }
function searchSupplierAddresses(text) { return searchLinkedDocument("Address", "Supplier", form.supplier, text) }
function searchDeliveryAddresses(text) { return searchLinkedDocument("Address", "Supplier", form.delivery_location, text) }
function hasCalculatedWork() { return Boolean(editor.value.calculated_items?.length || deliverableDetails.value.some((group) => group.items?.length) || receivableDetails.value.some((group) => group.items?.length)) }
async function changeSource(fieldname, value) {
	if (value === form[fieldname]) return
	if (hasCalculatedWork()) {
		pendingSourceChange.value = { kind: "source", fieldname, value, label: fieldname === "lot" ? "Lot" : "Process" }
		sourceConfirmVisible.value = true
		return
	}
	await applySourceChange(fieldname, value)
}
async function applySourceChange(fieldname, value) {
	const candidate = { lot: form.lot, process_name: form.process_name, [fieldname]: value }
	saving.value = "source"; error.value = ""
	try {
		const context = candidate.lot && candidate.process_name ? await getWorkOrderSelectionContext(candidate.lot, candidate.process_name) : { options: [], item_options: [] }
		form[fieldname] = value
		selectionContext.value = context || {}
		if (!(context.options || []).some((row) => row.item === form.item && row.production_detail === form.production_detail)) { form.item = ""; form.production_detail = "" }
		clearCalculatedRows(); markDirty(); sourceRevision.value += 1
	} catch (reason) { error.value = reason?.message || "Unable to validate this Work Order source."; sourceRevision.value += 1 }
	finally { saving.value = "" }
}
function changeItem(value) {
	if (value === form.item) return
	if (hasCalculatedWork()) {
		pendingSourceChange.value = { kind: "item", value, label: "Item" }
		sourceConfirmVisible.value = true
		return
	}
	applyItemChange(value)
}
function applyItemChange(value) {
	const option = (selectionContext.value.options || []).find((row) => row.item === value)
	form.item = option?.item || ""
	form.production_detail = option?.production_detail || ""
	clearCalculatedRows(); markDirty(); sourceRevision.value += 1
}
async function confirmSourceChange() {
	const change = pendingSourceChange.value
	const returnFocusSelector = change?.kind === "item" ? "#field-item-value" : change?.fieldname ? `#field-${change.fieldname}-value` : ""
	pendingSourceChange.value = null
	sourceConfirmVisible.value = false
	if (!change) return
	if (change.kind === "item") applyItemChange(change.value)
	else await applySourceChange(change.fieldname, change.value)
	await restoreSourceFocus(returnFocusSelector)
}
async function restoreSourceFocus(selector) {
	if (!selector || typeof document === "undefined") return
	await nextTick()
	window.requestAnimationFrame(() => window.requestAnimationFrame(() => document.querySelector(selector)?.focus?.()))
}
function sourceConfirmationVisibilityChanged(visible) {
	sourceConfirmVisible.value = visible
	if (visible || !pendingSourceChange.value) return
	pendingSourceChange.value = null
	sourceRevision.value += 1
}
function clearCalculatedRows() { deliverableDetails.value = []; receivableDetails.value = []; editor.value.calculated_items = []; editor.value.calculation_contexts = {} }
function searchAllowedItems(text) {
	const needle = String(text || "").toLowerCase()
	return Promise.resolve((selectionContext.value.item_options || []).filter((item) => String(item).toLowerCase().includes(needle)).map((item) => ({ name: item, label: item })))
}
function openCalculation() {
	if (dirty.value) { error.value = "Save the Work Order changes before calculating items."; return }
	actionVisible.value = true
}
async function calculationChanged() { await load() }
async function save(submit) {
	saving.value = submit ? "submit" : "draft"; error.value = ""
	try {
		const payload = await saveWorkOrder({ ...form, deliverable_details: clone(deliverableDetails.value), receivable_details: clone(receivableDetails.value) }, { name: props.name, submit, expectedModified: editor.value.modified })
		const record = payload?.record || {}
		dirty.value = false; allowNavigation = true
		toast.add({ severity: "success", summary: submit ? "Work Order submitted" : "Work Order saved", detail: record.name || "Your changes are saved.", life: 3500 })
		emit("saved", record)
	} catch (reason) { const message = reason?.message || "Unable to save this Work Order."; error.value = message; toast.add({ severity: "error", summary: "Work Order was not saved", detail: message, life: 6500 }) }
	finally { saving.value = "" }
}
function requestCancel() { if (!dirty.value) return emit("cancel"); pendingCancel.value = true; discardVisible.value = true }
function keepEditing() { discardVisible.value = false; pendingCancel.value = false; if (pendingNavigation) { pendingNavigation(false); pendingNavigation = null } }
function discardChanges() { discardVisible.value = false; allowNavigation = true; if (pendingCancel.value) { pendingCancel.value = false; emit("cancel"); return } const next = pendingNavigation; pendingNavigation = null; next?.() }
function beforeUnload(event) { if (!dirty.value) return; event.preventDefault(); event.returnValue = "" }
function calculatedRowText(row) { return [row.quantity ?? row.qty, row.uom, row.source_process].filter((value) => value !== undefined && value !== null && value !== "").join(" · ") || "Calculated row" }

onBeforeRouteLeave((_to, _from, next) => { if (allowNavigation || !dirty.value) return next(); pendingNavigation = next; discardVisible.value = true })
onMounted(() => { window.addEventListener("beforeunload", beforeUnload); load() })
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
watch(() => props.name, load)
</script>

<style scoped>
.work-order-editor { --work-order-editor-inline: clamp(14px, 1.5vw, 24px); display: flex; width: 100%; min-height: calc(100dvh - var(--erp-shell-header-height) - 78px); flex-direction: column; gap: var(--erp-space-3); padding: 0 var(--work-order-editor-inline) var(--erp-space-4); border-color: color-mix(in srgb, var(--erp-border) 84%, white); background: color-mix(in srgb, var(--erp-bg) 72%, white); }
.work-order-editor__header { position: sticky; z-index: var(--erp-layer-sticky); top: 0; display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-4); margin: 0 calc(0px - var(--work-order-editor-inline)); padding: 12px var(--work-order-editor-inline); border-top: 3px solid var(--erp-accent); border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface) 96%, var(--erp-accent-soft)); box-shadow: 0 5px 16px rgb(28 61 45 / 5%); }
.work-order-editor__header > div:first-child { display: grid; gap: 2px; }
.work-order-editor__header span, .work-order-editor__section > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }
.work-order-editor__header h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -.025em; }
.work-order-editor__actions { display: flex; justify-content: flex-end; gap: var(--erp-space-2); flex-wrap: wrap; }
.work-order-editor__loading, .work-order-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.work-order-editor__recovery { display: grid; min-height: 220px; place-content: center; justify-items: center; gap: 10px; padding: var(--erp-space-6); color: var(--erp-text-muted); text-align: center; border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.work-order-editor__recovery > i { color: var(--erp-danger); font-size: 24px; }.work-order-editor__recovery > div { display: grid; gap: 4px; }.work-order-editor__recovery strong { color: var(--erp-text); }.work-order-editor__recovery span { max-width: 520px; font-size: var(--erp-font-size-caption); }
.work-order-editor__section { display: grid; gap: var(--erp-space-3); padding: clamp(14px, 1.4vw, 22px); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 8px 24px rgb(28 61 45 / 4%); }
.work-order-editor__section > header { display: flex; align-items: end; justify-content: space-between; gap: 12px; }
.work-order-editor__section h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.work-order-editor__section small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-editor__fields, .work-order-editor__dimensions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: end; gap: 10px 14px; }
.work-order-editor__group-title { display: flex; grid-column: 1 / -1; min-height: 27px; align-items: center; gap: 9px; margin-top: 2px; padding-top: 6px; border-top: 1px solid color-mix(in srgb, var(--erp-border) 78%, white); }
.work-order-editor__group-title:first-child { margin-top: 0; padding-top: 0; border-top: 0; }
.work-order-editor__group-title span { color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.work-order-editor__group-title strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.work-order-editor__dimensions { padding-top: var(--erp-space-3); border-top: 1px solid var(--erp-border); }
.work-order-editor__check { display: flex; min-height: var(--erp-control-height); align-items: center; gap: 8px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.work-order-editor__comments { display: grid; grid-column: span 2; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.work-order-editor__calculated { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.work-order-editor__calculated > div { display: grid; gap: 3px; padding: 9px 11px; border-left: 3px solid color-mix(in srgb, var(--erp-accent) 58%, white); background: var(--erp-surface-soft); border-radius: 0 var(--erp-control-radius) var(--erp-control-radius) 0; }
.work-order-editor__calculated strong { overflow: hidden; font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.work-order-editor__calculated span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-editor__discard-copy { margin: 0; color: var(--erp-text-muted); line-height: 1.5; }
@media (max-width: 1180px) { .work-order-editor__fields, .work-order-editor__dimensions { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) { .work-order-editor__fields, .work-order-editor__dimensions { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .work-order-editor { padding: 0 var(--erp-space-3) var(--erp-space-3); } .work-order-editor__header { align-items: stretch; flex-direction: column; margin: 0 calc(var(--erp-space-3) * -1); padding: 10px var(--erp-space-3); } .work-order-editor__section { padding: var(--erp-space-3); } .work-order-editor__section > header small { display: none; } .work-order-editor__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } .work-order-editor__fields > :not(.work-order-editor__schedule-field) { grid-column: 1 / -1; } .work-order-editor__schedule-field :deep(.p-datepicker-input) { padding-inline: 8px; font-size: 13px; } .work-order-editor__schedule-field :deep(.p-datepicker-dropdown) { width: 32px; min-width: 32px; } .work-order-editor__dimensions, .work-order-editor__calculated { grid-template-columns: 1fr; } .work-order-editor__comments { grid-column: auto; } .work-order-editor__actions { width: 100%; } .work-order-editor__actions :deep(.p-button) { flex: 1; } }
</style>
