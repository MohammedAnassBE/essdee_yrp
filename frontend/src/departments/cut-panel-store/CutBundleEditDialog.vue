<template>
	<Dialog
		:visible="visible"
		modal
		maximizable
		:dismissable-mask="false"
		:closable="!busy"
		:close-on-escape="!busy"
		:header="record?.name ? `Cut Bundle Edit · ${record.name}` : 'New Cut Bundle Edit'"
		class="cut-bundle-edit-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="visibilityChanged"
	>
		<div v-if="loading" class="cut-bundle-dialog__loading"><Skeleton v-for="index in 7" :key="index" height="3rem" /></div>
		<div v-else class="cut-bundle-dialog__body">
			<section class="cut-bundle-document-card">
				<header><span>DOCUMENT</span><h3>Bundle transformation</h3><DocumentStatusBadge :docstatus="record?.docstatus" :label="record?.status || 'Draft'" /></header>
				<div class="cut-bundle-document-grid">
					<LinkField v-model="form.lot" label="Lot" doctype="SD YRP Lot" required :disabled="Boolean(record) || busy" @update:model-value="sourceChanged" />
					<LinkField v-model="form.warehouse" label="Warehouse" doctype="Supplier" required :disabled="Boolean(record) || busy" @update:model-value="sourceChanged" />
					<div class="cut-bundle-context"><span>Item</span><strong>{{ editor.context?.item || form.item || "Derived from Lot" }}</strong></div>
					<DateField v-model="form.posting_date" label="Posting Date" disabled />
					<TimeField v-model="form.posting_time" label="Posting Time" disabled />
					<label class="cut-bundle-select"><span>Colour</span><Select v-model="form.selected_colour" :options="choices.colours" :disabled="!canEdit || busy" fluid placeholder="Select colour" @change="colourChanged" /></label>
					<div class="cut-bundle-context"><span>Printed Time</span><strong>{{ formattedPrintedTime }}</strong></div>
					<Button v-if="canEdit" label="Fetch Bundles" icon="pi pi-refresh" severity="secondary" outlined :loading="acting === 'preview'" :disabled="!form.lot || !form.warehouse || busy" @click="preview()" />
				</div>
			</section>

			<section v-if="canEdit && availableRows.length" class="cut-bundle-source-card" aria-label="Available bundles">
				<header><div><span>SOURCE STOCK</span><h3>Select input bundles</h3></div><strong>{{ selectedKeys.size }} selected</strong></header>
				<div class="cut-bundle-table-scroll" tabindex="0" role="region" aria-label="Available input bundles">
					<table><thead><tr><th>Select</th><th>Lay / Bundle</th><th>Colour</th><th>Size</th><th>Panel</th><th>Shade</th><th>Qty</th></tr></thead>
					<tbody><tr v-for="row in availableRows" :key="row.key"><td><label class="cut-bundle-check"><input type="checkbox" :checked="selectedKeys.has(row.key)" :aria-label="`Select bundle ${row.bundle_no}, panel ${row.panel}`" @change="toggleInput(row)" /></label></td><td>{{ row.lay_no }} / {{ row.bundle_no }}</td><td>{{ row.colour }}</td><td>{{ row.size }}</td><td>{{ row.panel }}</td><td>{{ row.shade || '—' }}</td><td>{{ formatNumber(row.qty) }}</td></tr></tbody></table>
				</div>
				<footer><Button label="Use Selected Bundles" icon="pi pi-arrow-down" severity="secondary" :disabled="!selectedKeys.size" @click="useSelectedBundles" /></footer>
			</section>

			<div v-if="inputs.length || outputs.length" class="cut-bundle-comparison">
				<BundleTable title="Input bundles" eyebrow="BEFORE" :rows="inputs" />
				<BundleTable title="Output bundles" eyebrow="AFTER" :rows="outputs" :editable="canEdit" :choices="{ colours: choices.colours, sizes: choices.sizes, panels: panelOptions }" @add="addOutput" @split="splitCompositeOutputs" @remove="removeOutput" @update="updateOutput" />
			</div>
			<div v-else-if="!canEdit || previewed" class="cut-bundle-empty">No input and output bundles are available.</div>
		</div>

		<DocumentActivity :doctype="'SD YRP Cut Bundle Edit'" :name="record?.name || ''" :record="record" />
		<template #footer>
			<div class="cut-bundle-dialog__footer">
				<span>{{ quantitySummary }}</span>
				<div>
					<DocumentShortcuts :busy="busy || confirmationVisible" :can-save="canEdit && Boolean(inputs.length && outputs.length) && (!record?.name || dirty)" :can-submit="Boolean(record?.permissions?.can_submit && !dirty && inputs.length && outputs.length)" submit-confirms :can-cancel="Boolean(record?.permissions?.can_cancel)" cancel-confirms @save="save" @submit="requestCommand('submit')" @cancel="requestCommand('cancel')" />
					<Button label="Close" severity="secondary" text :disabled="busy" @click="requestClose" />
					<DocumentDeleteButton v-if="record?.name" doctype="SD YRP Cut Bundle Edit" :name="record.name" :docstatus="record.docstatus" :disabled="busy" :redirect="false" @deleted="documentDeleted" />
					<DocumentPrintButton v-if="record?.name" doctype="SD YRP Cut Bundle Edit" :name="record.name" :docstatus="record.docstatus" :disabled="busy" />
					<Button v-if="record?.permissions?.can_print" label="Print Labels" icon="pi pi-print" severity="secondary" outlined :disabled="busy" @click="printerVisible = true" />
					<Button v-if="record?.docstatus === 2 && record?.permissions?.can_amend" label="Amend" icon="pi pi-copy" severity="secondary" outlined :disabled="busy" @click="requestCommand('amend')" />
					<Button v-if="record?.permissions?.can_cancel" label="Cancel Document" :title="withShortcutHint('Cancel Document', 'cancel')" icon="pi pi-ban" severity="danger" outlined :disabled="busy" @click="requestCommand('cancel')" />
					<Button v-if="record?.permissions?.can_submit" label="Submit" :title="withShortcutHint('Submit', 'submit')" icon="pi pi-check" severity="secondary" outlined :disabled="busy || !inputs.length || !outputs.length" @click="requestCommand('submit')" />
					<Button v-if="canEdit" label="Save" :title="withShortcutHint('Save', 'save')" icon="pi pi-save" :loading="acting === 'save'" :disabled="busy || !inputs.length || !outputs.length" @click="save" />
				</div>
			</div>
		</template>
	</Dialog>

	<PrinterDialog v-model:visible="printerVisible" :busy="acting === 'print'" @confirm="printLabels" />
	<DocumentConfirmationDialog
		v-model:visible="confirmationVisible"
		:title="confirmationTitle"
		:message="confirmationMessage"
		:confirm-label="pendingCommand === 'close' ? 'Discard Changes' : pendingCommand === 'cancel' ? 'Cancel Document' : pendingCommand === 'amend' ? 'Create Amendment' : 'Submit'"
		:severity="pendingCommand === 'cancel' || pendingCommand === 'close' ? 'danger' : 'success'"
		:busy="acting === pendingCommand"
		@confirm="confirmCommand"
	/>
	<DocumentErrorDialog :message="error" title="Cut Bundle Edit action failed" @dismiss="error = ''" />
