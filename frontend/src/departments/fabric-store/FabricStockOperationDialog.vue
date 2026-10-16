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
				<FormField v-for="field in headerFields" :key="field.fieldname" :class="{ 'fabric-select-field': field.fieldtype === 'Select' }" :field="field" :form="form" :model-value="form[field.fieldname]" :required="Boolean(field.reqd)" :invalid="Boolean(fieldErrors[field.fieldname])" :error="fieldErrors[field.fieldname] || ''" :show-open-button="false" :show-clear="!field.read_only" @update:model-value="updateField(field.fieldname, $event)" />
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
				<div><Button v-if="canDiscard" label="Discard Draft" icon="pi pi-trash" severity="danger" outlined :disabled="saving" @click="requestDiscard" /><DocumentSaveButton :show-save="!editor.protected_completion && (editor.permissions?.can_create || editor.permissions?.can_write)" :show-submit="Boolean(editor.permissions?.can_submit)" :submit-label="editor.protected_completion ? 'Submit Completion' : 'Save & Submit'" :disabled="!canSave" :loading="saving" @save="save(false)" @submit="save(true)" /></div>
			</div>
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" :title="`${title} could not be completed`" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { discardCompletionDraft, getFabricStockItemSchema, getFabricStockOperationEditor, saveFabricStockOperation } from "../../api/fabricStore.js"
import FormField from "../../components/common/FormField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import StockItemComposer from "../../components/stock/StockItemComposer.vue"
import { mapFieldError, requiredFieldErrors } from "../../utils/fieldErrors.js"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	operation: { type: String, required: true },
	name: { type: String, default: "" },
	expectedModified: { type: String, default: "" },
	initialEditor: { type: Object, default: null },
	sourceContext: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()

const labels = { stock_entry: "Stock Entry", stock_reconciliation: "Stock Reconciliation", stock_update: "Stock Update", lot_transfer: "Lot Transfer" }
const loading = ref(false)
const saving = ref(false)
const saveMode = ref("")
const error = ref("")
const fieldErrors = ref({})
const dirty = ref(false)
const editor = ref({ dimensions: [], permissions: {} })
const itemDetails = ref([])
const form = reactive(emptyForm())
const title = computed(() => `${props.name ? "Edit" : "Create"} ${labels[props.operation] || "Stock Document"}${props.name ? ` · ${props.name}` : ""}`)
const canSave = computed(() => {
	const canMutate = editor.value.protected_completion
		? editor.value.permissions?.can_submit
		: editor.value.permissions?.can_create || editor.value.permissions?.can_write
	return Boolean(canMutate)
})

const headerFields = computed(() => {
	const fields = []
	const protectedFields = Boolean(editor.value.protected_completion)
	const receipt = form.purpose === "Receive at Warehouse"
	const link = (fieldname, label, options, required = false, readOnly = false) => fields.push({ fieldname, label, options, fieldtype: "Link", reqd: required, read_only: readOnly })
	if (["stock_entry", "stock_reconciliation"].includes(props.operation)) fields.push({ fieldname: "purpose", label: "Purpose", fieldtype: "Select", options: (editor.value.purpose_options || []).join("\n"), reqd: true, read_only: editor.value.purpose_locked })
	if (props.operation === "stock_entry") {
		if (receipt) link("outgoing_stock_entry", "Outgoing Stock Entry", "YRP Stock Entry", true, true)
		link("from_warehouse", "From Warehouse", "Warehouse", form.purpose !== "Material Receipt", protectedFields || receipt || form.purpose === "Material Receipt")
		if (["Send to Warehouse", "Material Receipt", "Receive at Warehouse"].includes(form.purpose) || protectedFields) link("to_warehouse", "To Warehouse", "Warehouse", true, protectedFields || receipt)
		if (form.purpose === "Send to Warehouse") fields.push({ fieldname: "skip_transit", label: "Skip Transit", fieldtype: "Check" })
	}
	if (props.operation === "stock_reconciliation") {
		link("default_warehouse", "Warehouse", "Warehouse", true)
		link("default_supplier", "Supplier", "Supplier")
	}
	if (props.operation === "stock_update") {
		fields.push({ fieldname: "update_type", label: "Update Type", fieldtype: "Select", options: (editor.value.update_type_options || []).join("\n"), reqd: true })
		link("warehouse", "Warehouse", "Warehouse", true)
		link("supplier", "Supplier", "Supplier")
	}
	if (editor.value.posting_fields?.length) fields.push({ fieldname: "edit_posting_date_and_time", label: "Edit Posting Date and Time", fieldtype: "Check", read_only: protectedFields })
	for (const field of editor.value.posting_fields || []) fields.push({ ...field, fieldtype: field.fieldname === "posting_date" ? "Date" : "Time", reqd: field.reqd || Boolean(form.edit_posting_date_and_time), read_only: protectedFields || !form.edit_posting_date_and_time })
	return fields
})
function updateField(fieldname, value) {
	form[fieldname] = value
	delete fieldErrors.value[fieldname]
	if (fieldname === "purpose" && value === "Material Receipt") form.from_warehouse = ""
	markDirty()
}

