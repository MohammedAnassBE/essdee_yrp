<template>
	<Dialog
		:visible="visible"
		modal
		maximizable
		:dismissable-mask="false"
		:closable="!closeLocked"
		:close-on-escape="!closeLocked"
		:header="record?.name ? `Box Sticker Print · ${record.name}` : 'New Box Sticker Print'"
		class="box-sticker-print-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="visibilityChanged"
	>
		<div v-if="loading" class="box-sticker-dialog__loading">
			<Skeleton v-for="index in 7" :key="index" height="3rem" />
		</div>

		<div v-else class="box-sticker-dialog__body">
			<section class="box-sticker-document" aria-label="Box Sticker Print details">
				<header class="box-sticker-section-head">
					<div><h3>Box Sticker Print</h3></div>
					<DocumentStatusBadge :docstatus="record?.docstatus" :label="record?.status || 'Draft'" />
				</header>
				<div class="box-sticker-document__grid">
					<LinkField
						:key="`lot-${sourceFieldKey}`"
						:model-value="form.lot"
						label="Lot"
						doctype="SD YRP Lot"
						placeholder="Search Lot…"
						required
						:disabled="!canEdit || busy"
						@update:model-value="requestSourceChange('lot', $event)"
					/>
					<LinkField
						:key="`fg-item-${sourceFieldKey}`"
						:model-value="form.fg_item"
						label="Item"
						doctype="SD YRP FG Item Master"
						placeholder="Search Item…"
						required
						:filters="{ is_temp_item: 0, disabled: 0 }"
						:disabled="!canEdit || busy"
						@update:model-value="requestSourceChange('fg_item', $event)"
					/>
					<div class="common-field box-sticker-field">
						<label class="common-field__label erp-field-label" for="box-sticker-size">Size</label>
						<InputText id="box-sticker-size" v-model="form.size" fluid :disabled="!canEdit || busy" @update:model-value="markDirty" />
					</div>
					<LinkField
						v-model="form.print_format"
						label="Print Format"
						doctype="YRP ZPL Raw Print Format"
						placeholder="Search Print Format…"
						required
						:disabled="!canEdit || busy"
						@update:model-value="documentValueChanged"
					/>
					<label class="box-sticker-check" for="box-sticker-use-item-name">
						<Checkbox
							v-model="form.use_item_name"
							binary
							:true-value="1"
							:false-value="0"
							input-id="box-sticker-use-item-name"
							:disabled="!canEdit || busy"
							@change="documentValueChanged"
						/>
						<span><strong>Use Item Name</strong><small>Print the item name instead of its display name.</small></span>
					</label>
					<div class="common-field box-sticker-context">
						<span class="common-field__label erp-field-label">Display Name</span>
						<strong>{{ displayName }}</strong>
					</div>
					<Button
						v-if="canEdit"
						label="Fetch Size Rows"
						icon="pi pi-refresh"
						severity="secondary"
						outlined
						:loading="acting === 'source'"
						:disabled="!form.lot || !form.fg_item || busy"
						@click="requestRowsRefresh"
					/>
				</div>
			</section>

			<section class="box-sticker-rows" aria-label="Box Sticker size rows">
				<header class="box-sticker-section-head">
					<div><h3>Box Sticker Print Details</h3></div>
					<strong>{{ rows.length }} {{ rows.length === 1 ? "size" : "sizes" }}</strong>
				</header>

				<div v-if="rows.length" ref="tableWrap" class="box-sticker-table-wrap" tabindex="0" role="region" aria-label="Box Sticker quantities">
					<table>
						<thead>
							<tr>
								<th>Size</th>
								<th>MRP</th>
								<th>Quantity</th>
								<th>Printed Quantity</th>
								<th>Allow Excess Quantity</th>
								<th>Allow Excess Percentage</th>
								<th>Allowed</th>
								<th>Remaining</th>
								<th :class="{ 'box-sticker-print-column': canPrint }">Print Quantity</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, index) in rows" :key="row.name || `${row.size}-${index}`">
								<td><strong>{{ row.size || "Not set" }}</strong></td>
								<td class="box-sticker-number-cell"><span>{{ money(row.mrp) }}</span></td>
								<td class="box-sticker-number-cell">
									<InputNumber
										v-if="canEdit"
										v-model="row.quantity"
										:min="0"
										:max-fraction-digits="0"
										:use-grouping="false"
										:disabled="busy"
										:aria-label="`Total quantity for ${row.size || `row ${index + 1}`}`"
										fluid
										@update:model-value="markDirty"
									/>
									<span v-else>{{ number(row.quantity) }}</span>
								</td>
								<td class="box-sticker-number-cell"><span>{{ number(row.printed_quantity) }}</span></td>
								<td class="box-sticker-excess-cell">
									<Checkbox v-model="row.allow_excess_quantity" binary :true-value="1" :false-value="0" disabled :aria-label="`Allow excess for ${row.size || `row ${index + 1}`}`" />
								</td>
								<td class="box-sticker-number-cell">
									<InputNumber
										v-if="canEdit"
										v-model="row.allow_excess_percentage"
										suffix="%"
										:min="0"
										:max="100"
										:max-fraction-digits="0"
										:use-grouping="false"
										:disabled="busy || Boolean(row.allow_excess_quantity)"
										:aria-label="`Excess percentage for ${row.size || `row ${index + 1}`}`"
										fluid
										@update:model-value="markDirty"
									/>
									<span v-else>{{ number(row.allow_excess_percentage) }}%</span>
								</td>
								<td class="box-sticker-number-cell"><span>{{ authoritativeNumber(row.allowed_quantity) }}</span></td>
								<td class="box-sticker-number-cell"><span>{{ authoritativeNumber(row.remaining_quantity) }}</span></td>
								<td class="box-sticker-print-quantity">
									<InputNumber
										v-model="row.print_quantity"
										:min="0"
										:max-fraction-digits="0"
										:use-grouping="false"
										:disabled="!canPrint || busy"
										:aria-label="`Print quantity for ${row.size || `row ${index + 1}`}`"
										fluid
										@update:model-value="printHint = ''"
									/>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-else class="box-sticker-empty">
					<i class="pi pi-tags" aria-hidden="true" />
					<strong>No size rows loaded</strong>
					<span>Select a Lot and Item to load the size rows.</span>
				</div>
			</section>

			<section class="box-sticker-preview" aria-label="Label preview">
				<header class="box-sticker-section-head">
					<div><h3>Preview</h3></div>
					<Button
						v-if="record?.name"
						icon="pi pi-refresh"
						severity="secondary"
						text
						rounded
						aria-label="Refresh label preview"
						:loading="previewLoading"
						:disabled="dirty || busy"
						@click="loadPreview"
					/>
				</header>
				<div class="box-sticker-preview__canvas">
					<Skeleton v-if="previewLoading" width="320px" height="180px" />
					<img v-else-if="previewUrl" :src="previewUrl" :alt="`Label preview for ${record?.name || 'Box Sticker Print'}`" @error="previewImageFailed" />
					<div v-else-if="previewError" class="box-sticker-preview__message box-sticker-preview__message--error" role="status">
						<i class="pi pi-image" aria-hidden="true" /><strong>Preview unavailable</strong><span>{{ previewError }}</span>
					</div>
					<div v-else class="box-sticker-preview__message">
						<i class="pi pi-image" aria-hidden="true" /><strong>{{ previewEmptyTitle }}</strong><span>{{ previewEmptyMessage }}</span>
					</div>
				</div>
				<footer v-if="record?.name && dirty"><i class="pi pi-info-circle" /> Save changes to refresh this preview.</footer>
			</section>
		</div>

		<template #footer>
			<div class="box-sticker-dialog__footer">
				<span :class="{ 'box-sticker-print-hint': printHint }" role="status">{{ printHint || footerSummary }}</span>
				<div>
					<Button label="Close" severity="secondary" text :disabled="busy" @click="requestClose" />
					<Button
						v-if="['reserving', 'reserved'].includes(pendingPrintConfirmation?.phase)"
						label="Resume Print"
						icon="pi pi-refresh"
						severity="warn"
						outlined
						:loading="acting === 'recover-print'"
						:disabled="busy"
						@click="resumePendingPrint"
					/>
					<Button
						v-if="pendingPrintConfirmation?.phase === 'printing'"
						label="Confirm Printed"
						icon="pi pi-check"
						severity="warn"
						outlined
						:loading="acting === 'confirm-print'"
						:disabled="busy"
						@click="requestCommand('confirm-print')"
					/>
					<Button
						v-if="pendingPrintConfirmation?.phase === 'confirming'"
						label="Retry Confirmation"
						icon="pi pi-refresh"
						severity="warn"
						outlined
						:loading="acting === 'confirm-print'"
						:disabled="busy"
						@click="retryPrintConfirmation"
					/>
					<Button
						v-if="pendingPrintConfirmation?.phase === 'rollback'"
						label="Retry Rollback"
						icon="pi pi-undo"
						severity="danger"
						outlined
						:loading="acting === 'rollback-print'"
						:disabled="busy"
						@click="retryPrintRollback"
					/>
					<Button
						v-if="pendingPrintConfirmation && pendingPrintConfirmation.phase !== 'confirming' && pendingPrintConfirmation.phase !== 'rollback'"
						label="Release Reservation"
						icon="pi pi-times"
						severity="secondary"
						outlined
						:disabled="busy"
						@click="requestCommand('release-print')"
					/>
					<Button
						v-if="canPrint"
						label="Print Labels"
						icon="pi pi-print"
						severity="secondary"
						outlined
						:disabled="busy"
						@click="startPrint"
					/>
					<Button v-if="documentPermissions.can_cancel" label="Cancel Document" icon="pi pi-ban" severity="danger" outlined :disabled="busy || Boolean(pendingPrintConfirmation)" @click="requestCommand('cancel')" />
					<Button v-if="documentPermissions.can_submit" label="Submit" icon="pi pi-check" severity="secondary" outlined :disabled="busy || dirty || !rows.length" @click="requestCommand('submit')" />
					<Button v-if="canEdit" label="Save" icon="pi pi-save" :loading="acting === 'save'" :disabled="busy || !canSave" @click="save" />
				</div>
			</div>
		</template>
	</Dialog>

	<PrinterDialog
		v-model:visible="printerVisible"
		:busy="acting === 'print'"
		show-resolution
		:resolutions="resolutionOptions"
		:filter-printers="configuredPrinters"
		@confirm="printLabels"
		@error="printerLoadFailed"
	/>

	<DocumentConfirmationDialog
		v-model:visible="confirmationVisible"
		:title="confirmationTitle"
		:message="confirmationMessage"
		:confirm-label="confirmationLabel"
		:cancel-label="confirmationCancelLabel"
		:severity="confirmationSeverity"
		:busy="acting === pendingAction"
		@confirm="confirmAction"
	/>

	<DocumentErrorDialog :message="error" title="Box Sticker Print action failed" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Skeleton from "primevue/skeleton"
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue"