</template>

<script setup>
import DocumentActivity from "../../components/documents/DocumentActivity.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import Button from "primevue/button"
import DocumentShortcuts from "../../components/documents/DocumentShortcuts.vue"
import { withShortcutHint } from "../../utils/documentShortcuts.js"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, defineComponent, h, reactive, ref, watch, withDirectives } from "vue"

import { confirmCutBundlePrint, executeCutBundleCommand, getCutBundleEditor, getCutBundlePrintData, previewCutBundleSource, saveCutBundle } from "../../api/cutPanelStore.js"
import { printQzRaw } from "../../api/qzPrinter.js"
import DateField from "../../components/common/DateField.vue"
import { vEntryTable } from "../../components/common/childGrid/entryTable.js"
import { useRowSelection } from "../../components/common/childGrid/rowSelection.js"
import LinkField from "../../components/common/LinkField.vue"
import TimeField from "../../components/common/TimeField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { formatDisplayDatetime } from "../../utils/dateFormat.js"
import PrinterDialog from "./PrinterDialog.vue"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../../utils/newDocumentDefaults.js"

const BundleTable = defineComponent({
	props: { title: String, eyebrow: String, rows: Array, editable: Boolean, choices: { type: Object, default: () => ({}) } },
	emits: ["add", "split", "remove", "update"],
	setup(props, { emit }) {
		const selection = useRowSelection(() => props.editable ? (props.rows || []).map((_, index) => index) : [])
		watch(() => props.rows, () => selection.toggleAll(false))
		const deleteSelected = () => selection.removeSelected((index) => emit("remove", index), () => props.editable)
		const checkbox = (attributes) => h("td", { class: "cut-bundle-pick" }, [h("input", { type: "checkbox", class: "cut-bundle-pick__box", ...attributes })])
		const selectAll = () => h("th", { class: "cut-bundle-pick" }, [h("input", { type: "checkbox", class: "cut-bundle-pick__box", "data-row-select": "", checked: selection.isAllSelected.value, indeterminate: selection.isPartlySelected.value, disabled: !props.rows?.length, "aria-label": `Select all ${props.title}`, onChange: (event) => selection.toggleAll(event.target.checked) })])
		const rowCheckbox = (index) => checkbox({ "data-row-select": "", tabindex: -1, checked: selection.isSelected(index), "aria-label": `Select output bundle ${index + 1}`, onChange: (event) => selection.toggle(index, event.target.checked) })
		const footer = () => selection.selected.value.length ? [h("footer", { class: "cut-bundle-selection" }, [h("span", `${selection.selected.value.length} selected`), h(Button, { label: "Delete", icon: "pi pi-trash", severity: "danger", size: "small", onClick: deleteSelected })])] : []
		const cell = (row, field, index, type = "text") => {
			if (!props.editable) return String(row[field] ?? "—")
			const fieldLabel = `${field.replaceAll("_", " ")} for output bundle ${index + 1}`
			if (["colour", "size", "panel"].includes(field)) return h(Select, { modelValue: row[field], options: props.choices?.[`${field}s`] || [], fluid: true, "aria-label": fieldLabel, "onUpdate:modelValue": (value) => emit("update", { index, field, value }) })
			return h("input", { type, value: row[field], min: type === "number" ? 1 : undefined, required: field === "shade", "aria-label": fieldLabel, onInput: (event) => emit("update", { index, field, value: type === "number" ? Number(event.target.value) : event.target.value }) })
		}
		return () => h("section", { class: "cut-bundle-table-card", role: "region", "aria-label": props.title }, [
			h("header", [h("div", [h("span", props.eyebrow), h("h3", props.title)]), h("div", { class: "cut-bundle-table-actions" }, [h("strong", `${props.rows?.length || 0} bundles`), ...(props.editable ? [h("button", { type: "button", onClick: () => emit("split") }, [h("i", { class: "pi pi-arrows-h" }), " Split panels"]), h("button", { type: "button", onClick: () => emit("add") }, [h("i", { class: "pi pi-plus" }), " Add output"])] : [])])]),
			h("div", { class: "cut-bundle-table-scroll", tabindex: 0, role: "region", "aria-label": `${props.title} table` }, [withDirectives(h("table", [
				h("thead", [h("tr", [...(props.editable ? [selectAll()] : []), ...["Lay", "Bundle", "Colour", "Size", "Panel", "Shade", "Qty"].map((label) => h("th", label))])]),
				h("tbody", (props.rows || []).map((row, index) => h("tr", { key: `${row.lay_no}-${row.bundle_no}-${row.panel}-${index}` }, [
					...(props.editable ? [rowCheckbox(index)] : []),
					h("td", [cell(row, "lay_no", index, "number")]), h("td", [cell(row, "bundle_no", index, "number")]), h("td", [cell(row, "colour", index)]),
					h("td", [cell(row, "size", index)]), h("td", [cell(row, "panel", index)]), h("td", [cell(row, "shade", index)]), h("td", [cell(row, "qty", index, "number")]),
				]))),
			]), [[vEntryTable, { add: props.editable ? () => emit("add") : null, fixed: false }]])]),
			...footer(),
		])
	},
})