const canDiscard = computed(() => Boolean(props.name && editor.value.protected_completion && editor.value.permissions?.can_delete))

watch(() => [props.visible, props.operation, props.name, JSON.stringify(props.sourceContext || {}), props.initialEditor], ([visible]) => { if (visible) load() }, { immediate: true })

async function load() {
	loading.value = true
	error.value = ""
	fieldErrors.value = {}
	itemDetails.value = []
	Object.assign(form, emptyForm())
	try {
		editor.value = props.initialEditor || await getFabricStockOperationEditor(props.operation, { name: props.name, sourceContext: props.sourceContext }) || { dimensions: [], permissions: {} }
		Object.assign(form, editor.value.defaults || {})
		itemDetails.value = clone(editor.value.item_groups || [])
		dirty.value = false
	} catch (reason) { error.value = reason?.message || "Unable to prepare this stock document." }
	finally { loading.value = false }
}

function loadSchema(operation, item) { return getFabricStockItemSchema(operation, item) }
function markDirty() { if (!loading.value) dirty.value = true }
async function save(submit) {
	if (!canSave.value) return
	fieldErrors.value = requiredFieldErrors(headerFields.value, form)
	if (Object.keys(fieldErrors.value).length) return
	if (!itemDetails.value.some((group) => group.items?.length)) { error.value = "Add at least one Item."; return }
	saving.value = true
	saveMode.value = submit ? "submit" : "draft"
	error.value = ""
	try {
		const saved = await saveFabricStockOperation(props.operation, { ...form, item_details: itemDetails.value }, { name: props.name, expectedModified: props.expectedModified || editor.value.modified, submit })
		dirty.value = false
		emit("changed", saved)
		emit("update:visible", false)
	} catch (reason) {
		const mapped = mapFieldError(reason, headerFields.value, "Unable to save this stock document.")
		fieldErrors.value = mapped.fields
		error.value = mapped.message
	}
	finally { saving.value = false; saveMode.value = "" }
}
function requestDiscard() {
	confirmAction({
		header: "Discard completion draft?",
		message: `Delete draft ${props.name}? Complete Transfer will prepare a fresh entry from the pending quantities.`,
		acceptLabel: "Discard Draft",
		rejectLabel: "Keep Draft",
		acceptIcon: "pi pi-trash",
		accept: discard,
	})
}
async function discard() {
	saving.value = true
	error.value = ""
	try {
		const discarded = await discardCompletionDraft(props.name, props.expectedModified || editor.value.modified)
		dirty.value = false
		emit("changed", discarded)
		emit("update:visible", false)
	} catch (reason) { error.value = reason?.message || "Unable to discard this draft." }
	finally { saving.value = false }
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
function emptyForm() { return { outgoing_stock_entry: "", skip_transit: 0, purpose: "", update_type: "", from_warehouse: "", to_warehouse: "", default_warehouse: "", default_supplier: "", warehouse: "", supplier: "", posting_date: "", posting_time: "", edit_posting_date_and_time: 0, comments: "" } }
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