import {
	confirmBoxStickerPrint,
	executeBoxStickerCommand,
	getBoxStickerEditor,
	getBoxStickerPrintRecovery,
	getBoxStickerPreview,
	getConfiguredBoxStickerPrinters,
	previewBoxStickerSource,
	reserveBoxStickerPrint,
	rollbackBoxStickerPrint,
	saveBoxSticker,
} from "../../api/cutPanelStore.js"
import { printQzRaw } from "../../api/qzPrinter.js"
import LinkField from "../../components/common/LinkField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import PrinterDialog from "./PrinterDialog.vue"

const props = defineProps({
	visible: Boolean,
	documentName: { type: String, default: "" },
})

const emit = defineEmits(["update:visible", "changed"])

const emptyForm = () => ({ lot: "", fg_item: "", size: "", use_item_name: 0, print_format: "" })
const editor = reactive({ context: {}, permissions: {}, choices: {}, record: null })
const form = reactive(emptyForm())
const rows = ref([])
const loading = ref(false)
const acting = ref("")
const error = ref("")
const dirty = ref(false)
const printerVisible = ref(false)
const confirmationVisible = ref(false)
const pendingAction = ref("")
const pendingSource = ref(null)
const previewLoading = ref(false)
const previewUrl = ref("")
const previewError = ref("")
const pendingPrintConfirmation = ref(null)
const sourceFieldKey = ref(0)
const printHint = ref("")
const tableWrap = ref(null)
let previewObjectUrl = ""
let loadSequence = 0
let sourceSequence = 0
let previewSequence = 0
let previewAbortController = null
let printIntentKey = ""
let printRequestId = ""