const props = defineProps({ visible: Boolean, documentName: { type: String, default: "" } })
const emit = defineEmits(["update:visible", "changed"])
const loading = ref(false)
const acting = ref("")
const error = ref("")
const previewed = ref(false)
const printerVisible = ref(false)
const confirmationVisible = ref(false)
const pendingCommand = ref("")
const editor = reactive({ context: {}, permissions: {}, record: null })
const form = reactive({ lot: "", warehouse: "", item: "", posting_date: "", posting_time: "", selected_colour: "" })
const choices = reactive({ colours: [], sizes: [], panels: [] })
const available = ref({})
const inputs = ref([])
const outputs = ref([])
const selectedKeys = ref(new Set())
const dirty = ref(false)
let loadSequence = 0
let previewSequence = 0
let actionSequence = 0
const record = computed(() => editor.record)
const busy = computed(() => Boolean(acting.value))
const canEdit = computed(() => record.value ? Boolean(record.value.permissions?.can_write) : Boolean(editor.permissions?.can_create))
const formattedPrintedTime = computed(() => formatDisplayDatetime(record.value?.printed_time, { fallback: "Not printed" }))
const availableRows = computed(() => flattenAvailable(available.value))
const panelOptions = computed(() => Array.isArray(choices.panels) ? choices.panels : Object.values(choices.panels || {}).flat())
const quantitySummary = computed(() => `Input ${formatNumber(totalQty(inputs.value))} · Output ${formatNumber(totalQty(outputs.value))}`)
const confirmationTitle = computed(() => pendingCommand.value === "close" ? "Discard unsaved changes?" : pendingCommand.value === "cancel" ? "Cancel Cut Bundle Edit?" : pendingCommand.value === "amend" ? "Amend Cut Bundle Edit?" : "Submit Cut Bundle Edit?")
const confirmationMessage = computed(() => pendingCommand.value === "close" ? "Your unsaved bundle changes will be lost." : pendingCommand.value === "cancel" ? `Cancel ${record.value?.name}?` : pendingCommand.value === "amend" ? `Create a new draft amendment from ${record.value?.name}?` : `Submit ${record.value?.name}? Bundle stock will be checked again.`)

