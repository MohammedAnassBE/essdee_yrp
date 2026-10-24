<template>
	<section class="purchase-order-editor erp-card erp-editor-shell" aria-label="Purchase Order editor" :aria-busy="loading">
		<header class="purchase-order-editor__header erp-editor-header">
			<div><span>{{ name || (duplicateFrom ? `Duplicate of ${duplicateFrom}` : "New document") }}</span><h1 class="erp-doc-title">{{ name ? "Edit Purchase Order" : "New Purchase Order" }}</h1></div>
			<div class="erp-editor-actions">
				<Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="busy" @click="requestCancel" />
				<Button v-if="canDraft" label="Save" icon="pi pi-save" :loading="saving === 'draft'" :disabled="busy || !canSave" @click="save(false)" />
			</div>
		</header>

		<DocumentErrorDialog
			:message="loadFailed ? '' : error"
			title="Purchase Order could not be saved"
		/>
		<div v-if="loading" class="purchase-order-editor__loading" role="status" aria-live="polite" aria-label="Loading Purchase Order editor"><Skeleton height="160px" /><Skeleton height="420px" /></div>
		<section v-else-if="loadFailed" class="purchase-order-editor__recovery" role="alert"><i class="pi pi-cloud-times" aria-hidden="true" /><div><strong>Purchase Order could not be loaded</strong><span>{{ error || "Try loading the Purchase Order again." }}</span></div><Button label="Retry" icon="pi pi-refresh" severity="secondary" outlined @click="load" /></section>
		<div v-else class="purchase-order-editor__body">
			<Message v-if="itemValidationError" severity="warn" :closable="false">{{ itemValidationError }}</Message>
			<section class="purchase-order-editor__section purchase-order-editor__document-setup">
				<header><div><span>Document setup</span><h2>Series & order date</h2></div><small>Set the document identity, company and transaction currency.</small></header>
				<div class="purchase-order-editor__document-fields">
					<label class="purchase-order-editor__control" for="po-naming-series"><span class="erp-field-label">{{ fieldLabel('naming_series', 'Naming Series', false) }}<span v-if="isRequired('naming_series', true)" class="erp-required-mark" aria-hidden="true">*</span></span><Select v-model="form.naming_series" input-id="po-naming-series" :aria-label="fieldLabel('naming_series', 'Naming Series', true, true)" aria-required="true" :options="fieldOptions('naming_series')" :disabled="busy || isReadOnly('naming_series')" fluid @change="markDirty" /></label>
					<DateField v-model="form.transaction_date" class="purchase-order-editor__date" :label="fieldLabel('transaction_date', 'Order date', false)" :required="isRequired('transaction_date', true)" :disabled="busy || isReadOnly('transaction_date')" @update:model-value="markDirty" />
					<LinkField v-model="form.company" :label="fieldLabel('company', 'Company', false)" doctype="Company" :required="isRequired('company')" show-clear :disabled="busy || isReadOnly('company')" @update:model-value="markDirty" />
					<LinkField v-model="form.currency" :label="fieldLabel('currency', 'Currency', false)" doctype="Currency" :required="isRequired('currency')" show-clear :disabled="busy || isReadOnly('currency')" @update:model-value="markDirty" />
				</div>
			</section>

			<div class="purchase-order-editor__card-grid">
				<section class="purchase-order-editor__section purchase-order-editor__entry-card">
					<header><div><span>Procurement</span><h2>Supplier & schedule</h2></div><small>Choose the supplier and required delivery date.</small></header>
					<div class="purchase-order-editor__fields">
						<LinkField input-id="field-supplier-value" :reset-version="sourceRevision" :model-value="form.supplier" :label="fieldLabel('supplier', 'Supplier', true, true)" doctype="Supplier" :required="isRequired('supplier', true)" :filters="{ disabled: 0 }" show-clear :disabled="loading || composerPreparing || previewPending || (Boolean(saving) && saving !== 'source') || isReadOnly('supplier')" @update:model-value="changeSupplier" />
						<DateField v-model="form.schedule_date" class="purchase-order-editor__date" :label="fieldLabel('schedule_date', 'Required by', false)" :required="isRequired('schedule_date', true)" :disabled="busy || isReadOnly('schedule_date')" @update:model-value="markDirty" />
					</div>
				</section>

				<section class="purchase-order-editor__section purchase-order-editor__entry-card">
					<header><div><span>Destination</span><h2>Delivery destination</h2></div><small>Choose the receiving location and warehouse.</small></header>
					<div class="purchase-order-editor__fields purchase-order-editor__delivery-fields">
						<label class="purchase-order-editor__check"><Checkbox v-model="deliverToSupplier" binary input-id="po-deliver-to-supplier" :disabled="busy || isReadOnly('deliver_to_supplier')" @change="deliveryModeChanged" /><span>{{ fieldLabel('deliver_to_supplier', 'Deliver to supplier', false) }}</span></label>
						<LinkField :model-value="form.default_delivery_location" :label="fieldLabel('default_delivery_location', 'Delivery location', false)" doctype="Supplier" :required="isRequired('default_delivery_location')" :filters="deliveryLocationFilters" show-clear :disabled="busy || isReadOnly('default_delivery_location')" @update:model-value="changeDeliveryLocation" />
						<LinkField v-model="form.set_warehouse" :label="fieldLabel('set_warehouse', 'Delivery warehouse', true, true)" doctype="Warehouse" :required="isRequired('set_warehouse', true)" :filters="deliveryWarehouseFilters" show-clear :disabled="busy || isReadOnly('set_warehouse') || !form.default_delivery_location" @update:model-value="markDirty" />
					</div>
				</section>

				<section class="purchase-order-editor__section purchase-order-editor__entry-card purchase-order-editor__notes-card">
					<header><div><span>Commercial</span><h2>Terms & notes</h2></div><small>Capture the agreed terms and operator comments.</small></header>
					<div class="purchase-order-editor__fields">
						<LinkField v-model="form.terms_and_condition" :label="fieldLabel('terms_and_condition', 'Terms and condition', false)" doctype="YRP Terms and Condition" :required="isRequired('terms_and_condition')" show-clear :disabled="busy || isReadOnly('terms_and_condition')" @update:model-value="markDirty" />
						<label class="purchase-order-editor__comments"><span class="erp-field-label">{{ fieldLabel('comments', 'Comments', false) }}</span><Textarea v-model="form.comments" rows="3" auto-resize fluid :disabled="busy || isReadOnly('comments')" @input="markDirty" /></label>
					</div>
				</section>
			</div>

			<StockItemComposer
				v-model="itemGroups"
				operation="purchase_order"
				:editor="composerEditor"
				:schema-loader="loadItemSchema"
				:row-preparer="prepareItemPrice"
				:groups-preparer="previewItemPrices"
				:entry-defaults="composerEntryDefaults"
				:entry-fields="['stock_uom', 'conversion_factor', 'set_combination']"
				:currency="form.currency"
				:disabled="Boolean(saving) || previewPending"
				natural-table-flow
				@dirty="markDirty"
				@preparing-change="composerPreparing = $event"
			>
				<template #entry-fields="{ values, schema }">
					<div class="purchase-order-editor__item-details">
						<LinkField
							:model-value="values.delivery_location"
							label="Delivery location *"
							doctype="Supplier"
							:filters="deliveryLocationFilters"
							:show-open-button="false"
							:disabled="busy"
							required
							@update:model-value="values.delivery_location = $event"
						/>
						<DateField :model-value="values.schedule_date" label="Required by" required :disabled="busy" @update:model-value="setItemRequiredBy(values, $event)" />
						<label class="purchase-order-editor__item-check"><Checkbox :model-value="Boolean(values.fetch_delivery_date)" binary :disabled="busy" @update:model-value="values.fetch_delivery_date = $event ? 1 : 0" /><span>Use Item Price lead time</span></label>
						<label class="purchase-order-editor__item-control"><span class="erp-field-label">Discount %</span><InputNumber :model-value="Number(values.discount_percentage || 0)" :min="0" :max="100" :max-fraction-digits="2" fluid :disabled="busy" @update:model-value="values.discount_percentage = Number($event || 0)" /></label>
						<label class="purchase-order-editor__item-control purchase-order-editor__item-comments"><span class="erp-field-label">Comments</span><Textarea :model-value="values.comments || ''" rows="1" auto-resize fluid :disabled="busy" @update:model-value="values.comments = $event" /></label>
						<LinkField
							v-for="parameter in values.additional_parameters || []"
							:key="parameter.additional_parameter_key"
							:model-value="parameter.additional_parameter_value"
							:label="`${parameter.additional_parameter_key} *`"
							doctype="YRP Additional Parameter Value"
							:filters="{ key: parameter.additional_parameter_key }"
							:show-open-button="false"
							:search-handler="(query) => searchAdditionalParameterValues(schema, parameter, query)"
							required
							:disabled="busy"
							@update:model-value="parameter.additional_parameter_value = $event"
						/>
						<span v-if="schema?.additional_parameters?.length" class="purchase-order-editor__item-hint">Item-specific procurement details</span>
					</div>
				</template>
				<template #row-warning="{ row }">
					<span v-if="row.price_warning" class="purchase-order-editor__price-warning" role="status">
						<i class="pi pi-exclamation-triangle" aria-hidden="true" />
						<span>{{ row.price_warning }}</span>
						<RouterLink v-if="row.price_create_url" :to="row.price_create_url">Create price</RouterLink>
					</span>
				</template>
			</StockItemComposer>
		</div>

		<Dialog v-model:visible="discardVisible" class="erp-dialog--sm" header="Discard unsaved changes?" modal :closable="false">
			<p class="purchase-order-editor__discard-copy">Your unsaved Purchase Order changes will be lost.</p>
			<template #footer><Button label="Keep Editing" severity="secondary" text @click="keepEditing" /><Button label="Discard Changes" severity="danger" @click="discardChanges" /></template>
		</Dialog>
		<DocumentConfirmationDialog v-model:visible="supplierConfirmVisible" :title="supplierConfirmationTitle" :message="supplierConfirmationMessage" cancel-label="Keep Current Supplier" :confirm-label="supplierConfirmationLabel" :busy="saving === 'source'" return-focus-selector="#field-supplier-value" @update:visible="supplierConfirmationVisibilityChanged" @confirm="confirmSupplierChange" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import { useToast } from "primevue/usetoast"
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave, RouterLink } from "vue-router"

