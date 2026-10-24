<template>
	<Dialog
		:visible="visible"
		modal
		:dismissable-mask="false"
		maximizable
		:header="title"
		class="item-conversion-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="requestVisibility"
	>
		<div v-if="loading" class="item-conversion-stack"><Skeleton v-for="index in 5" :key="index" height="3rem" /></div>
		<div v-else class="item-conversion-stack">
			<div v-if="record.name" class="item-conversion-status">
				<DocumentStatusBadge :docstatus="record.docstatus" :label="record.status" />
				<small v-if="record.amended_from">Amended from {{ record.amended_from }}</small>
			</div>

			<section class="item-conversion-header" aria-label="Conversion details">
				<FormField v-for="field in headerFields" :key="field.fieldname" :class="{ 'item-conversion-header__wide': field.fieldtype === 'Small Text' }" :field="field" :model-value="form[field.fieldname]" :required="Boolean(field.reqd) && !readOnly" :disabled="readOnly" :show-open-button="false" :show-clear="!readOnly" @update:model-value="form[field.fieldname] = $event" />
			</section>

			<section class="item-conversion-flow" aria-label="Item Conversion">
				<ItemConversionSide v-model:side="fromSide" direction="from" :schema="schemas.from" :loading-schema="schemaLoading.from" :read-only="readOnly" :rate="sideRate('from')" :amount="sideAmount('from')" @item-change="loadSchema('from', $event)" />
				<div class="item-conversion-arrow" aria-hidden="true">
					<i class="pi pi-arrow-right" />
					<span>Converts into</span>
				</div>
				<ItemConversionSide v-model:side="toSide" direction="to" :schema="schemas.to" :loading-schema="schemaLoading.to" :read-only="readOnly" :rate="sideRate('to')" :amount="sideAmount('to')" @item-change="loadSchema('to', $event)" />
			</section>

			<section class="item-conversion-totals" aria-label="Conversion totals">
				<div><span>From Value</span><strong>{{ formatAmount(totals.from) }}</strong></div>
				<div><span>To Value</span><strong>{{ formatAmount(totals.to) }}</strong></div>
				<div :class="{ 'item-conversion-totals--mismatch': totals.difference }"><span>Difference</span><strong>{{ formatAmount(totals.difference) }}</strong></div>
			</section>
			<p v-if="!readOnly" class="item-conversion-note">One From item and one To item (a single size each). The To rate is the From value divided by the To quantity, so both values match.</p>
		</div>

		<template #footer>
			<div class="item-conversion-footer">
				<Button label="Close" severity="secondary" text :disabled="Boolean(acting)" @click="requestVisibility(false)" />
				<div>
					<DocumentDeleteButton v-if="record.name && permissions.can_delete" doctype="SD YRP Item Conversion" document-label="Item Conversion" :name="record.name" :docstatus="record.docstatus" :disabled="Boolean(acting)" :redirect="false" @deleted="documentDeleted" />
					<DocumentPrintButton v-if="record.name && record.docstatus !== 0 && printFormats.length" doctype="SD YRP Item Conversion" :name="record.name" :formats="printFormats" :docstatus="record.docstatus" :disabled="Boolean(acting)" />
					<Button v-if="permissions.can_amend" label="Amend" icon="pi pi-copy" severity="secondary" outlined :loading="acting === 'amend'" :disabled="Boolean(acting)" @click="changeStatus('amend')" />
					<Button v-if="permissions.can_cancel" label="Cancel Document" icon="pi pi-ban" severity="danger" outlined :loading="acting === 'cancel'" :disabled="Boolean(acting)" @click="confirmCancel" />
					<DocumentSaveButton v-if="record.docstatus === 0" :saved="Boolean(record.name)" :dirty="dirty" :docstatus="0" :document-label="`Item Conversion ${record.name || ''}`.trim()" :show-save="canEdit" :show-submit="Boolean(permissions.can_submit)" :disabled="Boolean(acting)" :loading="Boolean(acting)" @save="save(false)" @submit="save(true)" />
				</div>
			</div>
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" title="Item Conversion could not be completed" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { changeItemConversionStatus, getItemConversion, getItemConversionItemSchema, getItemConversionValuationRate, saveItemConversion } from "../../../api/itemConversion.js"
import FormField from "../../../components/common/FormField.vue"
import DocumentDeleteButton from "../../../components/documents/DocumentDeleteButton.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import DocumentPrintButton from "../../../components/documents/DocumentPrintButton.vue"
import DocumentSaveButton from "../../../components/documents/DocumentSaveButton.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { useActionConfirmation } from "../../../utils/useActionConfirmation.js"
import ItemConversionSide from "./ItemConversionSide.vue"
import { conversionPreview, emptySide, formatAmount, inheritDimensions, sideProblems, sideSaveValues, valuationArgs } from "./itemConversion.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	name: { type: String, default: "" },
	newDefaults: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()