watch(() => [props.visible, props.documentName], ([visible]) => {
	if (visible) load()
	else {
		loadSequence += 1
		previewSequence += 1
		actionSequence += 1
		loading.value = false
		acting.value = ""
	}
})

async function load() {
	const sequence = ++loadSequence
	const requestedDocumentName = props.documentName
	previewSequence += 1
	actionSequence += 1
	loading.value = true; error.value = ""; previewed.value = false; selectedKeys.value = new Set()
	resetLoadedState()
	try {
		const payload = await getCutBundleEditor(requestedDocumentName)
		if (loadIsStale(sequence, requestedDocumentName)) return
		Object.assign(editor, payload || {})
		Object.assign(form, payload?.defaults || {}, payload?.record || {})
		const filterDefaults = requestedDocumentName ? {} : filterDefaultsFor("SD YRP Cut Bundle Edit", ["lot", "warehouse"])
		Object.assign(form, withNewDocumentDefaults({ lot: form.lot, warehouse: form.warehouse }, filterDefaults))
		form.selected_colour = payload?.record?.colour || payload?.defaults?.selected_colour || ""
		inputs.value = clone(payload?.record?.inputs || [])
		outputs.value = clone(payload?.record?.outputs || [])
		if (payload?.record?.docstatus === 0) {
			if (form.selected_colour) await preview(sequence, requestedDocumentName)
			else await preview(sequence, requestedDocumentName, true)
		} else if (!payload?.record && Object.keys(filterDefaults).length && form.lot && form.warehouse) await preview(sequence, requestedDocumentName, true)
		if (!loadIsStale(sequence, requestedDocumentName)) dirty.value = false
	} catch (reason) {
		if (!loadIsStale(sequence, requestedDocumentName)) error.value = reason.message || "Unable to load the Cut Bundle Edit."
	} finally {
		if (!loadIsStale(sequence, requestedDocumentName)) loading.value = false
	}
}

