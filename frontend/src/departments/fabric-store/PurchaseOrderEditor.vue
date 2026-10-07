<template>
	<section class="purchase-order-editor erp-card erp-editor-shell" aria-label="Purchase Order editor" :aria-busy="loading">
		<header class="purchase-order-editor__header erp-editor-header">
			<div><span>{{ name || (duplicateFrom ? `Duplicate of ${duplicateFrom}` : "New document") }}</span><h1>{{ name ? "Edit Purchase Order" : "New Purchase Order" }}</h1></div>
			<div class="purchase-order-editor__actions erp-editor-actions">
				<Button label="Cancel" severity="secondary" text :disabled="busy" @click="requestCancel" />
				<Button v-if="canDraft" label="Save" icon="pi pi-save" :loading="saving === 'draft'" :disabled="busy || !canSave" @click="save(false)" />
			</div>
		</header>

		<DocumentErrorDialog :message="error" :title="`Purchase Order could not be ${loadFailed ? 'loaded' : 'saved'}`" />
		<div v-if="loading" class="purchase-order-editor__loading" role="status" aria-live="polite" aria-label="Loading Purchase Order editor"><Skeleton height="160px" /><Skeleton height="420px" /></div>
		<section v-else-if="loadFailed" class="purchase-order-editor__recovery" role="alert"><i class="pi pi-cloud-times" aria-hidden="true" /><div><strong>Purchase Order could not be loaded</strong><span>Close the error message, then try loading the document again.</span></div><Button label="Retry" icon="pi pi-refresh" severity="secondary" outlined @click="load" /></section>
		<div v-else class="purchase-order-editor__body">
			<section class="purchase-order-editor__section">
				<header><h2>Order details</h2></header>
				<div class="purchase-order-editor__fields">
					<LinkField input-id="field-supplier-value" :key="`supplier-${sourceRevision}`" :model-value="form.supplier" label="Supplier *" doctype="Supplier" required :filters="{ disabled: 0 }" :show-open-button="false" show-clear :disabled="busy" @update:model-value="changeSupplier" />
					<DateField v-model="form.transaction_date" class="purchase-order-editor__date" label="Order date" required :disabled="busy" @update:model-value="markDirty" />
					<DateField v-model="form.schedule_date" class="purchase-order-editor__date" label="Required by" required :disabled="busy" @update:model-value="markDirty" />
					<LinkField v-model="form.company" label="Company" doctype="Company" :show-open-button="false" show-clear :disabled="busy" @update:model-value="markDirty" />
					<label class="purchase-order-editor__check"><Checkbox v-model="deliverToSupplier" binary input-id="po-deliver-to-supplier" :disabled="busy" @change="deliveryModeChanged" /><span>Deliver to supplier</span></label>
					<LinkField :model-value="form.default_delivery_location" label="Delivery location" doctype="Supplier" :filters="deliveryLocationFilters" :show-open-button="false" show-clear :disabled="busy" @update:model-value="changeDeliveryLocation" />
					<LinkField v-model="form.set_warehouse" label="Delivery warehouse *" doctype="Warehouse" required :filters="deliveryWarehouseFilters" :show-open-button="false" show-clear :disabled="busy || !form.default_delivery_location" @update:model-value="markDirty" />
					<LinkField v-model="form.currency" label="Currency" doctype="Currency" :show-open-button="false" show-clear :disabled="busy" @update:model-value="markDirty" />
					<LinkField v-model="form.terms_and_condition" label="Terms and condition" doctype="YRP Terms and Condition" :show-open-button="false" show-clear :disabled="busy" @update:model-value="markDirty" />
					<label class="purchase-order-editor__comments"><span>Comments</span><Textarea v-model="form.comments" rows="2" auto-resize fluid :disabled="busy" @input="markDirty" /></label>
				</div>
			</section>

			<StockItemComposer
				v-model="itemGroups"
				operation="purchase_order"
				:editor="composerEditor"
				:schema-loader="loadItemSchema"
				:row-preparer="prepareItemPrice"
				:currency="form.currency"
				natural-table-flow
				@dirty="markDirty"
			/>
		</div>

		<Dialog v-model:visible="discardVisible" header="Discard unsaved changes?" modal :closable="false" :style="{ width: 'min(440px, calc(100vw - 32px))' }">
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
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import { useToast } from "primevue/usetoast"
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave } from "vue-router"

import { getPurchaseOrderEditor, getPurchaseOrderItemPrice, getPurchaseOrderItemSchema, savePurchaseOrder } from "../../api/fabricStore.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import StockItemComposer from "../../components/stock/StockItemComposer.vue"

