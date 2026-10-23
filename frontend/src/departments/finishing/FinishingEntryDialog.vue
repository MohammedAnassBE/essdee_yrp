<template>
	<Dialog :visible="visible" modal maximizable :closable="!busy" :header="definition?.title || ''" class="finishing-entry-dialog erp-dialog--xl" @update:visible="(value) => !value && close()">
		<div v-if="loading" class="finishing-stack" aria-label="Loading entry"><Skeleton height="44px" /><Skeleton height="220px" /></div>
		<WorkspaceLoadError v-else-if="loadError" title="Entry unavailable" :message="loadError" @retry="load" />
		<form v-else-if="source" class="finishing-stack" @submit.prevent="submit">
			<div v-if="definition.fields.length" class="finishing-entry-dialog__fields">
				<template v-for="field in visibleFields" :key="field">
					<LinkField v-if="field === 'from_location'" v-model="form.from_location" doctype="Supplier" label="From Location" required :show-open-button="false" :disabled="busy" />
					<LinkField v-else-if="field === 'from_supplier'" :model-value="form.from_supplier" doctype="Supplier" label="From Supplier" required :show-open-button="false" :disabled="busy" @update:model-value="(value) => setSupplier('from', value)" />
					<LinkField v-else-if="field === 'from_warehouse'" v-model="form.from_warehouse" doctype="Warehouse" label="From Warehouse" required :filters="warehouseFilters(form.from_supplier)" :show-open-button="false" :disabled="busy" />
					<LinkField v-else-if="field === 'to_supplier'" :model-value="form.to_supplier" doctype="Supplier" label="To Supplier" required :show-open-button="false" :disabled="busy" @update:model-value="(value) => setSupplier('to', value)" />
					<LinkField v-else-if="field === 'to_warehouse'" v-model="form.to_warehouse" doctype="Warehouse" label="To Warehouse" required :filters="warehouseFilters(form.to_supplier)" :show-open-button="false" :disabled="busy" />
					<LinkField v-else-if="field === 'delivery_location'" v-model="form.delivery_location" doctype="Supplier" label="Delivery Location" required :show-open-button="false" :disabled="busy" />
					<DateField v-else-if="field === 'actual_date'" v-model="form.actual_date" label="Actual Date" required :disabled="busy" />
					<LinkField v-else-if="field === 'received_type'" v-model="form.received_type" doctype="YRP Received Type" label="Received Type" required :show-open-button="false" :disabled="busy" />
					<label v-else-if="field === 'goods_value'" class="common-field"><span class="finishing-entry-dialog__label">Goods Value</span><InputNumber v-model="form.goods_value" :min-fraction-digits="0" :max-fraction-digits="2" input-id="finishing-goods-value" aria-label="Goods Value" fluid :disabled="busy" /></label>
					<label v-else-if="field === 'vehicle_no'" class="common-field"><span class="finishing-entry-dialog__label">Vehicle No</span><InputText id="finishing-vehicle-no" aria-label="Vehicle No" v-model="form.vehicle_no" fluid :disabled="busy" /></label>
					<label v-else-if="field === 'lot_source'" class="common-field"><span class="finishing-entry-dialog__label">Lot Source</span><Select v-model="form.lot_source" :options="['New Lot', 'Existing Lot']" fluid :disabled="busy" /></label>
					<label v-else-if="field === 'lot_name'" class="common-field"><span class="finishing-entry-dialog__label">Lot Name</span><InputText v-model="form.lot_name" fluid :disabled="busy" /></label>
					<LinkField v-else-if="field === 'existing_lot'" v-model="form.existing_lot" doctype="SD YRP Lot" label="Existing Lot" required :search-handler="searchUnconfiguredLots" :show-open-button="false" :disabled="busy" />
					<LinkField v-else-if="field === 'alternative_item'" :model-value="form.alternative_item" doctype="Item" label="Alternative Item" placeholder="Select item" required :filters="{ name: ['in', options.alternative_items || []] }" :allow-create="false" :show-open-button="false" :disabled="busy" @update:model-value="setAlternativeItem" />
					<LinkField v-else-if="field === 'production_detail'" :key="form.alternative_item" v-model="form.production_detail" doctype="YRP Item Production Detail" label="Item Production Detail" required :filters="{ item: form.alternative_item }" :show-open-button="false" :disabled="busy || !form.alternative_item" />
					<LinkField v-else-if="field === 'target_lot'" v-model="form.target_lot" doctype="SD YRP Lot" label="Target Lot" placeholder="Select lot" required :filters="{ name: ['in', options.alternate_lots || []] }" :allow-create="false" :show-open-button="false" :disabled="busy" />
				</template>
			</div>
			<div v-if="definition.typeSelect" class="finishing-entry-dialog__type">
				<label class="common-field"><span class="finishing-entry-dialog__label">Choose Type</span><Select v-model="form.selected_type" :options="deliveryTypes" option-label="label" option-value="value" :disabled="busy" @change="resetQuantities" /></label>
				<Button label="Fill" icon="pi pi-download" severity="secondary" outlined :disabled="busy" @click="fill" />
			</div>
			<p v-if="sourceEntry" class="finishing-entry-dialog__source">Quantities from <strong>{{ sourceEntry }}</strong></p>
			<FinishingPackingEntry v-if="definition.component === 'packing'" ref="custom" :sizes="source.primary_values || []" :config="source.packing_config || {}" :disabled="busy" />
			<FinishingDispatchEntry v-else-if="definition.component === 'dispatch'" ref="custom" :label="name" :sizes="source.primary_values || []" :packed="source.packed || {}" :config="source.packing_config || {}" :disabled="busy" />
			<FinishingEntryMatrix v-else :payload="matrixPayload" :model-value="entry" :references="references" :input-label="definition.inputLabel" :checkable="Boolean(definition.checkable)" :disabled="busy" />
		</form>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="busy" @click="close" />
			<Button :label="definition?.submit || 'Create'" icon="pi pi-check" :loading="busy" :disabled="loading || Boolean(loadError)" @click="submit" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="validationError" title="Check the entry" @dismiss="validationError = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { getFinishingPlanTab, searchUnconfiguredLots } from "../../api/finishing.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { todayIso } from "../../components/reports/reportUtils.js"