import { getPurchaseOrderEditor, getPurchaseOrderItemSchema, previewPurchaseOrderPrices, savePurchaseOrder, searchPurchaseOrderAdditionalParameterValues } from "../../api/fabricStore.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import StockItemComposer from "../../components/stock/StockItemComposer.vue"
import { withNewDocumentDefaults } from "../../utils/newDocumentDefaults.js"
import { changePurchaseOrderDeliveryLocation } from "./purchaseOrderDelivery.js"
import { applyPurchaseOrderPricePreview, applyPurchaseOrderPriceSchedule, createPurchaseOrderDraftRevision, createPurchaseOrderPreviewController, currentPurchaseOrderPreview, loadPurchaseOrderGroups, validatePurchaseOrderItems } from "../../utils/purchaseOrder.js"

const props = defineProps({ name: { type: String, default: "" }, source: { type: Object, default: () => ({}) }, newDefaults: { type: Object, default: () => ({}) } })
const emit = defineEmits(["saved", "cancel"])
const toast = useToast()
const loading = ref(true)
const saving = ref("")
const composerPreparing = ref(false)
const previewPending = ref(false)
const error = ref("")
const loadFailed = ref(false)
const editor = ref({})
const form = reactive({ naming_series: "", supplier: "", transaction_date: "", schedule_date: "", company: "", set_warehouse: "", default_delivery_location: "", deliver_to_supplier: 0, currency: "", terms_and_condition: "", comments: "" })
const itemGroups = ref([])
const dirty = ref(false)
const sourceRevision = ref(0)
const discardVisible = ref(false)
const pendingCancel = ref(false)
const supplierConfirmVisible = ref(false)
const pendingSupplierValue = ref(null)
let allowNavigation = false
let pendingNavigation = null
const previewController = createPurchaseOrderPreviewController((pending) => { previewPending.value = pending })
const draftRevision = createPurchaseOrderDraftRevision()