const record = computed(() => editor.record)
const busy = computed(() => Boolean(acting.value))
const closeLocked = computed(() => busy.value || printerVisible.value || confirmationVisible.value || Boolean(error.value))
const documentPermissions = computed(() => record.value?.permissions || editor.permissions || {})
const canEdit = computed(() => Number(record.value?.docstatus || 0) === 0 && (record.value ? Boolean(documentPermissions.value.can_write) : Boolean(editor.permissions?.can_create)))
const canPrint = computed(() => Number(record.value?.docstatus) === 1 && Boolean(documentPermissions.value.can_print) && !pendingPrintConfirmation.value)
const canSave = computed(() => Boolean(form.lot && form.fg_item && form.print_format && rows.value.length))
const positivePrintRows = computed(() => rows.value.filter((row) => positiveInteger(row.print_quantity) > 0))
const hasPositivePrintQuantity = computed(() => positivePrintRows.value.length > 0)
const hasUnsavedValues = computed(() => dirty.value || hasPositivePrintQuantity.value)
const displayName = computed(() => {
	if (record.value?.fg_item === form.fg_item && record.value?.display_name) return record.value.display_name
	return editor.context?.display_name || "Derived from FG Item"
})
const resolutionOptions = computed(() => editor.choices?.printer_types?.length ? editor.choices.printer_types : ["200dpi", "300dpi"])
const footerSummary = computed(() => {
	if (pendingPrintConfirmation.value) {
		return ({
			reserving: "Print reservation interrupted · recovery required",
			reserved: "Labels reserved · ready to resume",
			printing: "Printer result unknown · choose Confirm Printed or Release Reservation",
			confirming: "Labels sent · server confirmation pending",
			rollback: "Labels not printed · quantity rollback pending",
		})[pendingPrintConfirmation.value.phase] || "Print recovery required"
	}
	const total = rows.value.reduce((sum, row) => sum + Number(row.quantity || 0), 0)
	const printed = rows.value.reduce((sum, row) => sum + Number(row.printed_quantity || 0), 0)
	const requested = positivePrintRows.value.reduce((sum, row) => sum + positiveInteger(row.print_quantity), 0)
	return requested > 0 ? `Total ${number(total)} · Printed ${number(printed)} · Requested ${number(requested)}` : `Total ${number(total)} · Printed ${number(printed)}`
})
const previewEmptyTitle = computed(() => record.value?.name ? "No preview generated" : "Save to generate preview")
const previewEmptyMessage = computed(() => record.value?.name ? "Refresh after choosing a valid print format." : "The server renders a preview after the document is saved.")
const confirmationTitle = computed(() => ({ close: "Discard unsaved changes?", "replace-source": "Replace size rows?", "replace-rows": "Refresh size rows?", cancel: "Cancel Box Sticker Print?", submit: "Submit Box Sticker Print?", "confirm-print": "Were the labels printed?", "release-print": "Were the labels not printed?" })[pendingAction.value] || "Confirm action")
const confirmationMessage = computed(() => ({ close: "Your unsaved document and print quantities will be lost.", "replace-source": "Changing the source reloads the authoritative size rows and discards current row edits.", "replace-rows": "Refreshing reloads the authoritative size rows and discards current row edits.", cancel: `Cancel ${record.value?.name || "this Box Sticker Print"}?`, submit: `Submit ${record.value?.name || "this Box Sticker Print"}? Quantities will be checked again.`, "confirm-print": "Confirm only if the printer produced these labels. This makes the reserved printed quantities permanent and cannot be undone.", "release-print": "Release only if the printer did not produce these labels. This restores the reserved printed quantities so they can be printed later." })[pendingAction.value] || "Continue with this action?")
const confirmationLabel = computed(() => ({ close: "Discard Changes", "replace-source": "Replace Rows", "replace-rows": "Refresh Rows", cancel: "Cancel Document", submit: "Submit", "confirm-print": "Yes, Labels Printed", "release-print": "No, Release Reservation" })[pendingAction.value] || "Continue")
const confirmationCancelLabel = computed(() => ["confirm-print", "release-print"].includes(pendingAction.value) ? "Go Back" : "Keep Document")
const confirmationSeverity = computed(() => pendingAction.value === "submit" || pendingAction.value === "confirm-print" ? "success" : "danger")