import FinishingDispatchEntry from "./components/FinishingDispatchEntry.vue"
import FinishingEntryMatrix from "./components/FinishingEntryMatrix.vue"
import FinishingPackingEntry from "./components/FinishingPackingEntry.vue"
import { ENTRY_DEFINITIONS, entryPayload, missingFields } from "./finishingEntryDefinitions.js"
import { fillEntry, initialEntry } from "./finishingEntries.js"
import { prefilledEntry } from "./plan/finishingSourceEntries.js"
import { setDispatchSupplier, warehouseFilters } from "./supplierWarehouse.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	action: { type: String, default: "" },
	name: { type: String, required: true },
	workspace: { type: Object, required: true },
	busy: { type: Boolean, default: false },
	prefill: { type: Object, default: null },
	sourceEntry: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "submit"])
const deliveryTypes = [
	{ value: "balance", label: "Balance" },
	{ value: "return_qty", label: "Loose Piece" },
	{ value: "pack_return", label: "Loose Piece Packed" },
]
const typeLabels = { balance: "Balance Qty", return_qty: "Loose Piece Qty", pack_return: "Packed Piece Qty" }
const definition = computed(() => ENTRY_DEFINITIONS[props.action])
const options = computed(() => props.workspace.entry_options || {})
const loading = ref(false)
const loadError = ref("")
const validationError = ref("")
const source = ref(null)
const custom = ref(null)
const entry = ref({})
const form = reactive({})
let requestId = ""
let loadToken = 0
const matrixPayload = computed(() => ({ ...source.value, data: source.value?.data || {} }))
const references = computed(() => (definition.value?.typeSelect ? [{ key: form.selected_type, label: typeLabels[form.selected_type] }] : definition.value?.references || []))
const visibleFields = computed(() => (definition.value?.fields || []).filter((field) => {
	if (field === "lot_name") return form.lot_source === "New Lot"
	if (field === "existing_lot") return form.lot_source === "Existing Lot"
	return true
}))

function resetForm() {
	const record = props.workspace.record || {}
	Object.keys(form).forEach((key) => delete form[key])
	Object.assign(form, {
		from_location: options.value.delivery_location || "",
		delivery_location: options.value.delivery_location || "",
		actual_date: todayIso(),
		selected_type: "balance",
		lot_source: "New Lot",
		lot_name: record.lot || "",
		received_type: "",
		from_supplier: "",
		from_warehouse: "",
		to_supplier: "",
		to_warehouse: "",
		goods_value: null,
		vehicle_no: "",
	})
	requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

async function load() {
	const token = ++loadToken
	loading.value = true
	loadError.value = ""
	source.value = null
	try {
		const data = await getFinishingPlanTab(props.name, definition.value.source)
		if (token !== loadToken) return
		source.value = data || {}
		resetQuantities()
	} catch (reason) {
		if (token === loadToken) loadError.value = reason?.message || "Unable to load this entry."
	} finally {
		if (token === loadToken) loading.value = false
	}
}

async function setSupplier(side, supplier) {
	const message = await setDispatchSupplier(form, side, supplier)
	if (message) validationError.value = message
}

function setAlternativeItem(item) {
	if ((item || "") === form.alternative_item) return
	form.alternative_item = item || ""
	form.production_detail = ""
}

function resetQuantities() {
	entry.value = props.prefill ? prefilledEntry(source.value, props.prefill) : initialEntry(source.value)
}

function fill() {
	fillEntry(source.value, entry.value, form.selected_type)
}

function close() {
	if (!props.busy) emit("update:visible", false)
}

function submit() {
	if (props.busy || loading.value || !source.value) return
	const missing = missingFields(visibleFields.value, form)
	const message = missing.length ? `Enter ${missing.join(", ")}.` : custom.value?.validationError?.() || ""
	if (message) {
		validationError.value = message
		return
	}
	const payload = entryPayload(props.action, form, entry.value, custom.value?.values?.(), requestId)
	emit("submit", props.action, props.sourceEntry ? { ...payload, source_entry: props.sourceEntry } : payload)
}

watch(() => [props.visible, props.action, props.sourceEntry], ([visible]) => {
	if (!visible || !definition.value) return
	resetForm()
	if (definition.value.fields.includes("from_supplier")) setSupplier("from", options.value.delivery_location)
	load()
}, { immediate: true })
</script>

<style scoped>
.finishing-entry-dialog__fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: var(--erp-space-3); }
.finishing-entry-dialog__type { display: flex; align-items: flex-end; flex-wrap: wrap; gap: var(--erp-space-3); }
.finishing-entry-dialog__type .common-field { min-width: 220px; }
.finishing-entry-dialog__label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.finishing-entry-dialog .common-field { display: grid; gap: 6px; }
.finishing-entry-dialog__source { margin: 0; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
</style>
