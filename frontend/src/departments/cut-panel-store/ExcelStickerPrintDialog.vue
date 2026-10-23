<template>
	<Dialog
		:visible="visible"
		modal
		maximizable
		:dismissable-mask="false"
		:closable="!closeLocked"
		:close-on-escape="!closeLocked"
		:header="record?.name ? `Excel Sticker Print · ${record.name}` : 'New Excel Sticker Print'"
		class="excel-sticker-print-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="visibilityChanged"
	>
		<div v-if="loading" class="excel-sticker-dialog__loading">
			<Skeleton v-for="index in 6" :key="index" height="3rem" />
		</div>

		<div v-else class="excel-sticker-dialog__body">
			<section class="excel-sticker-document" aria-label="Excel Sticker Print details">
				<header class="excel-sticker-section-head">
					<div><span>DOCUMENT</span><h3>Workbook & format</h3></div>
					<DocumentStatusBadge :docstatus="record?.docstatus" :label="record?.status || 'Draft'" />
				</header>
				<div class="excel-sticker-document__grid">
					<div class="excel-upload-field">
						<span><span>Excel File</span> <b>*</b></span>
						<div class="excel-upload-field__control" :class="{ 'excel-upload-field__control--busy': uploading }">
							<input
								ref="fileInput"
								type="file"
								accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
								:disabled="!canEdit || busy"
								@change="uploadSelected"
							/>
							<i class="pi pi-file-excel" aria-hidden="true" />
							<div><strong>{{ uploadedFileName || "No workbook uploaded" }}</strong><small>{{ uploadedFileName ? "Private Excel attachment" : "Only .xlsx files are accepted" }}</small></div>
							<Button v-if="canEdit" :label="uploadedFileName ? 'Replace' : 'Choose File'" icon="pi pi-upload" severity="secondary" outlined size="small" :disabled="busy" @click="openFilePicker" />
						</div>
						<div v-if="uploading" class="excel-upload__progress" role="progressbar" :aria-valuenow="uploadProgress" aria-valuemin="0" aria-valuemax="100">
							<span :style="{ width: `${uploadProgress}%` }" /><small>Uploading {{ uploadProgress }}%</small>
						</div>
					</div>

					<LinkField
						v-model="form.print_format"
						label="Print Format"
						doctype="YRP ZPL Raw Print Format"
						required
						:disabled="!canEdit || busy"
						@update:model-value="valueChanged"
					/>
					<div class="excel-sticker-context">
						<span>Parsed Rows</span>
						<strong>{{ record ? `${rowCount.toLocaleString("en-IN")} rows` : "Available after submission" }}</strong>
					</div>
				</div>
			</section>

			<div class="excel-sticker-workspace">
				<section class="excel-sticker-sample" aria-label="Excel data sample">
					<header class="excel-sticker-section-head">
						<div><span>DATA SAMPLE</span><h3>Uploaded workbook</h3></div>
						<strong>{{ rowCount.toLocaleString("en-IN") }} {{ rowCount === 1 ? "row" : "rows" }}</strong>
					</header>
					<div v-if="sampleRows.length && sampleColumns.length" class="excel-sticker-sample__wrap" tabindex="0" role="region" aria-label="Excel workbook sample">
						<table>
							<thead><tr><th v-for="column in sampleColumns" :key="column">{{ column }}</th></tr></thead>
							<tbody>
								<tr v-for="(row, index) in sampleRows" :key="index">
									<td v-for="column in sampleColumns" :key="column" :title="formatCell(row[column])">{{ formatCell(row[column]) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
					<div v-else class="excel-sticker-empty">
						<i class="pi pi-table" aria-hidden="true" />
						<strong>{{ record?.docstatus === 1 ? "No preview rows available" : "Submit to parse the workbook" }}</strong>
						<span>{{ record?.docstatus === 1 ? "The submitted workbook did not return a display sample." : "The server validates and parses the private .xlsx file during submission." }}</span>
					</div>
					<footer v-if="sampleTruncated"><i class="pi pi-info-circle" /> This is a bounded sample. The full workbook remains on the server.</footer>
				</section>

				<section class="excel-sticker-preview" aria-label="Label preview">
					<header class="excel-sticker-section-head">
						<div><span>PREVIEW</span><h3>First-row label</h3></div>
						<Button v-if="record?.docstatus === 1" icon="pi pi-refresh" severity="secondary" text rounded aria-label="Refresh label preview" :loading="previewLoading" :disabled="busy" @click="loadPreview" />
					</header>
					<div class="excel-sticker-preview__canvas">
						<Skeleton v-if="previewLoading" width="82%" height="250px" />
						<img v-else-if="previewUrl" :src="previewUrl" :alt="`Label preview for ${record?.name || 'Excel Sticker Print'}`" @error="previewImageFailed" />
						<div v-else-if="previewError" class="excel-sticker-preview__message excel-sticker-preview__message--error" role="status">
							<i class="pi pi-image" aria-hidden="true" /><strong>Preview unavailable</strong><span>{{ previewError }}</span>
						</div>
						<div v-else class="excel-sticker-preview__message">
							<i class="pi pi-image" aria-hidden="true" /><strong>{{ previewEmptyTitle }}</strong><span>{{ previewEmptyMessage }}</span>
						</div>
					</div>
				</section>
			</div>
		</div>

		<DocumentActivity :doctype="'YRP Excel Sticker Print'" :name="record?.name || ''" :record="record" />
		<template #footer>
			<div class="excel-sticker-dialog__footer">
				<span>{{ footerSummary }}</span>
				<div>
					<DocumentShortcuts :busy="busy || confirmationVisible" :can-save="canEdit && canSave && (!record?.name || dirty)" :can-submit="Boolean(documentPermissions.can_submit && !dirty)" submit-confirms @save="save" @submit="requestCommand('submit')" />
					<Button label="Close" severity="secondary" text :disabled="busy" @click="requestClose" />
					<DocumentDeleteButton v-if="record?.name" doctype="YRP Excel Sticker Print" :name="record.name" :docstatus="record.docstatus" :disabled="busy" :redirect="false" @deleted="documentDeleted" />
					<DocumentPrintButton v-if="record?.name" doctype="YRP Excel Sticker Print" :name="record.name" :docstatus="record.docstatus" :disabled="busy" />
					<Button v-if="canPrint" label="Print Labels" icon="pi pi-print" severity="secondary" outlined :disabled="busy" @click="printerVisible = true" />
					<Button v-if="documentPermissions.can_submit" label="Submit" :title="withShortcutHint('Submit', 'submit')" icon="pi pi-check" severity="secondary" outlined :disabled="busy || dirty" @click="requestCommand('submit')" />
					<Button v-if="canEdit" label="Save" :title="withShortcutHint('Save', 'save')" icon="pi pi-save" :loading="acting === 'save'" :disabled="busy || !canSave" @click="save" />
				</div>
			</div>
		</template>
	</Dialog>

	<PrinterDialog
		v-model:visible="printerVisible"
		:busy="acting === 'print'"
		show-resolution
		:resolutions="['200dpi', '300dpi']"
		default-resolution="300dpi"
		@confirm="printLabels"
		@error="printerLoadFailed"
	/>

	<DocumentConfirmationDialog
		v-model:visible="confirmationVisible"
		:title="confirmationTitle"
		:message="confirmationMessage"
		:confirm-label="confirmationLabel"
		:severity="pendingAction === 'submit' ? 'success' : 'danger'"
		:busy="acting === pendingAction"
		@confirm="confirmAction"
	/>

	<DocumentErrorDialog :message="error" title="Excel Sticker Print action failed" @dismiss="error = ''" />
</template>

<script setup>
import DocumentActivity from "../../components/documents/DocumentActivity.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import Button from "primevue/button"
import DocumentShortcuts from "../../components/documents/DocumentShortcuts.vue"
import { withShortcutHint } from "../../utils/documentShortcuts.js"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"

import {
	executeExcelStickerCommand,
	getExcelStickerEditor,
	getExcelStickerPreview,
	getExcelStickerPrintData,
	saveExcelSticker,
} from "../../api/cutPanelStore.js"
import { uploadFile } from "../../api/frappe.js"
import { printQzRaw } from "../../api/qzPrinter.js"
import LinkField from "../../components/common/LinkField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import PrinterDialog from "./PrinterDialog.vue"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../../utils/newDocumentDefaults.js"

const props = defineProps({
	visible: Boolean,
	documentName: { type: String, default: "" },
})

const emit = defineEmits(["update:visible", "changed"])
const editor = reactive({ permissions: {}, upload: null, record: null })
const form = reactive({ excel_file: "", print_format: "", temporary_name: "" })
const fileInput = ref(null)
const loading = ref(false)
const acting = ref("")
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadedFileName = ref("")
const dirty = ref(false)
const error = ref("")
const printerVisible = ref(false)
const confirmationVisible = ref(false)
const pendingAction = ref("")
const previewLoading = ref(false)
const previewUrl = ref("")
const previewError = ref("")
let loadSequence = 0
let previewSequence = 0
let uploadController = null
let previewAbortController = null
let previewObjectUrl = ""

const record = computed(() => editor.record)
const busy = computed(() => Boolean(acting.value) || uploading.value)
const closeLocked = computed(() => busy.value || printerVisible.value || confirmationVisible.value || Boolean(error.value))
const documentPermissions = computed(() => record.value?.permissions || editor.permissions || {})
const canEdit = computed(() => Number(record.value?.docstatus || 0) === 0 && (record.value ? Boolean(documentPermissions.value.can_write) : Boolean(editor.permissions?.can_create)))
const canPrint = computed(() => Number(record.value?.docstatus) === 1 && Boolean(documentPermissions.value.can_print))
const canSave = computed(() => Boolean(form.excel_file && form.print_format))
const rowCount = computed(() => Number(record.value?.row_count || 0))
const sampleColumns = computed(() => record.value?.sample?.columns || record.value?.columns || [])
const sampleRows = computed(() => record.value?.sample?.rows || record.value?.sample_rows || [])
const sampleTruncated = computed(() => Boolean(record.value?.sample?.truncated))
const previewEmptyTitle = computed(() => record.value?.docstatus === 1 ? "No preview generated" : "Submit to generate preview")
const previewEmptyMessage = computed(() => record.value?.docstatus === 1 ? "Refresh to render the first workbook row." : "A first-row preview is available after the workbook is parsed.")
const footerSummary = computed(() => uploading.value ? `Uploading ${uploadProgress.value}%` : record.value?.docstatus === 1 ? `${rowCount.value.toLocaleString("en-IN")} parsed rows` : uploadedFileName.value || "Upload a private .xlsx workbook")
const confirmationTitle = computed(() => ({ close: "Discard unsaved changes?", submit: "Submit Excel Sticker Print?" })[pendingAction.value] || "Confirm action")
const confirmationMessage = computed(() => ({
	close: "Your unsaved workbook and format changes will be lost.",
	submit: `Submit ${record.value?.name || "this Excel Sticker Print"}? The workbook will be validated and parsed on the server.`,
})[pendingAction.value] || "Continue with this action?")
const confirmationLabel = computed(() => ({ close: "Discard Changes", submit: "Submit" })[pendingAction.value] || "Continue")

watch(() => [props.visible, props.documentName], ([visible]) => {
	if (visible) load()
})

onBeforeUnmount(() => {
	uploadController?.abort()
	previewAbortController?.abort()
	revokePreviewUrl()
})

async function load() {
	const sequence = ++loadSequence
	uploadController?.abort()
	previewAbortController?.abort()
	loading.value = true
	error.value = ""
	try {
		const filterDefaults = props.documentName ? {} : filterDefaultsFor("YRP Excel Sticker Print", ["print_format"])
		const payload = await getExcelStickerEditor(props.documentName)
		if (sequence !== loadSequence) return
		applyEditorPayload(payload && !payload.record ? { ...payload, defaults: withNewDocumentDefaults(payload.defaults, filterDefaults) } : payload)
		if (record.value?.docstatus === 1) void loadPreview()
	} catch (reason) {
		if (sequence === loadSequence) error.value = messageOf(reason, "Unable to load the Excel Sticker Print.")
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

/** Staged list filters for a new document, limited to the fields this form holds. */
function filterDefaultsFor(doctype, keys) {
	const staged = takeNewDocumentDefaults(doctype)
	return Object.fromEntries(keys.filter((key) => key in staged).map((key) => [key, staged[key]]))
}

function applyEditorPayload(payload = {}) {
	revokePreviewUrl()
	editor.permissions = { ...(payload.permissions || {}) }
	editor.record = payload.record ? clone(payload.record) : null
	const source = payload.record || payload.defaults || {}
	form.excel_file = source.excel_file || ""
	form.print_format = source.print_format || ""
	form.temporary_name = payload.defaults?.temporary_name || ""
	editor.upload = payload.upload ? { ...payload.upload } : record.value?.name ? {
		doctype: "YRP Excel Sticker Print",
		docname: record.value.name,
		fieldname: "excel_file",
		is_private: 1,
	} : null
	uploadedFileName.value = fileNameFromUrl(form.excel_file)
	uploadProgress.value = 0
	dirty.value = false
	previewError.value = ""
}

function applyRecordPayload(payload) {
	const changed = payload?.record || payload
	if (!changed?.name) return false
	editor.record = clone(changed)
	editor.permissions = { ...(changed.permissions || editor.permissions) }
	form.excel_file = changed.excel_file || form.excel_file
	form.print_format = changed.print_format || form.print_format
	form.temporary_name = ""
	editor.upload = {
		doctype: "YRP Excel Sticker Print",
		docname: changed.name,
		fieldname: "excel_file",
		is_private: 1,
	}
	uploadedFileName.value = fileNameFromUrl(form.excel_file)
	dirty.value = false
	return true
}

function openFilePicker() {
	if (!canEdit.value || busy.value) return
	fileInput.value?.click()
}

async function uploadSelected(event) {
	const input = event.target
	const file = input.files?.[0]
	input.value = ""
	if (!file) return
	if (!file.name.toLowerCase().endsWith(".xlsx")) {
		error.value = "Upload a valid .xlsx file."
		return
	}
	const target = editor.upload
	if (!target?.doctype || !target?.docname || !target?.fieldname) {
		error.value = "The Excel upload target is unavailable. Reopen this editor and try again."
		return
	}

	uploadController?.abort()
	const controller = new AbortController()
	uploadController = controller
	uploading.value = true
	uploadProgress.value = 0
	error.value = ""
	const previous = { fileUrl: form.excel_file, fileName: uploadedFileName.value }
	try {
		const uploaded = await uploadFile(file, {
			doctype: target.doctype,
			docname: target.docname,
			fieldname: target.fieldname,
			isPrivate: Number(target.is_private ?? 1),
			signal: controller.signal,
			onProgress: (value) => { if (uploadController === controller) uploadProgress.value = value },
		})
		if (uploadController !== controller) return
		const fileUrl = uploaded?.file_url || uploaded?.fileUrl
		if (!fileUrl) throw new Error("The upload completed without a private file URL.")
		form.excel_file = fileUrl
		uploadedFileName.value = uploaded?.file_name || file.name || fileNameFromUrl(fileUrl)
		dirty.value = true
	} catch (reason) {
		if (reason?.name === "AbortError") return
		form.excel_file = previous.fileUrl
		uploadedFileName.value = previous.fileName
		error.value = messageOf(reason, "Unable to upload the Excel workbook.")
	} finally {
		if (uploadController === controller) {
			uploadController = null
			uploading.value = false
		}
	}
}

function valueChanged() {
	dirty.value = true
}

function documentValues() {
	return {
		excel_file: form.excel_file,
		print_format: form.print_format,
		...(record.value ? {} : { temporary_name: form.temporary_name }),
	}
}

async function save() {
	acting.value = "save"
	error.value = ""
	try {
		const saved = await saveExcelSticker(documentValues(), {
			name: record.value?.name,
			expectedModified: record.value?.modified,
		})
		applyRecordPayload(saved)
		emit("changed", editor.record)
	} catch (reason) {
		error.value = messageOf(reason, "Unable to save the Excel Sticker Print.")
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
	if (dirty.value) requestCommand("close")
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
		pendingAction.value = ""
		emit("update:visible", false)
		return
	}
	acting.value = action
	error.value = ""
	try {
		const changed = await executeExcelStickerCommand(record.value.name, action, record.value.modified)
		applyRecordPayload(changed)
		if (record.value?.docstatus === 1) void loadPreview()
		else revokePreviewUrl()
		emit("changed", editor.record)
	} catch (reason) {
		error.value = messageOf(reason, `Unable to ${action} the Excel Sticker Print.`)
	} finally {
		acting.value = ""
		pendingAction.value = ""
	}
}

function printerLoadFailed(message) {
	printerVisible.value = false
	error.value = message || "Unable to load label printers."
}

async function printLabels(selection) {
	if (!selection?.printer || !selection?.printerType) {
		printerVisible.value = false
		error.value = "Choose a printer and either 200dpi or 300dpi."
		return
	}
	acting.value = "print"
	error.value = ""
	try {
		const payload = await getExcelStickerPrintData(record.value.name, selection.printerType)
		const zpl = typeof payload === "string" ? payload : payload?.zpl || payload?.raw || payload?.code
		if (!zpl) throw new Error("The server did not return any labels to print.")
		await printQzRaw(selection.printer, zpl)
		printerVisible.value = false
	} catch (reason) {
		printerVisible.value = false
		error.value = messageOf(reason, "The Excel labels were not printed.")
	} finally {
		acting.value = ""
	}
}

async function loadPreview() {
	if (!record.value?.name || Number(record.value.docstatus) !== 1) return
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
		const payload = await getExcelStickerPreview(documentName)
		if (sequence !== previewSequence || record.value?.name !== documentName) return
		const directUrl = payload?.image_url || payload?.preview_url || payload?.url
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
		previewError.value = reason?.name === "AbortError" ? "The preview service timed out." : messageOf(reason, "The first-row label preview could not be rendered.")
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

function fileNameFromUrl(value) {
	if (!value) return ""
	try { return decodeURIComponent(String(value).split("/").pop() || "") } catch { return String(value).split("/").pop() || "" }
}

function formatCell(value) {
	if (value === null || value === undefined || value === "") return "—"
	if (typeof value === "object") return JSON.stringify(value)
	return String(value)
}

function messageOf(reason, fallback) {
	return reason?.message || String(reason || "") || fallback
}

function clone(value) {
	return JSON.parse(JSON.stringify(value))
}
function documentDeleted() {
	emit("update:visible", false)
	emit("changed")
}
</script>

<style scoped>
.excel-sticker-dialog__loading,.excel-sticker-dialog__body{display:grid;gap:12px}.excel-sticker-document,.excel-sticker-sample,.excel-sticker-preview{min-width:0;overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.excel-sticker-section-head{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:43px;padding:9px 12px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.excel-sticker-section-head>div{display:flex;align-items:center;gap:9px;min-width:0}.excel-sticker-section-head span{color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:800;letter-spacing:.08em}.excel-sticker-section-head h3{margin:0;color:var(--erp-text);font-size:.95rem}.excel-sticker-section-head>strong,.excel-sticker-section-head>em{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption);font-style:normal}.excel-sticker-document__status--1{color:var(--erp-accent-hover)!important}.excel-sticker-document__status--2{color:var(--erp-danger)!important}.excel-sticker-document__grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(240px,1fr) minmax(210px,.75fr);align-items:end;gap:12px;padding:12px}.excel-upload-field,.excel-sticker-context{display:grid;gap:7px;min-width:0}.excel-upload-field>span,.excel-sticker-context>span{color:var(--erp-text);font-size:var(--erp-font-size-caption);font-weight:700}.excel-upload-field>span b{color:var(--erp-danger)}.excel-upload-field__control{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:10px;min-height:43px;padding:5px 6px 5px 11px;border:1px solid var(--erp-border-strong);border-radius:var(--erp-control-radius);background:var(--erp-surface);box-shadow:var(--erp-shadow-xs)}.excel-upload-field__control--busy{border-color:color-mix(in srgb,var(--erp-accent) 45%,var(--erp-border-strong));background:var(--erp-accent-soft)}.excel-upload-field__control>input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.excel-upload-field__control>i{color:var(--erp-accent);font-size:19px}.excel-upload-field__control>div{display:grid;gap:1px;min-width:0}.excel-upload-field__control strong,.excel-upload-field__control small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.excel-upload-field__control strong{color:var(--erp-text);font-size:12px}.excel-upload-field__control small{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.excel-upload__progress{position:relative;height:18px;overflow:hidden;border-radius:999px;background:var(--erp-surface-muted)}.excel-upload__progress>span{position:absolute;inset:0 auto 0 0;background:var(--erp-accent);transition:width .15s ease}.excel-upload__progress small{position:relative;display:flex;align-items:center;justify-content:center;height:100%;color:var(--erp-text);font-size:var(--erp-font-size-min);font-weight:750}.excel-sticker-context strong{display:block;min-height:auto;padding:2px 0 7px;border:0;border-bottom:1px solid var(--erp-border);border-radius:0;background:transparent;color:var(--erp-text);font-size:13px;font-weight:750}.excel-sticker-workspace{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(290px,.8fr);gap:12px;min-width:0}.excel-sticker-sample__wrap{max-width:100%;overflow:auto}.excel-sticker-sample__wrap table{width:100%;min-width:680px;border-collapse:collapse}.excel-sticker-sample__wrap th{padding:8px 10px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-muted);color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-align:left;text-transform:none;white-space:nowrap}.excel-sticker-sample__wrap td{max-width:280px;padding:9px 10px;border-bottom:1px solid var(--erp-border-subtle);overflow:hidden;color:var(--erp-text-secondary);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.excel-sticker-sample__wrap tbody tr:last-child td{border-bottom:0}.excel-sticker-sample>footer{display:flex;align-items:center;gap:6px;padding:8px 12px;border-top:1px solid var(--erp-border);color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.excel-sticker-empty{display:grid;min-height:270px;padding:32px;color:var(--erp-text-muted);text-align:center;place-content:center;justify-items:center}.excel-sticker-empty i{margin-bottom:11px;color:var(--erp-accent);font-size:24px}.excel-sticker-empty strong{margin-bottom:4px;color:var(--erp-text);font-size:14px}.excel-sticker-empty span{max-width:380px;font-size:12px;line-height:1.5}.excel-sticker-preview{align-self:start}.excel-sticker-preview__canvas{display:grid;min-height:315px;padding:18px;background:color-mix(in srgb,var(--erp-surface-muted) 65%,var(--erp-surface));place-items:center}.excel-sticker-preview__canvas img{display:block;width:100%;max-width:440px;max-height:360px;object-fit:contain;border:1px solid var(--erp-border-strong);border-radius:var(--erp-control-radius);background:white;box-shadow:0 9px 24px color-mix(in srgb,var(--erp-accent-hover) 10%,transparent)}.excel-sticker-preview__message{display:grid;max-width:280px;justify-items:center;color:var(--erp-text-muted);text-align:center}.excel-sticker-preview__message i{margin-bottom:10px;color:var(--erp-border-strong);font-size:27px}.excel-sticker-preview__message strong{margin-bottom:5px;color:var(--erp-text);font-size:13px}.excel-sticker-preview__message span{font-size:12px;line-height:1.5}.excel-sticker-preview__message--error i{color:var(--erp-danger)}.excel-sticker-dialog__footer{display:flex;align-items:center;justify-content:space-between;gap:14px;width:100%}.excel-sticker-dialog__footer>span{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption)}.excel-sticker-dialog__footer>div{display:flex;gap:8px}
@media(max-width:1050px){.excel-sticker-document__grid{grid-template-columns:repeat(2,minmax(0,1fr))}.excel-sticker-workspace{grid-template-columns:1fr}.excel-sticker-preview__canvas{min-height:260px}}
@media(max-width:600px){.excel-sticker-document__grid{grid-template-columns:1fr}.excel-sticker-dialog__footer{align-items:stretch;flex-direction:column}.excel-sticker-dialog__footer>div{justify-content:flex-end;flex-wrap:wrap}.excel-sticker-dialog__footer>span{text-align:right}.excel-sticker-preview__canvas{min-height:180px;padding:12px}.excel-sticker-preview__canvas img{max-height:220px}.excel-sticker-empty{min-height:160px;padding:22px}}
</style>