/** Staged list filters for a new document, limited to the fields this form holds. */
function filterDefaultsFor(doctype, keys) {
	const staged = takeNewDocumentDefaults(doctype)
	return Object.fromEntries(keys.filter((key) => key in staged).map((key) => [key, staged[key]]))
}

function loadIsStale(sequence, requestedDocumentName) {
	return sequence !== loadSequence || !props.visible || requestedDocumentName !== props.documentName
}

function actionIsStale(sequence, requestedDocumentName, requestedLoadSequence) {
	return sequence !== actionSequence || requestedLoadSequence !== loadSequence || !props.visible || requestedDocumentName !== props.documentName
}

function resetLoadedState() {
	for (const key of Object.keys(editor)) delete editor[key]
	Object.assign(editor, { context: {}, permissions: {}, record: null })
	Object.assign(form, { lot: "", warehouse: "", item: "", posting_date: "", posting_time: "", selected_colour: "" })
	Object.assign(choices, { colours: [], sizes: [], panels: [] })
	available.value = {}
	inputs.value = []
	outputs.value = []
	selectedKeys.value = new Set()
	dirty.value = false
	acting.value = ""
}

function invalidatePreview() { previewSequence += 1; if (acting.value === "preview") acting.value = "" }
function sourceChanged() { invalidatePreview(); dirty.value = true; form.selected_colour = ""; Object.assign(choices, { colours: [], sizes: [], panels: [] }); available.value = {}; inputs.value = []; outputs.value = []; selectedKeys.value = new Set(); previewed.value = false; if (form.lot && form.warehouse) preview(loadSequence, props.documentName, true) }
function colourChanged() { invalidatePreview(); dirty.value = true; available.value = {}; selectedKeys.value = new Set(); inputs.value = []; outputs.value = []; if (form.selected_colour) preview() }

async function preview(parentLoadSequence = loadSequence, requestedDocumentName = props.documentName, choicesOnly = false) {
	if (!choicesOnly && !form.selected_colour) {
		error.value = "Select a Colour to fetch bundles."
		return
	}
	const sequence = ++previewSequence
	const request = { lot: form.lot, warehouse: form.warehouse, posting_date: form.posting_date, posting_time: form.posting_time, selected_colour: form.selected_colour, record: record.value?.name }
	acting.value = "preview"; error.value = ""
	try {
		const payload = await previewCutBundleSource(request.lot, request.warehouse, { posting_date: request.posting_date, posting_time: request.posting_time, selected_colour: request.selected_colour }, request.record)
		if (sequence !== previewSequence || loadIsStale(parentLoadSequence, requestedDocumentName)) return
		Object.assign(editor.context, payload?.context || {})
		Object.assign(choices, payload?.choices || {})
		available.value = payload?.available || {}
		previewed.value = !choicesOnly
	} catch (reason) {
		if (sequence === previewSequence && !loadIsStale(parentLoadSequence, requestedDocumentName)) error.value = reason.message || "Unable to fetch available bundles."
	} finally {
		if (sequence === previewSequence && acting.value === "preview") acting.value = ""
	}
}