const props = defineProps({ name: { type: String, default: "" }, source: { type: Object, default: () => ({}) } })
const emit = defineEmits(["saved", "cancel"])
const toast = useToast()
const loading = ref(true)
const saving = ref("")
const error = ref("")
const loadFailed = ref(false)
const editor = ref({})
const form = reactive({ supplier: "", transaction_date: "", schedule_date: "", company: "", set_warehouse: "", default_delivery_location: "", deliver_to_supplier: 0, currency: "", terms_and_condition: "", comments: "" })
const itemGroups = ref([])
const dirty = ref(false)
const sourceRevision = ref(0)
const discardVisible = ref(false)
const pendingCancel = ref(false)
const supplierConfirmVisible = ref(false)
const pendingSupplierValue = ref(null)
let allowNavigation = false
let pendingNavigation = null

const busy = computed(() => loading.value || Boolean(saving.value))
const duplicateFrom = computed(() => String(props.source?.duplicate_from || ""))
const deliverToSupplier = computed({ get: () => Boolean(Number(form.deliver_to_supplier)), set: (value) => { form.deliver_to_supplier = value ? 1 : 0 } })
const deliveryLocationFilters = computed(() => ({ is_company_location: deliverToSupplier.value ? 0 : 1 }))
const deliveryWarehouseFilters = computed(() => ({ disabled: 0, supplier: form.default_delivery_location || "__unselected__" }))
const composerEditor = computed(() => ({
	dimensions: editor.value.dimensions || [],
	locked_dimensions: editor.value.locked_dimensions || [],
	default_dimensions: editor.value.default_dimensions || {},
	item_filters: editor.value.item_filters || { has_variants: 1, disabled: 0 },
}))
const logicalItemCount = computed(() => itemGroups.value.reduce((total, group) => total + (group.items?.length || 0), 0))
const canDraft = computed(() => props.name ? Boolean(editor.value.permissions?.can_write) : Boolean(editor.value.permissions?.can_create))
const canSave = computed(() => Boolean(form.supplier && form.transaction_date && form.schedule_date && form.set_warehouse && logicalItemCount.value))
const supplierChangeIsClear = computed(() => pendingSupplierValue.value === "")
const supplierConfirmationTitle = computed(() => supplierChangeIsClear.value ? "Clear Supplier?" : "Change Supplier?")
const supplierConfirmationMessage = computed(() => supplierChangeIsClear.value
	? "Clearing Supplier will keep the entered quantities and reset their rates, discounts, taxes and totals. Select a Supplier again before saving."
	: "Changing Supplier will recalculate every entered item rate, discount, tax and total using the new Supplier. Entered quantities remain unchanged.")
const supplierConfirmationLabel = computed(() => supplierChangeIsClear.value ? "Clear Supplier" : "Change & Reprice")

async function load() {
	loading.value = true
	loadFailed.value = false
	error.value = ""
	try {
		editor.value = await getPurchaseOrderEditor(props.name, props.source) || {}
		Object.assign(form, editor.value.values || {})
		itemGroups.value = clone(editor.value.item_groups || [])
		dirty.value = false
	} catch (reason) { loadFailed.value = true; error.value = reason?.message || "Unable to load the Purchase Order editor." }
	finally { loading.value = false }
}