const busy = computed(() => loading.value || Boolean(saving.value) || composerPreparing.value || previewPending.value)
const duplicateFrom = computed(() => String(props.source?.duplicate_from || ""))
const deliverToSupplier = computed({ get: () => Boolean(Number(form.deliver_to_supplier)), set: (value) => { form.deliver_to_supplier = value ? 1 : 0 } })
const deliveryLocationFilters = computed(() => ({ is_company_location: deliverToSupplier.value ? 0 : 1 }))
const deliveryWarehouseFilters = computed(() => ({ disabled: 0, supplier: form.default_delivery_location || "__unselected__" }))
const composerEditor = computed(() => ({
	dimensions: editor.value.dimensions || [],
	locked_dimensions: editor.value.locked_dimensions || [],
	default_dimensions: editor.value.default_dimensions || {},
	item_filters: editor.value.item_filters || {
		disabled: 0,
		variant_of: ["is", "not set"],
		is_purchase_item: 1,
		is_stock_item: 1,
	},
}))
const composerEntryDefaults = computed(() => ({
	delivery_location: form.default_delivery_location || "",
	schedule_date: form.schedule_date || "",
	expected_delivery_date: form.schedule_date || "",
	fetch_delivery_date: 0,
	discount_percentage: 0,
	comments: "",
	additional_parameters: [],
}))
const logicalItemCount = computed(() => itemGroups.value.reduce((total, group) => total + (group.items?.length || 0), 0))
const canDraft = computed(() => props.name ? Boolean(editor.value.permissions?.can_write) : Boolean(editor.value.permissions?.can_create))
const fieldMetadata = computed(() => new Map((editor.value.fields || []).map((field) => [field.fieldname, field])))
const canSave = computed(() => Boolean(form.naming_series && form.supplier && form.transaction_date && form.schedule_date && form.set_warehouse && logicalItemCount.value))
const itemValidationError = computed(() => validatePurchaseOrderItems(form, itemGroups.value))
const supplierChangeIsClear = computed(() => pendingSupplierValue.value === "")
const supplierConfirmationTitle = computed(() => supplierChangeIsClear.value ? "Clear Supplier?" : "Change Supplier?")
const supplierConfirmationMessage = computed(() => supplierChangeIsClear.value
	? "Clearing Supplier will keep the entered quantities and reset their rates, discounts, taxes and totals. Select a Supplier again before saving."
	: "Changing Supplier will reprice every entered item when an approved price is available. Unresolved items keep their commercial values and show a warning.")