const headerFields = [
	{ fieldname: "warehouse", fieldtype: "Link", options: "Warehouse", label: "Location", reqd: 1 },
	{ fieldname: "posting_date", fieldtype: "Date", label: "Posting Date", reqd: 1 },
	{ fieldname: "posting_time", fieldtype: "Time", label: "Posting Time", reqd: 1 },
	{ fieldname: "comments", fieldtype: "Small Text", label: "Comments" },
]
const loading = ref(false)
const acting = ref("")
const error = ref("")
const payload = ref({ record: {}, permissions: {}, totals: {} })
const form = reactive({ warehouse: "", posting_date: "", posting_time: "", comments: "" })
const fromSide = ref(emptySide())
const toSide = ref(emptySide())
const schemas = reactive({ from: null, to: null })
const schemaLoading = reactive({ from: false, to: false })
const cleanSignature = ref("")
let valuationSequence = 0

const record = computed(() => payload.value.record || {})
const permissions = computed(() => payload.value.permissions || {})
const printFormats = computed(() => payload.value.print_formats || [])
const canEdit = computed(() => record.value.docstatus === 0 && Boolean(record.value.name ? permissions.value.can_write : permissions.value.can_create))
const readOnly = computed(() => !canEdit.value)
const title = computed(() => record.value.name ? `Item Conversion · ${record.value.name}` : "New Item Conversion")
const signature = computed(() => JSON.stringify({ form, from: sideSaveValues(fromSide.value), to: sideSaveValues(toSide.value) }))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)
const preview = computed(() => conversionPreview(fromSide.value, toSide.value))
const totals = computed(() => readOnly.value
	? { from: payload.value.totals?.from_total_amount || 0, to: payload.value.totals?.to_total_amount || 0, difference: payload.value.totals?.difference_amount || 0 }
	: { from: preview.value.fromValue, to: preview.value.toValue, difference: preview.value.difference })

function sideRate(direction) {
	if (readOnly.value) return Number((direction === "from" ? fromSide : toSide).value.rate || 0)
	return direction === "from" ? Number(fromSide.value.rate || 0) : preview.value.toRate
}
function sideAmount(direction) {
	if (readOnly.value) return Number((direction === "from" ? fromSide : toSide).value.amount || 0)
	return direction === "from" ? preview.value.fromValue : preview.value.toValue
}

watch(() => [props.visible, props.name], ([visible]) => { if (visible) load(props.name) }, { immediate: true })
watch(() => valuationArgs(fromSide.value, schemas.from, form), refreshFromRate, { deep: true })
watch(() => [fromSide.value.lot, fromSide.value.received_type], () => { if (canEdit.value) toSide.value = inheritDimensions(fromSide.value, toSide.value) })

async function load(name) {
	loading.value = true
	error.value = ""
	try {
		payload.value = await getItemConversion(name)
		Object.assign(form, payload.value.values || {})
		if (!name) for (const fieldname of Object.keys(form)) if (props.newDefaults?.[fieldname]) form[fieldname] = props.newDefaults[fieldname]
		fromSide.value = emptySide(payload.value.sides?.from)
		toSide.value = emptySide(payload.value.sides?.to)
		await Promise.all([loadSchema("from", fromSide.value.item), loadSchema("to", toSide.value.item)])
		cleanSignature.value = signature.value
	} catch (reason) {
		error.value = reason?.message || "Unable to load this Item Conversion."
	} finally {
		loading.value = false
	}
}

async function loadSchema(direction, item) {
	schemas[direction] = null
	if (!item) return
	schemaLoading[direction] = true
	try {
		const schema = await getItemConversionItemSchema(item)
		if ((direction === "from" ? fromSide : toSide).value.item === item) schemas[direction] = schema
	} catch (reason) {
		error.value = reason?.message || `Unable to load ${item}.`
	} finally {
		schemaLoading[direction] = false
	}
}

