<template>
	<Dialog
		:visible="visible"
		modal
		:dismissable-mask="false"
		maximizable
		:header="title"
		class="fabric-stock-operation-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="requestVisibility"
	>
		<div v-if="loading" class="fabric-stock-loading"><Skeleton v-for="index in 6" :key="index" height="3rem" /></div>
		<div v-else class="fabric-stock-stack">
			<section class="fabric-operation-fields">
				<label v-if="operation === 'stock_entry'" class="fabric-select-field"><span>Purpose *</span><Select v-model="form.purpose" :options="editor.purpose_options || []" :disabled="editor.purpose_locked" placeholder="Select purpose" fluid @change="markDirty" /></label>
				<label v-if="operation === 'stock_reconciliation'" class="fabric-select-field"><span>Purpose *</span><Select v-model="form.purpose" :options="editor.purpose_options || []" placeholder="Select purpose" fluid @change="markDirty" /></label>
				<label v-if="operation === 'stock_update'" class="fabric-select-field"><span>Update type *</span><Select v-model="form.update_type" :options="editor.update_type_options || []" placeholder="Select Add or Reduce" fluid @change="markDirty" /></label>

				<LinkField v-if="operation === 'stock_entry'" v-model="form.from_warehouse" label="From warehouse *" doctype="Warehouse" :disabled="editor.protected_completion" :show-open-button="false" :show-clear="!editor.protected_completion" @update:model-value="markDirty" />
				<LinkField v-if="operation === 'stock_entry' && (form.purpose === 'Send to Warehouse' || editor.protected_completion)" v-model="form.to_warehouse" label="To warehouse *" doctype="Warehouse" :disabled="editor.protected_completion" :show-open-button="false" :show-clear="!editor.protected_completion" @update:model-value="markDirty" />
				<LinkField v-if="operation === 'stock_reconciliation'" v-model="form.default_warehouse" label="Warehouse *" doctype="Warehouse" :show-open-button="false" show-clear @update:model-value="markDirty" />
				<LinkField v-if="operation === 'stock_reconciliation'" v-model="form.default_supplier" label="Supplier" doctype="Supplier" :show-open-button="false" show-clear @update:model-value="markDirty" />
				<LinkField v-if="operation === 'stock_update'" v-model="form.warehouse" label="Warehouse *" doctype="Warehouse" :show-open-button="false" show-clear @update:model-value="markDirty" />
				<LinkField v-if="operation === 'stock_update'" v-model="form.supplier" label="Supplier" doctype="Supplier" :show-open-button="false" show-clear @update:model-value="markDirty" />
				<DateField v-model="form.posting_date" label="Posting date" :disabled="editor.protected_completion" @update:model-value="markPostingDateTimeDirty" />
				<TimeField v-model="form.posting_time" label="Posting time" :disabled="editor.protected_completion" @update:model-value="markPostingDateTimeDirty" />
			</section>

			<StockItemComposer
				v-model="itemDetails"
				:operation="operation"
				:purpose="form.purpose"
				:update-type="form.update_type"
				:editor="editor"
				:read-only="editor.protected_completion"
				:schema-loader="loadSchema"
				@dirty="markDirty"
			/>
		</div>

		<template #footer>
			<div class="fabric-stock-footer">
				<Button label="Close" severity="secondary" text :disabled="saving" @click="requestVisibility(false)" />
				<div><DocumentSaveButton :show-save="!editor.protected_completion && (editor.permissions?.can_create || editor.permissions?.can_write)" :show-submit="Boolean(editor.permissions?.can_submit)" :submit-label="editor.protected_completion ? 'Submit Completion' : 'Save & Submit'" :disabled="!canSave" :loading="saving" @save="save(false)" @submit="save(true)" /></div>
			</div>
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" :title="`${title} could not be completed`" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { getFabricStockItemSchema, getFabricStockOperationEditor, saveFabricStockOperation } from "../../api/fabricStore.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import TimeField from "../../components/common/TimeField.vue"
import StockItemComposer from "../../components/stock/StockItemComposer.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	operation: { type: String, required: true },
	name: { type: String, default: "" },
	expectedModified: { type: String, default: "" },
	sourceContext: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()