const supplierConfirmationLabel = computed(() => supplierChangeIsClear.value ? "Clear Supplier" : "Change & Reprice")

function isRequired(fieldname, fallback = false) { return Boolean(fieldMetadata.value.get(fieldname)?.reqd) || fallback }
function isReadOnly(fieldname) { return Boolean(fieldMetadata.value.get(fieldname)?.read_only) }
function fieldLabel(fieldname, fallback, showRequired = true, requiredFallback = false) {
	const label = fieldMetadata.value.get(fieldname)?.label || fallback
	return `${label}${showRequired && isRequired(fieldname, requiredFallback) ? " *" : ""}`
}
function fieldOptions(fieldname) {
	const options = fieldMetadata.value.get(fieldname)?.options
	const values = Array.isArray(options) ? options : String(options || "").split("\n").map((value) => value.trim()).filter(Boolean)
	return values.length ? values : [form[fieldname]].filter(Boolean)
}

async function load() {
	const loadRevision = draftRevision.revise()
	previewController.revise()
	saving.value = ""
	loading.value = true
	loadFailed.value = false
	error.value = ""
	try {
		const loadedEditor = await getPurchaseOrderEditor(props.name, props.source) || {}
		if (!draftRevision.isCurrent(loadRevision)) return
		editor.value = loadedEditor
		Object.assign(form, editor.value.values || {})
		if (!props.name && !props.source?.duplicate_from) {
			Object.assign(form, withNewDocumentDefaults(form, Object.fromEntries(Object.entries(props.newDefaults || {}).filter(([fieldname]) => fieldname in form))))
		}
		itemGroups.value = loadPurchaseOrderGroups(editor.value.item_groups)
		dirty.value = false
	} catch (reason) {
		if (!draftRevision.isCurrent(loadRevision)) return
		loadFailed.value = true
		error.value = reason?.message || "Unable to load the Purchase Order editor."
	} finally {
		if (draftRevision.isCurrent(loadRevision)) loading.value = false
	}
}

