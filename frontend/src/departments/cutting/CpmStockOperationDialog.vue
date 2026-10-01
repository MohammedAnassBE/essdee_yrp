<template>
	<Dialog :visible="visible" modal dismissable-mask maximizable :header="title" class="erp-stock-dialog erp-entity-dialog" :style="{ width: 'min(96vw, 1440px)' }" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="erp-stock-loading"><Skeleton v-for="index in 6" :key="index" height="3rem" /></div>
		<div v-else class="erp-stock-stack">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<div class="erp-stock-context">
				<div><span>Cutting Plan</span><strong>{{ stock.context?.cutting_plan || cuttingPlan }}</strong></div>
				<div><span>Lot</span><strong>{{ stock.context?.lot || "—" }}</strong></div>
				<div><span>Source Warehouse</span><strong>{{ stock.context?.source_warehouse || "—" }}</strong></div>
			</div>

			<div v-if="operation === 'stock_entry'" class="erp-operation-fields">
				<label class="erp-select-field"><span>Purpose *</span><Select v-model="form.purpose" :options="stockPurposes" placeholder="Select purpose" fluid /></label>
				<LinkField v-if="form.purpose === 'Send to Warehouse'" v-model="form.to_warehouse" label="To Warehouse *" doctype="Warehouse" :show-open-button="false" />
			</div>
			<div v-if="operation === 'stock_update'" class="erp-operation-fields">
				<label class="erp-select-field"><span>Update Type *</span><Select v-model="form.update_type" :options="stock.update_type_options || ['Add', 'Reduce']" placeholder="Select Add or Reduce" fluid /></label>
			</div>

			<StockItemComposer v-model="itemDetails" :cutting-plan="cuttingPlan" :operation="operation" :purpose="form.purpose" :update-type="form.update_type" :editor="stock" />
		</div>

		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
			<Button v-if="permissions.can_create" label="Save Draft" icon="pi pi-save" severity="secondary" outlined :disabled="!canSave" :loading="saving && saveMode === 'draft'" @click="save(false)" />
			<Button v-if="permissions.can_create && permissions.can_submit" label="Save & Submit" icon="pi pi-check" :disabled="!canSave" :loading="saving && saveMode === 'submit'" @click="save(true)" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import LinkField from "../../components/common/LinkField.vue"
import StockItemComposer from "./StockItemComposer.vue"
import { getStockOperationEditor, saveStockOperation } from "./cpmApi.js"

const props = defineProps({
	visible: Boolean,
	cuttingPlan: { type: String, required: true },
	operation: { type: String, required: true },
	permissions: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])

const stockPurposes = ["Material Issue", "Material Consumed", "Send to Warehouse"]
const operationMap = {
	stock_entry: { title: "Create Stock Entry" },
	stock_reconciliation: { title: "Create Stock Reconciliation" },
	stock_update: { title: "Create Stock Update" },
	lot_transfer: { title: "Create Lot Transfer" },
}

const loading = ref(false)
const saving = ref(false)
const saveMode = ref("")
const error = ref("")
const itemDetails = ref([])
const stock = reactive({ context: {}, dimensions: [], update_type_options: [] })
const form = reactive(emptyForm())

const operationMeta = computed(() => operationMap[props.operation] || operationMap.stock_entry)
const title = computed(() => operationMeta.value.title)
const canSave = computed(() => {
	if (!props.permissions.can_create) return false
	if (!itemDetails.value.some((group) => group.items?.length)) return false
	if (props.operation === "stock_entry" && !form.purpose) return false
	if (props.operation === "stock_entry" && form.purpose === "Send to Warehouse" && !form.to_warehouse) return false
	if (props.operation === "stock_update" && !form.update_type) return false
	return true
})

watch(() => [props.visible, props.operation, props.cuttingPlan], ([visible]) => { if (visible) load() })

async function load() {
	loading.value = true
	error.value = ""
	itemDetails.value = []
	Object.assign(form, emptyForm())
	try {
		const data = await getStockOperationEditor(props.cuttingPlan, props.operation)
		Object.assign(stock, data || { context: {}, dimensions: [] })
		form.update_type = data?.defaults?.update_type || ""
	} catch (reason) {
		error.value = reason.message || "Unable to load plan stock."
	} finally {
		loading.value = false
	}
}

async function save(submit) {
	if (!canSave.value) return
	saving.value = true
	saveMode.value = submit ? "submit" : "draft"
	error.value = ""
	try {
		const saved = await saveStockOperation(props.cuttingPlan, props.operation, {
			item_details: itemDetails.value,
			purpose: form.purpose,
			to_warehouse: form.to_warehouse,
			update_type: form.update_type,
		}, submit)
		emit("changed", saved)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason.message || "Unable to create the stock document."
	} finally {
		saving.value = false
		saveMode.value = ""
	}
}

function emptyForm() { return { purpose: "", to_warehouse: "", update_type: "" } }
</script>

<style scoped>
.erp-stock-loading,
.erp-stock-stack {
	display: grid;
	gap: var(--erp-space-3);
}

.erp-stock-context {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface-soft);
}

.erp-stock-context > div {
	display: grid;
	gap: var(--erp-space-1);
	padding: 10px var(--erp-space-3);
	border-right: 1px solid var(--erp-border);
}

.erp-stock-context > div:last-child {
	border-right: 0;
}

.erp-stock-context span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	letter-spacing: 0.035em;
	text-transform: uppercase;
}

.erp-stock-context strong {
	overflow: hidden;
	color: var(--erp-text);
	font-size: 13px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.erp-operation-fields {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--erp-space-3);
}

.erp-select-field {
	display: grid;
	gap: 6px;
}

.erp-select-field > span {
	color: #405047;
	font-size: var(--erp-font-size-caption);
	font-weight: 700;
}

@media (max-width: 720px) {
	.erp-operation-fields,
	.erp-stock-context {
		grid-template-columns: 1fr;
	}
}
</style>