const labels = { stock_entry: "Stock Entry", stock_reconciliation: "Stock Reconciliation", stock_update: "Stock Update", lot_transfer: "Lot Transfer" }
const loading = ref(false)
const saving = ref(false)
const saveMode = ref("")
const error = ref("")
const dirty = ref(false)
const editor = ref({ dimensions: [], permissions: {} })
const itemDetails = ref([])
const form = reactive(emptyForm())
const title = computed(() => `${props.name ? "Edit" : "Create"} ${labels[props.operation] || "Stock Document"}${props.name ? ` · ${props.name}` : ""}`)
const canSave = computed(() => {
	const canMutate = editor.value.protected_completion
		? editor.value.permissions?.can_submit
		: editor.value.permissions?.can_create || editor.value.permissions?.can_write
	if (!canMutate || !itemDetails.value.some((group) => group.items?.length)) return false
	if (props.operation === "stock_entry" && (!form.purpose || !form.from_warehouse)) return false
	if (props.operation === "stock_entry" && form.purpose === "Send to Warehouse" && !form.to_warehouse) return false
	if (props.operation === "stock_reconciliation" && (!form.purpose || !form.default_warehouse)) return false
	if (props.operation === "stock_update" && (!form.update_type || !form.warehouse)) return false
	return true
})

watch(() => [props.visible, props.operation, props.name, JSON.stringify(props.sourceContext || {})], ([visible]) => { if (visible) load() }, { immediate: true })

async function load() {
	loading.value = true
	error.value = ""
	itemDetails.value = []
	Object.assign(form, emptyForm())
	try {
		editor.value = await getFabricStockOperationEditor(props.operation, { name: props.name, sourceContext: props.sourceContext }) || { dimensions: [], permissions: {} }
		Object.assign(form, editor.value.defaults || {})
		itemDetails.value = clone(editor.value.item_groups || [])
		dirty.value = false
	} catch (reason) { error.value = reason?.message || "Unable to prepare this stock document." }
	finally { loading.value = false }
}

function loadSchema(operation, item) { return getFabricStockItemSchema(operation, item) }
function markDirty() { if (!loading.value) dirty.value = true }
function markPostingDateTimeDirty() { form.edit_posting_date_and_time = 1; markDirty() }
async function save(submit) {
	if (!canSave.value) return
	saving.value = true
	saveMode.value = submit ? "submit" : "draft"
	error.value = ""
	try {
		const saved = await saveFabricStockOperation(props.operation, { ...form, item_details: itemDetails.value }, { name: props.name, expectedModified: props.expectedModified || editor.value.modified, submit })
		dirty.value = false
		emit("changed", saved)
		emit("update:visible", false)
	} catch (reason) { error.value = reason?.message || "Unable to save this stock document." }
	finally { saving.value = false; saveMode.value = "" }
}
function requestVisibility(value) {
	if (value) return
	if (dirty.value) return confirmAction({
		header: "Discard stock document changes?",
		message: "Discard the unsaved stock document changes? This cannot be undone.",
		acceptLabel: "Discard Changes",
		rejectLabel: "Keep Editing",
		acceptIcon: "pi pi-trash",
		accept: () => emit("update:visible", false),
	})
	emit("update:visible", false)
}
function emptyForm() { return { purpose: "", update_type: "", from_warehouse: "", to_warehouse: "", default_warehouse: "", default_supplier: "", warehouse: "", supplier: "", posting_date: "", posting_time: "", edit_posting_date_and_time: 0, comments: "" } }
function clone(value) { return JSON.parse(JSON.stringify(value || [])) }
</script>

<style scoped>
.fabric-stock-loading, .fabric-stock-stack { display: grid; gap: var(--erp-space-3); }
.fabric-stock-stack { overflow-y: visible; padding: 1px; }
.fabric-operation-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); }
.fabric-select-field { display: grid; align-content: start; gap: 6px; }
.fabric-select-field > span { color: #405047; font-size: var(--erp-font-size-caption); font-weight: 700; }
.fabric-stock-footer { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 12px; }
.fabric-stock-footer > div { display: flex; gap: 8px; }
@media (max-width: 860px) { .fabric-operation-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) {
	.fabric-operation-fields { grid-template-columns: 1fr; }
	.fabric-stock-footer { align-items: stretch; flex-direction: column; }
	.fabric-stock-footer > div { display: grid; grid-template-columns: 1fr; }
	.fabric-stock-footer > :deep(.p-button),
	.fabric-stock-footer > div,
	.fabric-stock-footer > div :deep(.document-save-button) { width: 100%; }
}
</style>