function loadItemSchema(_operation, item) { return getPurchaseOrderItemSchema(item, props.name) }
function searchAdditionalParameterValues(schema, parameter, query) {
	return searchPurchaseOrderAdditionalParameterValues(
		schema?.item || "",
		parameter.additional_parameter_key,
		query,
		props.name,
	)
}
async function prepareItemPrice(row) {
	if (!form.supplier) throw new Error("Select Supplier before adding Purchase Order items.")
	if (!row.delivery_location) throw new Error("Select Delivery Location for this item.")
	row.schedule_date ||= form.schedule_date
	row.expected_delivery_date = row.schedule_date
	const discount = Number(row.discount_percentage || 0)
	if (!Number.isFinite(discount) || discount < 0 || discount > 100) throw new Error("Discount % must be between 0 and 100.")
	for (const parameter of row.additional_parameters || []) {
		if (!parameter.additional_parameter_value) throw new Error(`Select ${parameter.additional_parameter_key} for ${row.name}.`)
	}
	return row
}
async function previewItemPrices(groups, supplier = form.supplier, requireCurrent = false) {
	if (!supplier) return clone(groups)
	const request = await previewController.run(
		() => previewPurchaseOrderPrices(groups, supplier, props.name),
	)
	const preview = currentPurchaseOrderPreview(request, { required: requireCurrent })
	if (!preview) return null
	const repriced = applyPurchaseOrderPricePreview(groups, preview, {
		supplier,
		canCreateItemPrice: Boolean(editor.value.permissions?.can_create_item_price),
	})
	return applyPurchaseOrderPriceSchedule(repriced, {
		transactionDate: form.transaction_date,
		defaultRequiredBy: form.schedule_date,
	})
}
function setItemRequiredBy(values, value) {
	values.schedule_date = value || ""
	values.expected_delivery_date = value || ""
}
function markDirty() { if (!loading.value) dirty.value = true }
async function changeSupplier(value) {
	if (previewPending.value || composerPreparing.value) return
	if ((value || "") === (form.supplier || "")) return
	if (hasEnteredQuantities()) {
		pendingSupplierValue.value = value || ""
		supplierConfirmVisible.value = true
		return
	}
	form.supplier = value
	markDirty()
}
async function applySupplierChange(value) {
	const operationRevision = draftRevision.current()
	const previousSupplier = form.supplier

	const previousGroups = clone(itemGroups.value)
	let repricedGroups = clone(itemGroups.value)
	form.supplier = value
	saving.value = "source"
	error.value = ""
	try {
		if (value) repricedGroups = await previewItemPrices(repricedGroups, value, true)
		else {
			previewController.revise()
			for (const group of repricedGroups) for (const row of group.items || []) resetItemPrice(row)
		}
		if (!draftRevision.isCurrent(operationRevision)) return
		itemGroups.value = repricedGroups
		markDirty()
		sourceRevision.value += 1
	} catch (reason) {
		if (!draftRevision.isCurrent(operationRevision)) return
		form.supplier = previousSupplier
		itemGroups.value = previousGroups
		sourceRevision.value += 1
		error.value = reason?.message || "Unable to refresh Purchase Order prices for this Supplier."
	} finally {
		if (draftRevision.isCurrent(operationRevision)) saving.value = ""
	}
}
function resetItemPrice(row) {
	row.tax = ""
	row.price_status = ""
	row.price_warning = ""
	row.price_create_url = ""
	row.price_lead_time_days = null
	row.discount_percentage = 0
	for (const value of Object.values(row.values || {})) {
		value.price_status = ""
		value.price_tier = null
		value.tax = ""
		value.rate = 0
		value.amount = 0
		value.discount_amount = 0
		value.tax_amount = 0
		value.total_amount = 0
	}
}
async function confirmSupplierChange() {
	const value = pendingSupplierValue.value
	pendingSupplierValue.value = null
	supplierConfirmVisible.value = false
	await applySupplierChange(value)
	await nextTick()
	window.requestAnimationFrame(() => window.requestAnimationFrame(() => document.querySelector("#field-supplier-value")?.focus?.()))
}
function supplierConfirmationVisibilityChanged(visible) {
	supplierConfirmVisible.value = visible
	if (visible || pendingSupplierValue.value === null) return
	pendingSupplierValue.value = null
	sourceRevision.value += 1
}
function hasEnteredQuantities() {
	return itemGroups.value.some((group) => (group.items || []).some((item) =>
		Object.values(item.values || {}).some((value) => Number(value?.qty || 0) !== 0),
	))
}
function deliveryModeChanged() { form.default_delivery_location = ""; form.set_warehouse = ""; markDirty() }
function changeDeliveryLocation(value) {
	if ((value || "") === form.default_delivery_location) return
	markDirty()
	changePurchaseOrderDeliveryLocation(form, value).catch((reason) => { error.value = reason?.message || "Unable to load the delivery location's warehouse." })
}