function toggleInput(row) {
	const next = new Set(selectedKeys.value)
	if (next.has(row.key)) next.delete(row.key); else next.add(row.key)
	selectedKeys.value = next
}
function useSelectedBundles() {
	inputs.value = availableRows.value.filter((row) => selectedKeys.value.has(row.key)).map(({ key, ...row }) => ({ ...row }))
	const largest = Math.max(0, ...availableRows.value.map((row) => Number(row.bundle_no || 0)))
	outputs.value = inputs.value.map((row, index) => ({ ...clone(row), bundle_no: largest + index + 1 }))
	dirty.value = true
}
function addOutput() { const source = outputs.value.at(-1) || inputs.value[0]; if (!source) return; const largest = Math.max(0, ...outputs.value.map((row) => Number(row.bundle_no || 0))); outputs.value.push({ ...clone(source), bundle_no: largest + 1 }); dirty.value = true }
function splitCompositeOutputs() { outputs.value = outputs.value.flatMap((row) => { const panels = String(row.panel || "").split(",").map((value) => value.trim()).filter(Boolean); return panels.length > 1 ? panels.map((panel) => ({ ...clone(row), panel })) : [row] }); dirty.value = true }
function updateOutput({ index, field, value }) { outputs.value[index] = { ...outputs.value[index], [field]: value }; dirty.value = true }
function removeOutput(index) { outputs.value.splice(index, 1); dirty.value = true }

async function save() {
	const sequence = ++actionSequence
	const requestedDocumentName = props.documentName
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value?.name
	const expectedModified = record.value?.modified
	const request = { ...form, inputs: clone(inputs.value), outputs: clone(outputs.value) }
	acting.value = "save"; error.value = ""
	try {
		const saved = await saveCutBundle(request, { name: requestedRecord, expectedModified })
		if (actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) return
		applyRecord(saved); emit("changed", saved)
	} catch (reason) {
		if (!actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) error.value = reason.message || "Unable to save the Cut Bundle Edit."
	} finally {
		if (!actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) acting.value = ""
	}
}

function requestCommand(command) { pendingCommand.value = command; confirmationVisible.value = true }
function requestClose() { if (busy.value) return; if (dirty.value) requestCommand("close"); else emit("update:visible", false) }
function visibilityChanged(value) { if (value) emit("update:visible", true); else requestClose() }
async function confirmCommand() {
	const command = pendingCommand.value
	if (command === "close") { dirty.value = false; confirmationVisible.value = false; pendingCommand.value = ""; emit("update:visible", false); return }
	const sequence = ++actionSequence
	const requestedDocumentName = props.documentName
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value?.name
	const expectedModified = record.value?.modified
	acting.value = command; error.value = ""; confirmationVisible.value = false
	try {
		const changed = await executeCutBundleCommand(requestedRecord, command, expectedModified)
		if (actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) return
		applyRecord(changed); emit("changed", changed)
	} catch (reason) {
		if (!actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) error.value = reason.message || `Unable to ${command} the Cut Bundle Edit.`
	} finally {
		if (!actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) { acting.value = ""; pendingCommand.value = "" }
	}
}