function loadItemSchema(_operation, item) { return getPurchaseOrderItemSchema(item, props.name) }
async function prepareItemPrice(row) {
	if (!form.supplier) throw new Error("Select Supplier before adding Purchase Order items.")
	const price = await getPurchaseOrderItemPrice(row, form.supplier, props.name)
	const taxRate = Number(price?.tax_rate || 0)
	row.tax = price?.tax || ""
	for (const [key, value] of Object.entries(row.values || {})) {
		const qty = Number(value?.qty || 0)
		const rate = price?.rates ? price.rates[key] : price?.rate
		value.rate = Number(rate || 0)
		value.amount = qty * value.rate
		value.discount_amount = value.amount * Number(row.discount_percentage || 0) / 100
		value.tax_amount = (value.amount - value.discount_amount) * taxRate / 100
		value.total_amount = value.amount - value.discount_amount + value.tax_amount
	}
	return row
}
function markDirty() { if (!loading.value) dirty.value = true }
async function changeSupplier(value) {
	if (value === form.supplier) return
	if (hasEnteredQuantities()) {
		pendingSupplierValue.value = value || ""
		supplierConfirmVisible.value = true
		return
	}
	form.supplier = value
	markDirty()
}
async function applySupplierChange(value) {
	const previousSupplier = form.supplier

	const previousGroups = clone(itemGroups.value)
	const repricedGroups = clone(itemGroups.value)
	form.supplier = value
	saving.value = "source"
	error.value = ""
	try {
		for (const group of repricedGroups) {
			for (const row of group.items || []) {
				if (value) await prepareItemPrice(row)
				else resetItemPrice(row)
			}
		}
		itemGroups.value = repricedGroups
		markDirty()
		sourceRevision.value += 1
	} catch (reason) {
		form.supplier = previousSupplier
		itemGroups.value = previousGroups
		sourceRevision.value += 1
		error.value = reason?.message || "Unable to refresh Purchase Order prices for this Supplier."
	} finally { saving.value = "" }
}
function resetItemPrice(row) {
	row.tax = ""
	row.discount_percentage = 0
	for (const value of Object.values(row.values || {})) {
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
	if (value === form.default_delivery_location) return
	form.default_delivery_location = value || ""
	form.set_warehouse = ""
	markDirty()
}

async function save(submit) {
	saving.value = submit ? "submit" : "draft"
	error.value = ""
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
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
watch(() => props.name, load)
</script>

<style scoped>
.purchase-order-editor { --purchase-order-editor-inline: clamp(14px, 1.5vw, 24px); display: flex; width: 100%; min-height: calc(100dvh - var(--erp-shell-header-height) - 78px); flex-direction: column; gap: var(--erp-space-3); padding: 0 var(--purchase-order-editor-inline) var(--erp-space-4); border-color: color-mix(in srgb, var(--erp-border) 84%, white); background: color-mix(in srgb, var(--erp-bg) 72%, white); }
.purchase-order-editor__header { position: sticky; z-index: var(--erp-layer-sticky); top: 0; display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-4); margin: 0 calc(0px - var(--purchase-order-editor-inline)); padding: 12px var(--purchase-order-editor-inline); border-top: 3px solid var(--erp-accent); border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface) 96%, var(--erp-accent-soft)); box-shadow: 0 5px 16px rgb(28 61 45 / 5%); }
.purchase-order-editor__header > div:first-child { display: grid; gap: 2px; }
.purchase-order-editor__header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }
.purchase-order-editor__header h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -.025em; }
.purchase-order-editor__actions { display: flex; justify-content: flex-end; gap: var(--erp-space-2); flex-wrap: wrap; }
.purchase-order-editor__loading, .purchase-order-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.purchase-order-editor__recovery { display: grid; min-height: 220px; place-content: center; justify-items: center; gap: 10px; padding: var(--erp-space-6); color: var(--erp-text-muted); text-align: center; border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.purchase-order-editor__recovery > i { color: var(--erp-danger); font-size: 24px; }.purchase-order-editor__recovery > div { display: grid; gap: 4px; }.purchase-order-editor__recovery strong { color: var(--erp-text); }.purchase-order-editor__recovery span { max-width: 520px; font-size: var(--erp-font-size-caption); }
.purchase-order-editor__section { padding: clamp(14px, 1.4vw, 22px); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 8px 24px rgb(28 61 45 / 4%); }
.purchase-order-editor__section h2 { margin: 0 0 var(--erp-space-3); color: var(--erp-text); font-size: var(--erp-font-size-section); }
.purchase-order-editor__fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: end; gap: 11px 14px; }
.purchase-order-editor__check { display: flex; min-height: var(--erp-control-height); align-items: center; gap: 8px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.purchase-order-editor__comments { display: grid; grid-column: span 2; gap: 6px; }
.purchase-order-editor__comments > span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; text-transform: none; letter-spacing: normal; }
.purchase-order-editor__discard-copy { margin: 0; color: var(--erp-text-muted); line-height: 1.5; }
@media (max-width: 1100px) { .purchase-order-editor__fields { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) { .purchase-order-editor__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .purchase-order-editor { padding: 0 var(--erp-space-3) var(--erp-space-3); } .purchase-order-editor__header { align-items: stretch; flex-direction: column; margin: 0 calc(var(--erp-space-3) * -1); padding: 10px var(--erp-space-3); } .purchase-order-editor__actions { justify-content: flex-start; } .purchase-order-editor__section { padding: var(--erp-space-3); } .purchase-order-editor__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } .purchase-order-editor__fields > :not(.purchase-order-editor__date) { grid-column: 1 / -1; } .purchase-order-editor__date :deep(.p-datepicker-input) { padding-inline: 8px; font-size: 13px; } .purchase-order-editor__date :deep(.p-datepicker-dropdown) { width: 32px; min-width: 32px; } .purchase-order-editor__comments { grid-column: auto; } .purchase-order-editor__actions { width: 100%; } .purchase-order-editor__actions :deep(.p-button) { flex: 1; } }
</style>