async function save(submit) {
	if (previewPending.value || composerPreparing.value) return
	error.value = ""
	const itemError = validatePurchaseOrderItems(form, itemGroups.value)
	if (itemError) { error.value = itemError; return }
	saving.value = submit ? "submit" : "draft"
	try {
		const payload = await savePurchaseOrder({ ...form, item_details: clone(itemGroups.value) }, { name: props.name, submit, expectedModified: editor.value.modified })
		const record = payload?.record || {}
		dirty.value = false
		allowNavigation = true
		toast.add({ severity: "success", summary: submit ? "Purchase Order submitted" : "Purchase Order saved", detail: record.name || "Your changes are saved.", life: 3500 })
		emit("saved", record)
	} catch (reason) { error.value = reason?.message || "Unable to save this Purchase Order." }
	finally { saving.value = "" }
}

function requestCancel() {
	if (!dirty.value) return emit("cancel")
	pendingCancel.value = true
	discardVisible.value = true
}
function keepEditing() {
	discardVisible.value = false
	pendingCancel.value = false
	if (pendingNavigation) {
		pendingNavigation(false)
		pendingNavigation = null
	}
}
function discardChanges() {
	discardVisible.value = false
	allowNavigation = true
	if (pendingCancel.value) { pendingCancel.value = false; emit("cancel"); return }
	const next = pendingNavigation
	pendingNavigation = null
	next?.()
}
function beforeUnload(event) { if (!dirty.value) return; event.preventDefault(); event.returnValue = "" }
function clone(value) { return JSON.parse(JSON.stringify(value ?? [])) }

onBeforeRouteLeave((_to, _from, next) => {
	if (allowNavigation || !dirty.value) return next()
	pendingNavigation = next
	discardVisible.value = true
})
onMounted(() => { window.addEventListener("beforeunload", beforeUnload); load() })
onBeforeUnmount(() => { draftRevision.revise(); previewController.revise(); window.removeEventListener("beforeunload", beforeUnload) })
watch(() => props.name, load)
</script>