async function refreshFromRate(args) {
	if (!canEdit.value) return
	const sequence = ++valuationSequence
	if (!args) { fromSide.value.rate = 0; return }
	try {
		const result = await getItemConversionValuationRate(args)
		if (sequence === valuationSequence) fromSide.value.rate = Number(result?.rate || 0)
	} catch (reason) {
		error.value = reason?.message || "Unable to read the From valuation rate."
	}
}

function problems() {
	const missing = headerFields.filter((field) => field.reqd && !form[field.fieldname]).map((field) => `Enter the ${field.label}.`)
	return [...missing, ...sideProblems(fromSide.value, schemas.from, "from"), ...sideProblems(toSide.value, schemas.to, "to")]
}

async function save(submit) {
	const found = problems()
	if (found.length) { error.value = found.join("\n"); return }
	acting.value = submit ? "submit" : "save"
	error.value = ""
	try {
		const saved = await saveItemConversion(
			{ ...form, from: sideSaveValues(fromSide.value), to: sideSaveValues(toSide.value) },
			{ name: record.value.name, expectedModified: record.value.modified, submit },
		)
		cleanSignature.value = signature.value
		emit("changed", saved)
		await load(saved.record.name)
	} catch (reason) {
		error.value = reason?.message || "Unable to save this Item Conversion."
	} finally {
		acting.value = ""
	}
}

async function changeStatus(action) {
	acting.value = action
	error.value = ""
	try {
		const changed = await changeItemConversionStatus(record.value.name, action, record.value.modified)
		emit("changed", changed)
		await load(changed.record.name)
	} catch (reason) {
		error.value = reason?.message || `Unable to ${action} this Item Conversion.`
	} finally {
		acting.value = ""
	}
}

function confirmCancel() {
	confirmAction({
		header: "Cancel Item Conversion?",
		message: `Cancel ${record.value.name}? Its stock movement will be reversed.`,
		acceptLabel: "Cancel Document",
		accept: () => changeStatus("cancel"),
	})
}

function documentDeleted() {
	emit("changed")
	emit("update:visible", false)
}

function requestVisibility(value) {
	if (value) return
	if (dirty.value && canEdit.value) return confirmAction({
		header: "Discard Item Conversion changes?",
		message: "Discard the unsaved changes? This cannot be undone.",
		acceptLabel: "Discard Changes",
		rejectLabel: "Keep Editing",
		acceptIcon: "pi pi-trash",
		accept: () => emit("update:visible", false),
	})
	emit("update:visible", false)
}
</script>

<style scoped>
.item-conversion-stack { display: grid; gap: var(--erp-space-3); padding: 1px; }
.item-conversion-status { display: flex; align-items: center; gap: var(--erp-space-2); }
.item-conversion-status small, .item-conversion-note { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.item-conversion-note { margin: 0; }
.item-conversion-header { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); }
.item-conversion-header__wide { grid-column: 1 / -1; }
.item-conversion-flow { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: var(--erp-space-3); align-items: stretch; }
.item-conversion-arrow {
	display: grid;
	align-content: center;
	justify-items: center;
	gap: 6px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	font-weight: 700;
}
.item-conversion-arrow i {
	display: grid;
	width: 40px;
	height: 40px;
	place-items: center;
	color: var(--erp-on-accent);
	font-size: 1.1rem;
	background: var(--erp-accent);
	border-radius: 50%;
}
.item-conversion-totals {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: var(--erp-space-2);
	padding: var(--erp-space-2) var(--erp-space-3);
	background: var(--erp-surface-muted);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
}
.item-conversion-totals div { display: grid; gap: 2px; }
.item-conversion-totals span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 700; }
.item-conversion-totals strong { font-variant-numeric: tabular-nums; }
.item-conversion-totals--mismatch strong { color: var(--erp-danger); }
.item-conversion-footer { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 12px; }
.item-conversion-footer > div { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
@media (max-width: 900px) {
	.item-conversion-flow { grid-template-columns: 1fr; }
	.item-conversion-arrow i { transform: rotate(90deg); }
	.item-conversion-arrow span { display: none; }
}
@media (max-width: 560px) {
	.item-conversion-header, .item-conversion-totals { grid-template-columns: 1fr; }
	.item-conversion-footer { align-items: stretch; flex-direction: column; }
}
</style>