async function printLabels(printer) {
	const sequence = ++actionSequence
	const requestedDocumentName = props.documentName
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value?.name
	acting.value = "print"; error.value = ""; let labelsSent = false
	try {
		const printData = await getCutBundlePrintData(requestedRecord, printer)
		if (actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) return
		await printQzRaw(printer, printData.zpl)
		labelsSent = true
		const changed = await confirmCutBundlePrint(requestedRecord, printData.expected_modified, printData.confirmation_token)
		if (actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) return
		applyRecord(changed); printerVisible.value = false; emit("changed", changed)
	} catch (reason) {
		if (!actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) { printerVisible.value = false; error.value = labelsSent ? "Labels were sent to the printer, but the document status could not be updated. Do not print again; reopen this document and verify Printed Time." : reason.message || "Labels were not printed." }
	} finally {
		if (!actionIsStale(sequence, requestedDocumentName, requestedLoadSequence)) acting.value = ""
	}
}

function applyRecord(value) { editor.record = value; inputs.value = clone(value?.inputs || inputs.value); outputs.value = clone(value?.outputs || outputs.value); Object.assign(form, value || {}); form.selected_colour = value?.colour || form.selected_colour; dirty.value = false }
function flattenAvailable(value) {
	const rows = []
	const panels = value?.panels || []
	for (const [colour, detail] of Object.entries(value?.data || {})) {
		const groupPanels = Array.isArray(panels) ? panels : panels[detail?.part] || []
		for (const source of detail?.data || []) for (const panel of groupPanels) {
			const qty = Number(source?.[panel] || 0); if (qty <= 0) continue
			const row = { lay_no: source.lay_no, bundle_no: source.bundle_no, qty, panel, set_combination: clone(source.set_combination || {}), shade: source.shade || "", size: scalar(source.size), colour: scalar(source[`${panel}_colour`]) || scalar(colour), is_collapsed: false }
			rows.push({ ...row, key: bundleKey(row) })
		}
	}
	for (const source of value?.collapsed_details || []) {
		const row = { lay_no: source.lay_no, bundle_no: source.bundle_no, qty: Number(source.quantity || 0), panel: scalar(source.panel), set_combination: clone(source.set_combination || {}), shade: source.shade || "", size: scalar(source.size), colour: scalar(source.colour), is_collapsed: true }
		if (row.qty > 0) rows.push({ ...row, key: bundleKey(row) })
	}
	return rows
}
function scalar(value) { return value && typeof value === "object" ? value.value || value.name || value.label || "" : value || "" }
function bundleKey(row) { return [row.lay_no, row.bundle_no, row.size, row.colour, row.panel, row.shade, row.is_collapsed ? 1 : 0, stableJson(row.set_combination || {})].join("|") }
function stableJson(value) { if (!value || typeof value !== "object") return String(value || ""); return JSON.stringify(Object.keys(value).sort().reduce((result, key) => ({ ...result, [key]: value[key] }), {})) }
function clone(value) { return JSON.parse(JSON.stringify(value || [])) }
function totalQty(rows) { return (rows || []).reduce((sum, row) => sum + Number(row.qty || 0) * Math.max(1, String(row.panel || "").split(",").filter(Boolean).length), 0) }
function formatNumber(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function documentDeleted() {
	emit("update:visible", false)
	emit("changed")
}
</script>

<style scoped>
.cut-bundle-dialog__loading,.cut-bundle-dialog__body{display:grid;gap:12px}.cut-bundle-document-card,.cut-bundle-source-card,.cut-bundle-table-card{overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.cut-bundle-document-card>header,.cut-bundle-source-card>header,.cut-bundle-table-card>header{display:flex;align-items:center;gap:9px;padding:10px 12px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.cut-bundle-document-card>header span,.cut-bundle-source-card>header span,.cut-bundle-table-card>header span{color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:800;letter-spacing:.08em}.cut-bundle-document-card h3,.cut-bundle-source-card h3,.cut-bundle-table-card h3{margin:0;color:var(--erp-text);font-size:.95rem}.cut-bundle-document-card>header em,.cut-bundle-source-card>header>strong,.cut-bundle-table-card>header>strong{margin-left:auto;color:var(--erp-text-muted);font-size:var(--erp-font-size-caption);font-style:normal}.cut-bundle-source-card>header>div,.cut-bundle-table-card>header>div{display:flex;align-items:center;gap:9px}.cut-bundle-document-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));align-items:end;gap:12px;padding:12px}.cut-bundle-context,.cut-bundle-select{display:grid;gap:7px}.cut-bundle-context span,.cut-bundle-select>span{color:var(--erp-text);font-size:var(--erp-font-size-caption);font-weight:700}.cut-bundle-context strong{display:block;min-height:auto;padding:2px 0 7px;border:0;border-bottom:1px solid var(--erp-border);border-radius:0;background:transparent;color:var(--erp-text);font-size:13px;font-weight:750}.cut-bundle-source-card footer{display:flex;justify-content:flex-end;padding:9px 12px;border-top:1px solid var(--erp-border)}.cut-bundle-comparison{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.cut-bundle-table-scroll{max-width:100%;overflow:auto}.cut-bundle-table-scroll table{width:100%;min-width:720px;border-collapse:collapse}.cut-bundle-table-scroll th{padding:var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x);border-bottom:1px solid var(--erp-border);background:var(--erp-surface-muted);color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-align:left;text-transform:uppercase}.cut-bundle-table-scroll td{padding:var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x);border-bottom:1px solid var(--erp-border-subtle);color:var(--erp-text-secondary);font-size:var(--erp-font-size-table)}.cut-bundle-table-scroll tbody tr:last-child td{border-bottom:0}.cut-bundle-table-scroll input[type='text'],.cut-bundle-table-scroll input[type='number']{width:100%;min-width:72px;padding:6px 7px;border:1px solid var(--erp-border);border-radius:6px;color:var(--erp-text);background:var(--erp-surface)}.cut-bundle-empty{padding:38px;border:1px dashed var(--erp-border-strong);border-radius:var(--erp-panel-radius);color:var(--erp-text-muted);text-align:center}.cut-bundle-dialog__footer{display:flex;align-items:center;justify-content:space-between;gap:14px;width:100%}.cut-bundle-dialog__footer>span{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption)}.cut-bundle-dialog__footer>div{display:flex;gap:8px}
.cut-bundle-check{display:grid;min-width:44px;height:44px;place-items:center}.cut-bundle-check input{width:18px;height:18px;margin:0;accent-color:var(--erp-accent)}.cut-bundle-pick{width:36px;padding-inline:0!important;text-align:center}.cut-bundle-pick__box{width:15px;height:15px;margin:0;vertical-align:middle;accent-color:var(--erp-accent);cursor:pointer}.cut-bundle-pick__box:disabled{cursor:not-allowed;opacity:.45}.cut-bundle-selection{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:6px 12px;border-top:1px solid var(--erp-border);color:var(--erp-text-muted);font-size:var(--erp-font-size-caption)}.cut-bundle-table-actions{display:flex;align-items:center;gap:7px;margin-left:auto}.cut-bundle-table-actions strong{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption);font-weight:700}.cut-bundle-table-actions button{display:inline-flex;align-items:center;min-height:36px;gap:5px;padding:5px 8px;border:1px solid var(--erp-border);border-radius:6px;background:var(--erp-surface);color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:750;cursor:pointer}.cut-bundle-table-actions button:hover{border-color:var(--erp-accent);background:var(--erp-accent-soft)}
@media(max-width:1050px),(pointer:coarse){.cut-bundle-document-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cut-bundle-comparison{grid-template-columns:1fr}.cut-bundle-table-actions button,.cut-bundle-document-grid>:deep(.p-button),.cut-bundle-source-card footer :deep(.p-button){min-height:44px}}
@media(max-width:600px){.cut-bundle-document-grid{grid-template-columns:1fr}.cut-bundle-dialog__footer{align-items:stretch;flex-direction:column}.cut-bundle-dialog__footer>div{justify-content:flex-end;flex-wrap:wrap}}
</style>