watch(() => [props.visible, props.documentName], ([visible]) => {
	if (visible) load()
	else {
		loadSequence += 1
		loading.value = false
		previewLoading.value = false
		resetEditorState()
	}
})

watch(confirmationVisible, (visible) => {
	if (visible || pendingAction.value !== "replace-source") return
	pendingSource.value = null
	pendingAction.value = ""
	sourceFieldKey.value += 1
})

onBeforeUnmount(revokePreviewUrl)

async function load() {
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	resetEditorState()
	try {
		const payload = await getBoxStickerEditor(props.documentName)
		if (sequence !== loadSequence || !props.visible) return
		applyEditorPayload(payload)
		if (record.value?.name) void loadPreview()
	} catch (reason) {
		if (sequence !== loadSequence || !props.visible) return
		error.value = messageOf(reason, "Unable to load the Box Sticker Print.")
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function resetEditorState() {
	previewSequence += 1
	sourceSequence += 1
	if (acting.value === "source") acting.value = ""
	printHint.value = ""
	previewAbortController?.abort()
	previewAbortController = null
	revokePreviewUrl()
	editor.context = {}
	editor.permissions = {}
	editor.choices = {}
	editor.record = null
	setForm()
	rows.value = []
	dirty.value = false
	previewError.value = ""
	pendingPrintConfirmation.value = null
}

function applyEditorPayload(payload = {}) {
	revokePreviewUrl()
	editor.context = { ...(payload.context || {}) }
	editor.permissions = { ...(payload.permissions || {}) }
	editor.choices = { ...(payload.choices || {}) }
	editor.record = payload.record ? clone(payload.record) : null
	const source = payload.record || payload.defaults || {}
	setForm(source)
	rows.value = normaliseRows(source.rows || [])
	dirty.value = false
	previewError.value = ""
	restorePendingPrintConfirmation(payload.record?.name || "")
}

function applyRecordPayload(payload) {
	const changed = payload?.record || payload
	if (!changed?.name) return false
	editor.record = clone(changed)
	editor.context = { ...editor.context, display_name: changed.display_name || changed.fg_item }
	setForm(changed)
	rows.value = normaliseRows(changed.rows || [])
	dirty.value = false
	return true
}

function requestSourceChange(field, value) {
	if (form[field] === value) return
	const change = { field, value: value || "" }
	if (rows.value.length) {
		pendingSource.value = change
		pendingAction.value = "replace-source"
		confirmationVisible.value = true
		return
	}
	applySourceChange(change)
}

async function applySourceChange(change) {
	if (!change) return
	form[change.field] = change.value
	if (change.field === "fg_item") delete editor.context.display_name
	rows.value = []
	dirty.value = true
	revokePreviewUrl()
	previewError.value = ""
	if (form.lot && form.fg_item) await loadSourceRows()
}

function requestRowsRefresh() {
	if (rows.value.length && dirty.value) {
		pendingAction.value = "replace-rows"
		confirmationVisible.value = true
		return
	}
	loadSourceRows()
}

async function loadSourceRows() {
	if (!form.lot || !form.fg_item) return
	const sequence = ++sourceSequence
	acting.value = "source"
	error.value = ""
	revokePreviewUrl()
	try {
		const payload = await previewBoxStickerSource(form.lot, form.fg_item, sourcePreviewValues(), record.value?.name || "")
		if (sequence !== sourceSequence) return
		editor.context = { ...editor.context, ...(payload?.context || {}) }
		editor.choices = { ...editor.choices, ...(payload?.choices || {}) }
		rows.value = normaliseRows(payload?.rows || [])
		dirty.value = true
	} catch (reason) {
		if (sequence === sourceSequence) error.value = messageOf(reason, "Unable to load the authoritative size rows.")
	} finally {
		if (sequence === sourceSequence) acting.value = ""
	}
}

function documentValueChanged() {
	markDirty()
	revokePreviewUrl()
}

function markDirty() {
	dirty.value = true
}

function documentValues() {
	return {
		lot: form.lot,
		fg_item: form.fg_item,
		size: form.size,
		print_format: form.print_format,
		use_item_name: form.use_item_name ? 1 : 0,
		rows: editableRows(),
	}
}

function sourcePreviewValues() {
	const values = {
		lot: form.lot,
		fg_item: form.fg_item,
		size: form.size,
		print_format: form.print_format,
		use_item_name: form.use_item_name ? 1 : 0,
	}
	if (rows.value.length) values.rows = editableRows()
	return values
}

function setForm(source = {}) {
	for (const key of Object.keys(form)) delete form[key]
	Object.assign(form, emptyForm(), {
		lot: source.lot || "",
		fg_item: source.fg_item || "",
		size: source.size || "",
		use_item_name: source.use_item_name ? 1 : 0,
		print_format: source.print_format || "",
	})
}

function editableRows() {
	return rows.value.map((row) => ({
		name: row.name || undefined,
		size: row.size,
		quantity: Number(row.quantity || 0),
		allow_excess_percentage: Number(row.allow_excess_percentage || 0),
	}))
}

async function save() {
	acting.value = "save"
	error.value = ""
	try {
		const saved = await saveBoxSticker(documentValues(), {
			name: record.value?.name,
			expectedModified: record.value?.modified,
		})
		applyRecordPayload(saved)
		void loadPreview()
		emit("changed", editor.record)
	} catch (reason) {
		error.value = messageOf(reason, "Unable to save the Box Sticker Print.")
	} finally {
		acting.value = ""
	}
}

function requestCommand(command) {
	pendingAction.value = command
	confirmationVisible.value = true
}

function requestClose() {
	if (closeLocked.value) return
	if (hasUnsavedValues.value) requestCommand("close")
	else emit("update:visible", false)
}

function visibilityChanged(value) {
	if (value) emit("update:visible", true)
	else requestClose()
}

async function confirmAction() {
	const action = pendingAction.value
	confirmationVisible.value = false
	if (action === "close") {
		dirty.value = false
		rows.value.forEach((row) => { row.print_quantity = 0 })
		pendingAction.value = ""
		emit("update:visible", false)
		return
	}
	if (action === "replace-source") {
		const change = pendingSource.value
		pendingSource.value = null
		pendingAction.value = ""
		await applySourceChange(change)
		return
	}
	if (action === "replace-rows") {
		pendingAction.value = ""
		await loadSourceRows()
		return
	}
	if (action === "confirm-print") {
		try { await retryPrintConfirmation() } finally { pendingAction.value = "" }
		return
	}
	if (action === "release-print") {
		try { await releasePendingPrint() } finally { pendingAction.value = "" }
		return
	}
	acting.value = action
	error.value = ""
	try {
		const changed = await executeBoxStickerCommand(record.value.name, action, record.value.modified)
		applyRecordPayload(changed)
		void loadPreview()
		emit("changed", editor.record)
	} catch (reason) {
		error.value = messageOf(reason, `Unable to ${action} the Box Sticker Print.`)
	} finally {
		acting.value = ""
		pendingAction.value = ""
	}
}

async function startPrint() {
	if (hasPositivePrintQuantity.value) {
		printHint.value = ""
		printerVisible.value = true
		return
	}
	printHint.value = "Enter Print Quantity for at least one size"
	await nextTick()
	tableWrap.value?.querySelector(".box-sticker-print-quantity input")?.focus()
}

async function configuredPrinters(detected) {
	return getConfiguredBoxStickerPrinters(detected)
}

function printerLoadFailed(message) {
	printerVisible.value = false
	error.value = message || "Unable to load configured label printers."
}

async function printLabels(selection) {
	const printRows = positivePrintRows.value.map((row) => ({ doc_name: row.name, quantity: positiveInteger(row.print_quantity) }))
	if (!selection?.printer || !selection?.printerType || !printRows.length) {
		printerVisible.value = false
		error.value = "Choose a configured printer and resolution, then enter at least one positive print quantity."
		return
	}

	acting.value = "print"
	error.value = ""
	const requestId = requestIdForPrintIntent(printRows, selection.printerType)
	rememberPendingPrintConfirmation({
		document: record.value.name,
		requestId,
		phase: "reserving",
		rows: printRows,
		printer: selection.printer,
		printerType: selection.printerType,
		expectedModified: record.value.modified,
		reservation: "",
	})

	try {
		const reserved = await reserveBoxStickerPrint(record.value.name, printRows, selection.printerType, requestId, record.value.modified)
		const reservation = reserved?.reservation ?? reserved?.reservation_id
		const zpl = reserved?.zpl || reserved?.raw
		if (!reservation || !zpl) throw new Error("The server did not return a valid print reservation.")
		updatePendingPrintConfirmation({ phase: "reserved", reservation })
		printerVisible.value = false
		await sendReservedLabels(zpl)
	} catch (reason) {
		printerVisible.value = false
		error.value = `The reservation result is uncertain. Use Resume Print to recover this request safely; it will reuse the same request ID.\n${messageOf(reason, "The reservation could not be completed.")}`
	} finally {
		acting.value = ""
	}
}

async function sendReservedLabels(zpl) {
	const pending = pendingPrintConfirmation.value
	if (!pending?.reservation || !zpl) return
	updatePendingPrintConfirmation({ phase: "printing" })
	try {
		await printQzRaw(pending.printer, zpl)
	} catch (reason) {
		updatePendingPrintConfirmation({ phase: "rollback" })
		try {
			await performPrintRollback()
			error.value = `${messageOf(reason, "Labels were not printed.")}\nReserved printed quantities were restored.`
		} catch (rollbackReason) {
			error.value = `${messageOf(reason, "Labels were not printed.")}\nThe quantity rollback is still pending. Use Retry Rollback before printing again.\n${messageOf(rollbackReason, "Rollback failed.")}`
		}
		return
	}
	updatePendingPrintConfirmation({ phase: "confirming" })
	try {
		await finishPrintConfirmation()
	} catch (reason) {
		try { await refreshAuthoritativeRecord() } catch { /* keep confirmation failure primary */ }
		error.value = `Labels were sent to the printer, but the server confirmation did not finish. Use Retry Confirmation; it will not print the labels again.\n${messageOf(reason, "Confirmation failed.")}`
	}
}

async function retryPrintConfirmation() {
	const pending = pendingPrintConfirmation.value
	if (!pending?.reservation) return
	acting.value = "confirm-print"
	error.value = ""
	try {
		updatePendingPrintConfirmation({ phase: "confirming" })
		await finishPrintConfirmation()
	} catch (reason) {
		try { await refreshAuthoritativeRecord() } catch { /* keep confirmation failure primary */ }
		error.value = `The labels were already sent to the printer, but server confirmation is still pending. Retry Confirmation again; do not print another copy.\n${messageOf(reason, "Confirmation failed.")}`
	} finally {
		acting.value = ""
	}
}

async function finishPrintConfirmation() {
	const pending = pendingPrintConfirmation.value
	const confirmed = await confirmBoxStickerPrint(pending.reservation)
	clearPendingPrintConfirmation()
	clearPrintRequestId(pending.requestId)
	if (!applyRecordPayload(confirmed)) await refreshAuthoritativeRecord()
	void loadPreview()
	emit("changed", editor.record)
}

async function resumePendingPrint() {
	const pending = pendingPrintConfirmation.value
	if (!pending?.requestId || !pending?.rows?.length) return
	acting.value = "recover-print"
	error.value = ""
	try {
		let recovery = await getBoxStickerPrintRecovery(pending.requestId)
		if (recovery?.state === "Confirmed") {
			clearPendingPrintConfirmation()
			clearPrintRequestId(pending.requestId)
			if (!applyRecordPayload(recovery)) await refreshAuthoritativeRecord()
			emit("changed", editor.record)
			return
		}
		if (recovery?.state === "Rolled Back") {
			clearPendingPrintConfirmation()
			clearPrintRequestId(pending.requestId)
			if (!applyRecordPayload(recovery)) await refreshAuthoritativeRecord()
			return
		}
		if (recovery?.state === "Missing") {
			recovery = await reserveBoxStickerPrint(pending.document, pending.rows, pending.printerType, pending.requestId, pending.expectedModified)
		}
		if (recovery?.state === "Preparing") throw new Error("The print request is still being prepared. Retry shortly.")
		const reservation = recovery?.reservation ?? recovery?.reservation_id
		if (recovery?.state === "Active" && recovery?.can_resume === false) {
			updatePendingPrintConfirmation({ phase: "rollback", reservation })
			throw new Error("This document can no longer be printed. Use Retry Rollback to release its reserved quantities.")
		}
		const zpl = recovery?.zpl || recovery?.raw
		if (!reservation || !zpl) throw new Error("No active print reservation was found.")
		updatePendingPrintConfirmation({ phase: "reserved", reservation })
		await sendReservedLabels(zpl)
	} catch (reason) {
		error.value = `This print is still waiting for recovery. No new print was started.\n${messageOf(reason, "Recovery failed.")}`
	} finally {
		acting.value = ""
	}
}

async function retryPrintRollback() {
	acting.value = "rollback-print"
	error.value = ""
	try {
		await performPrintRollback()
	} catch (reason) {
		error.value = `The quantity rollback is still pending. Printing remains blocked.\n${messageOf(reason, "Rollback failed.")}`
	} finally {
		acting.value = ""
	}
}

async function releasePendingPrint() {
	const pending = pendingPrintConfirmation.value
	if (!pending?.requestId) return
	acting.value = "rollback-print"
	error.value = ""
	try {
		const recovery = await getBoxStickerPrintRecovery(pending.requestId)
		if (recovery?.state === "Missing" || recovery?.state === "Rolled Back") {
			clearPendingPrintConfirmation()
			clearPrintRequestId(pending.requestId)
			if (recovery?.record) applyRecordPayload(recovery)
			return
		}
		if (recovery?.state === "Confirmed") {
			clearPendingPrintConfirmation()
			clearPrintRequestId(pending.requestId)
			if (!applyRecordPayload(recovery)) await refreshAuthoritativeRecord()
			return
		}
		if (recovery?.state !== "Active") throw new Error("The reservation is still being prepared. Retry shortly.")
		updatePendingPrintConfirmation({ phase: "rollback", reservation: recovery.reservation || pending.requestId })
		await performPrintRollback()
	} catch (reason) {
		error.value = `The reservation could not be released. Printing remains blocked.\n${messageOf(reason, "Release failed.")}`
	} finally {
		acting.value = ""
	}
}

async function performPrintRollback() {
	const pending = pendingPrintConfirmation.value
	if (!pending?.reservation) throw new Error("Recover the reservation before retrying rollback.")
	const rolledBack = await rollbackBoxStickerPrint(pending.reservation)
	const requestedQuantities = new Map((pending.rows || []).map((row) => [row.doc_name, positiveInteger(row.quantity)]))
	clearPendingPrintConfirmation()
	clearPrintRequestId(pending.requestId)
	if (applyRecordPayload(rolledBack)) void loadPreview()
	else await refreshAuthoritativeRecord()
	restorePrintQuantities(requestedQuantities)
	emit("changed", editor.record)
}

function pendingConfirmationStorageKey(documentName) {
	return `essdee-yrp:box-sticker-confirmation:${documentName}`
}

function rememberPendingPrintConfirmation(value) {
	pendingPrintConfirmation.value = { ...value }
	try {
		window.sessionStorage.setItem(pendingConfirmationStorageKey(value.document), JSON.stringify(value))
	} catch { /* the in-memory recovery action remains available */ }
}

function updatePendingPrintConfirmation(values) {
	if (!pendingPrintConfirmation.value) return
	rememberPendingPrintConfirmation({ ...pendingPrintConfirmation.value, ...values })
}

function restorePendingPrintConfirmation(documentName) {
	pendingPrintConfirmation.value = null
	if (!documentName) return
	try {
		const raw = window.sessionStorage.getItem(pendingConfirmationStorageKey(documentName))
		if (!raw) return
		const saved = JSON.parse(raw)
		if (saved?.document === documentName && typeof saved.requestId === "string" && saved.requestId) {
			pendingPrintConfirmation.value = {
				...saved,
				phase: saved.phase || (saved.reservation ? "confirming" : "reserving"),
				rows: Array.isArray(saved.rows) ? saved.rows : [],
			}
			printRequestId = saved.requestId
		}
	} catch { /* ignore invalid or unavailable session storage */ }
}

function clearPendingPrintConfirmation() {
	const pending = pendingPrintConfirmation.value
	if (pending?.document) {
		try { window.sessionStorage.removeItem(pendingConfirmationStorageKey(pending.document)) } catch { /* storage may be unavailable */ }
	}
	pendingPrintConfirmation.value = null
}

function restorePrintQuantities(quantities) {
	for (const row of rows.value) row.print_quantity = quantities.get(row.name) || 0
}

async function refreshAuthoritativeRecord() {
	const payload = await getBoxStickerEditor(record.value?.name || props.documentName)
	applyEditorPayload(payload)
	if (record.value?.name) void loadPreview()
}

async function loadPreview() {
	if (!record.value?.name || dirty.value) return
	previewAbortController?.abort()
	const controller = new AbortController()
	previewAbortController = controller
	const sequence = ++previewSequence
	const documentName = record.value.name
	const timeout = window.setTimeout(() => controller.abort(), 10_000)
	previewLoading.value = true
	previewError.value = ""
	revokePreviewUrl()
	try {
		const payload = await getBoxStickerPreview(documentName)
		if (sequence !== previewSequence || record.value?.name !== documentName) return
		if (controller.signal.aborted) throw new DOMException("Preview timed out", "AbortError")
		const directUrl = payload?.image_url || payload?.preview_url || payload?.url || (typeof payload?.image === "string" ? payload.image : "")
		if (directUrl) {
			previewUrl.value = directUrl
			return
		}
		const zpl = payload?.code || payload?.zpl || payload?.raw
		if (!zpl) throw new Error("No preview output was returned.")
		const width = encodeURIComponent(payload?.width || 4)
		const height = encodeURIComponent(payload?.height || 6)
		const response = await fetch(`https://api.labelary.com/v1/printers/12dpmm/labels/${width}x${height}/0/`, {
			method: "POST",
			headers: { Accept: "image/png", "Content-Type": "application/x-www-form-urlencoded" },
			body: zpl,
			signal: controller.signal,
		})
		if (sequence !== previewSequence || record.value?.name !== documentName) return
		if (!response.ok) throw new Error(`Preview service returned HTTP ${response.status}.`)
		const blob = await response.blob()
		if (sequence !== previewSequence || record.value?.name !== documentName) return
		previewObjectUrl = URL.createObjectURL(blob)
		previewUrl.value = previewObjectUrl
	} catch (reason) {
		if (sequence !== previewSequence || record.value?.name !== documentName) return
		previewError.value = reason?.name === "AbortError" ? "The preview service timed out." : messageOf(reason, "The label preview could not be rendered.")
	} finally {
		window.clearTimeout(timeout)
		if (previewAbortController === controller) previewAbortController = null
		if (sequence === previewSequence) previewLoading.value = false
	}
}

function previewImageFailed() {
	revokePreviewUrl()
	previewError.value = "The preview image could not be displayed."
}

function revokePreviewUrl() {
	if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl)
	previewObjectUrl = ""
	previewUrl.value = ""
}

function normaliseRows(values) {
	return (values || []).map((row) => ({
		...clone(row),
		mrp: Number(row.mrp || 0),
		quantity: Number(row.quantity || 0),
		printed_quantity: Number(row.printed_quantity || 0),
		allow_excess_quantity: row.allow_excess_quantity ? 1 : 0,
		allow_excess_percentage: Number(row.allow_excess_percentage || 0),
		print_quantity: 0,
	}))
}

function positiveInteger(value) {
	const parsed = Math.floor(Number(value || 0))
	return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

function requestIdForPrintIntent(printRows, printerType) {
	const key = JSON.stringify({
		document: record.value?.name || "",
		expectedModified: record.value?.modified || "",
		printerType,
		rows: [...printRows].sort((left, right) => String(left.doc_name).localeCompare(String(right.doc_name))),
	})
	if (key !== printIntentKey || !printRequestId) {
		printIntentKey = key
		printRequestId = newPrintRequestId()
	}
	return printRequestId
}

function clearPrintRequestId(requestId) {
	if (requestId !== printRequestId) return
	printIntentKey = ""
	printRequestId = ""
}

function newPrintRequestId() {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID()
	return `box-sticker-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function authoritativeNumber(value) {
	return value === null || value === undefined || value === "" ? "Unlimited" : number(value)
}

function number(value) {
	return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

function money(value) {
	return Number(value || 0).toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 })
}

function messageOf(reason, fallback) {
	return reason?.message || String(reason || "") || fallback
}

function clone(value) {
	return JSON.parse(JSON.stringify(value))
}
</script>

<style scoped>
.box-sticker-dialog__loading,.box-sticker-dialog__body{display:grid;gap:12px}.box-sticker-document,.box-sticker-rows,.box-sticker-preview{min-width:0;overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.box-sticker-section-head{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:43px;padding:9px 12px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.box-sticker-section-head>div{display:flex;align-items:center;gap:9px;min-width:0}.box-sticker-section-head h3{margin:0;color:var(--erp-text);font-size:.95rem}.box-sticker-section-head>strong,.box-sticker-section-head>em{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption);font-style:normal}.box-sticker-document__status--1{color:var(--erp-accent-hover)!important}.box-sticker-document__status--2{color:var(--erp-danger)!important}.box-sticker-document__grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));align-items:end;gap:12px;padding:12px}.box-sticker-field,.box-sticker-context{display:grid;gap:7px}.box-sticker-context strong{display:block;min-height:auto;padding:2px 0 7px;border:0;border-bottom:1px solid var(--erp-border);border-radius:0;background:transparent;color:var(--erp-text);font-size:13px;font-weight:750}.box-sticker-check{display:flex;align-items:center;gap:9px;min-height:40px;padding:8px 10px;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface-soft);cursor:pointer}.box-sticker-check>span{display:grid;gap:2px}.box-sticker-check strong{color:var(--erp-text);font-size:var(--erp-font-size-caption)}.box-sticker-check small{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);line-height:1.3}.box-sticker-table-wrap{max-width:100%;overflow:auto}.box-sticker-table-wrap table{width:100%;min-width:900px;border-collapse:collapse}.box-sticker-table-wrap th{padding:8px 9px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-muted);color:var(--erp-text-muted);font-size:var(--erp-font-size-min);line-height:1.3;text-align:center;text-transform:uppercase;vertical-align:middle}.box-sticker-table-wrap th.box-sticker-print-column{background:color-mix(in srgb,var(--erp-accent) 14%,var(--erp-surface-muted));color:var(--erp-accent-hover)}.box-sticker-table-wrap td{height:52px;padding:7px 9px;border-bottom:1px solid var(--erp-border-subtle);color:var(--erp-text-secondary);font-size:12px;text-align:center;vertical-align:middle}.box-sticker-table-wrap tbody tr:last-child td{border-bottom:0}.box-sticker-table-wrap td>strong{color:var(--erp-text)}.box-sticker-number-cell{min-width:90px}.box-sticker-print-quantity{min-width:110px}.box-sticker-print-hint{color:var(--erp-warning)!important;font-weight:700}.box-sticker-empty{display:grid;min-height:250px;padding:32px;color:var(--erp-text-muted);text-align:center;place-content:center;justify-items:center}.box-sticker-empty i{margin-bottom:11px;color:var(--erp-accent);font-size:24px}.box-sticker-empty strong{margin-bottom:4px;color:var(--erp-text);font-size:14px}.box-sticker-empty span{max-width:360px;font-size:12px;line-height:1.5}.box-sticker-preview__canvas{display:grid;min-height:180px;padding:14px;background:color-mix(in srgb,var(--erp-surface-muted) 65%,white);place-items:center}.box-sticker-preview__canvas img{display:block;width:auto;max-width:100%;max-height:220px;object-fit:contain;border:1px solid var(--erp-border-strong);border-radius:var(--erp-control-radius);background:white;box-shadow:0 9px 24px color-mix(in srgb,var(--erp-accent-hover) 10%,transparent)}.box-sticker-preview__message{display:grid;max-width:280px;justify-items:center;color:var(--erp-text-muted);text-align:center}.box-sticker-preview__message i{margin-bottom:10px;color:var(--erp-border-strong);font-size:27px}.box-sticker-preview__message strong{margin-bottom:5px;color:var(--erp-text);font-size:13px}.box-sticker-preview__message span{font-size:12px;line-height:1.5}.box-sticker-preview__message--error i{color:var(--erp-danger)}.box-sticker-preview>footer{display:flex;align-items:center;gap:6px;padding:8px 12px;border-top:1px solid var(--erp-border);color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.box-sticker-dialog__footer{display:flex;align-items:center;justify-content:space-between;gap:14px;width:100%}.box-sticker-dialog__footer>span{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption)}.box-sticker-dialog__footer>div{display:flex;gap:8px}.box-sticker-table-wrap :deep(.p-inputnumber-input){min-width:64px;padding:7px 8px;font-size:12px;text-align:center}
.box-sticker-table-wrap td:first-child,.box-sticker-table-wrap th:first-child{position:sticky;left:0;z-index:1;white-space:nowrap;background:var(--erp-surface);box-shadow:1px 0 0 var(--erp-border-subtle)}.box-sticker-table-wrap th:first-child{background:var(--erp-surface-muted)}
@media(max-width:1050px){.box-sticker-document__grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.box-sticker-document__grid{grid-template-columns:1fr}.box-sticker-dialog__footer{align-items:stretch;flex-direction:column}.box-sticker-dialog__footer>div{justify-content:flex-end;flex-wrap:wrap}.box-sticker-dialog__footer>span{text-align:right}.box-sticker-preview__canvas{min-height:180px;padding:12px}.box-sticker-preview__canvas img{max-height:220px}.box-sticker-empty{min-height:160px;padding:22px}}
</style>
