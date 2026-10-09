<template>
	<Dialog :visible="visible" modal maximizable :closable="!busy" :header="definition?.title || ''" class="finishing-entry-dialog erp-dialog--xl" @update:visible="(value) => !value && close()">
		<div v-if="loading" class="finishing-stack" aria-label="Loading entry"><Skeleton height="44px" /><Skeleton height="220px" /></div>
		<WorkspaceLoadError v-else-if="loadError" title="Entry unavailable" :message="loadError" @retry="load" />
		<form v-else-if="source" class="finishing-stack" @submit.prevent="submit">
			<div v-if="definition.fields.length" class="finishing-entry-dialog__fields">
				<template v-for="field in visibleFields" :key="field">
					<LinkField v-if="field === 'from_location'" v-model="form.from_location" doctype="Supplier" label="From Location" required :show-open-button="false" :disabled="busy" />
					<LinkField v-else-if="field === 'to_location'" v-model="form.to_location" doctype="Supplier" label="To Location" required :show-open-button="false" :disabled="busy" />
					<LinkField v-else-if="field === 'delivery_location'" v-model="form.delivery_location" doctype="Supplier" label="Delivery Location" required :show-open-button="false" :disabled="busy" />
					<DateField v-else-if="field === 'actual_date'" v-model="form.actual_date" label="Actual Date" required :disabled="busy" />
					<LinkField v-else-if="field === 'received_type'" v-model="form.received_type" doctype="YRP Received Type" label="Received Type" required :show-open-button="false" :disabled="busy" />
					<label v-else-if="field === 'goods_value'" class="common-field"><span class="finishing-entry-dialog__label">Goods Value</span><InputNumber v-model="form.goods_value" :min-fraction-digits="0" :max-fraction-digits="2" input-id="finishing-goods-value" fluid :disabled="busy" /></label>
					<label v-else-if="field === 'vehicle_no'" class="common-field"><span class="finishing-entry-dialog__label">Vehicle No</span><InputText v-model="form.vehicle_no" fluid :disabled="busy" /></label>
					<label v-else-if="field === 'lot_source'" class="common-field"><span class="finishing-entry-dialog__label">Lot Source</span><Select v-model="form.lot_source" :options="['New Lot', 'Existing Lot']" fluid :disabled="busy" /></label>
					<label v-else-if="field === 'lot_name'" class="common-field"><span class="finishing-entry-dialog__label">Lot Name</span><InputText v-model="form.lot_name" fluid :disabled="busy" /></label>
					<LinkField v-else-if="field === 'existing_lot'" v-model="form.existing_lot" doctype="SD YRP Lot" label="Existing Lot" required :search-handler="searchUnconfiguredLots" :show-open-button="false" :disabled="busy" />
					<label v-else-if="field === 'alternative_item'" class="common-field"><span class="finishing-entry-dialog__label">Alternative Item</span><Select v-model="form.alternative_item" :options="options.alternative_items || []" placeholder="Select item" fluid :disabled="busy" @change="form.production_detail = ''" /></label>
					<LinkField v-else-if="field === 'production_detail'" :key="form.alternative_item" v-model="form.production_detail" doctype="YRP Item Production Detail" label="Item Production Detail" required :filters="{ item: form.alternative_item }" :show-open-button="false" :disabled="busy || !form.alternative_item" />
					<label v-else-if="field === 'target_lot'" class="common-field"><span class="finishing-entry-dialog__label">Target Lot</span><Select v-model="form.target_lot" :options="options.alternate_lots || []" placeholder="Select lot" fluid :disabled="busy" /></label>
				</template>
			</div>
			<div v-if="definition.typeSelect" class="finishing-entry-dialog__type">
				<label class="common-field"><span class="finishing-entry-dialog__label">Choose Type</span><Select v-model="form.selected_type" :options="deliveryTypes" option-label="label" option-value="value" :disabled="busy" @change="fill" /></label>
				<Button label="Fill" icon="pi pi-download" severity="secondary" outlined :disabled="busy" @click="fill" />
			</div>
			<FinishingPackingEntry v-if="definition.component === 'packing'" ref="custom" :sizes="source.primary_values || []" :config="source.packing_config || {}" :disabled="busy" />
			<FinishingDispatchEntry v-else-if="definition.component === 'dispatch'" ref="custom" :sizes="source.primary_values || []" :packed="source.packed || {}" :config="source.packing_config || {}" :disabled="busy" />
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

const props = defineProps({
	visible: { type: Boolean, default: false },
	action: { type: String, default: "" },
	name: { type: String, required: true },
	workspace: { type: Object, required: true },
	busy: { type: Boolean, default: false },
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
		to_location: "",
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
		entry.value = initialEntry(source.value)
	} catch (reason) {
		if (token === loadToken) loadError.value = reason?.message || "Unable to load this entry."
	} finally {
		if (token === loadToken) loading.value = false
	}
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
	emit("submit", props.action, entryPayload(props.action, form, entry.value, custom.value?.values?.(), requestId))
}

watch(() => [props.visible, props.action], ([visible]) => {
	if (!visible || !definition.value) return
	resetForm()
	load()
}, { immediate: true })
</script>

<style scoped>
.finishing-entry-dialog__fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: var(--erp-space-3); }
.finishing-entry-dialog__type { display: flex; align-items: flex-end; flex-wrap: wrap; gap: var(--erp-space-3); }
.finishing-entry-dialog__type .common-field { min-width: 220px; }
.finishing-entry-dialog__label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.finishing-entry-dialog .common-field { display: grid; gap: 6px; }
</style>