<style scoped>
.purchase-order-editor {
	display: flex;
	width: 100%;
	min-height: calc(100dvh - var(--erp-shell-header-height) - 78px);
	flex-direction: column;
	gap: var(--erp-space-3);
	padding: 0 0 var(--erp-space-4);
	border-color: color-mix(in srgb, var(--erp-border) 84%, var(--erp-surface));
	background: var(--erp-bg);
}
.purchase-order-editor__section > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.purchase-order-editor__loading, .purchase-order-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.purchase-order-editor__recovery { display: grid; min-height: 220px; place-content: center; justify-items: center; gap: 10px; padding: var(--erp-space-6); color: var(--erp-text-muted); text-align: center; border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.purchase-order-editor__recovery > i { color: var(--erp-danger); font-size: var(--erp-font-size-title); }.purchase-order-editor__recovery > div { display: grid; gap: 4px; }.purchase-order-editor__recovery strong { color: var(--erp-text); }.purchase-order-editor__recovery span { max-width: 520px; font-size: var(--erp-font-size-caption); }
.purchase-order-editor__section { display: grid; gap: var(--erp-space-3); padding: clamp(14px, 1.4vw, 22px); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-card); }
.purchase-order-editor__section > header { display: flex; align-items: end; justify-content: space-between; gap: 12px; }
.purchase-order-editor__section h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.purchase-order-editor__section small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.purchase-order-editor__document-fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: end; gap: 12px 16px; }
.purchase-order-editor__card-grid { display: grid; min-width: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); }
.purchase-order-editor__entry-card { min-width: 0; align-content: start; box-shadow: var(--erp-shadow-card); }
.purchase-order-editor__notes-card { grid-column: 1 / -1; }
.purchase-order-editor__fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: end; gap: 11px 14px; }
.purchase-order-editor__delivery-fields { grid-template-columns: minmax(150px, .8fr) minmax(200px, 1fr) minmax(200px, 1fr); }
.purchase-order-editor__control {
	display: grid;
	min-width: 0;
	gap: 6px;
}

.purchase-order-editor__check {
	display: flex;
	min-height: var(--erp-control-height);
	align-items: center;
	gap: 8px;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-medium);
}
.purchase-order-editor__comments { display: grid; grid-column: span 2; gap: 6px; }

.purchase-order-editor__item-details { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: end; gap: 10px; padding: 11px 0; background: transparent; }
.purchase-order-editor__item-check {
	display: flex;
	min-height: var(--erp-control-height);
	align-items: center;
	gap: 8px;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-medium);
}
.purchase-order-editor__item-control {
	display: grid;
	gap: 6px;
}
.purchase-order-editor__item-comments { grid-column: span 2; }
.purchase-order-editor__item-hint { align-self: center; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.purchase-order-editor__price-warning { display: flex; max-width: 260px; align-items: center; gap: 5px; margin-top: 4px; color: var(--erp-warning); font-size: var(--erp-font-size-min); font-weight: 600; white-space: normal; }
.purchase-order-editor__price-warning a { color: var(--erp-accent-dark); font-weight: 600; white-space: nowrap; }
.purchase-order-editor__discard-copy { margin: 0; color: var(--erp-text-muted); line-height: 1.5; }
@media (max-width: 1100px) { .purchase-order-editor__document-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } .purchase-order-editor__card-grid { grid-template-columns: 1fr; } .purchase-order-editor__notes-card { grid-column: auto; } }
@media (max-width: 900px) { .purchase-order-editor__delivery-fields, .purchase-order-editor__item-details { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) {
	.purchase-order-editor__section {
		padding: var(--erp-space-3);
	}
	.purchase-order-editor__section > header small {
		display: none;
	}
	.purchase-order-editor__document-fields, .purchase-order-editor__fields, .purchase-order-editor__delivery-fields {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
	.purchase-order-editor__document-fields > *, .purchase-order-editor__fields > * {
		grid-column: 1 / -1;
	}
	.purchase-order-editor__date :deep(.p-datepicker-input) {
		padding-inline: 8px;
	}
	.purchase-order-editor__date :deep(.p-datepicker-dropdown) {
		width: 44px;
		min-width: 44px;
	}
	.purchase-order-editor__comments {
		grid-column: auto;
	}
}
@media (max-width: 340px) { .purchase-order-editor__document-fields, .purchase-order-editor__fields, .purchase-order-editor__delivery-fields { grid-template-columns: 1fr; } .purchase-order-editor__date { grid-column: 1 / -1; } }
</style>
