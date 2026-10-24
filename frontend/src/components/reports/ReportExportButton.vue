<template>
	<Button
		v-if="canExport && !hideButton"
		type="button"
		label="Export"
		icon="pi pi-download"
		severity="secondary"
		outlined
		class="erp-action-button report-export-button"
		:disabled="disabled"
		@click="open"
	/>
	<Dialog v-model:visible="visible" modal :header="`Export Report: ${title}`" :style="{ width: '30rem', maxWidth: 'calc(100vw - 24px)' }">
		<form class="report-export" @submit.prevent="download">
			<label for="report-export-format">File Format</label>
			<Select v-model="settings.fileFormat" input-id="report-export-format" :options="EXPORT_FORMATS" fluid />
			<template v-if="settings.fileFormat === 'CSV'">
				<label for="report-export-delimiter">CSV Delimiter</label>
				<InputText id="report-export-delimiter" v-model="settings.csvDelimiter" maxlength="1" fluid @blur="settings.csvDelimiter ||= ','" />
				<label for="report-export-quoting">CSV Quoting</label>
				<Select v-model="settings.csvQuoting" input-id="report-export-quoting" :options="CSV_QUOTING_OPTIONS" option-label="label" option-value="value" fluid />
				<template v-if="settings.csvQuoting !== 2">
					<label for="report-export-decimal">CSV Decimal Separator</label>
					<InputText id="report-export-decimal" v-model="settings.csvDecimalSep" maxlength="1" fluid @blur="settings.csvDecimalSep ||= '.'" />
				</template>
				<label for="report-export-preview">CSV Preview</label>
				<Textarea id="report-export-preview" :model-value="preview" rows="4" readonly fluid />
			</template>
			<label v-if="hasAppliedFilters" class="report-export__check">
				<Checkbox v-model="settings.includeFilters" binary input-id="report-export-filters" />
				<span>Include filters</span>
			</label>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		</form>
		<template #footer>
			<Button label="Cancel" severity="secondary" outlined :disabled="downloading" @click="visible = false" />
			<Button label="Download" icon="pi pi-download" :loading="downloading" @click="download" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { exportReportRows, exportWebReport, getExportPermission } from "../../api/reportExport.js"
import { CSV_QUOTING_OPTIONS, EXPORT_FORMATS, csvPreview, defaultExportSettings, deskExportArgs, rowsExportArgs } from "./reportExport.js"

const props = defineProps({
	title: { type: String, required: true },
	source: { type: Object, required: true },
	getRows: { type: Function, required: true },
	/** Mounts every row before `getRows` reads them; resolves to a function that undoes it when the dialog closes. */
	prepareRows: { type: Function, default: null },
	disabled: { type: Boolean, default: false },
	/** Opened from a menu through the exposed `open`. */
	hideButton: { type: Boolean, default: false },
})

const canExport = ref(false)
const visible = ref(false)
const downloading = ref(false)
const error = ref("")
const previewRows = ref([])
const settings = reactive(defaultExportSettings())
const hasAppliedFilters = computed(() => Object.keys(props.source.appliedFilters || {}).length > 0)
const preview = computed(() => csvPreview(previewRows.value, settings))

let restoreRows = null

onMounted(async () => { canExport.value = await getExportPermission(props.source) })
watch(visible, (open) => { if (!open) releaseRows() })
defineExpose({ open, canExport })

async function open() {
	error.value = ""
	await prepareRows()
	previewRows.value = props.getRows()
	visible.value = true
}

async function prepareRows() {
	const restore = await props.prepareRows?.()
	if (restore && !restoreRows) restoreRows = restore
}

function releaseRows() {
	restoreRows?.()
	restoreRows = null
}

async function download() {
	if (downloading.value) return
	downloading.value = true
	error.value = ""
	const fallbackName = `${props.title}.${settings.fileFormat === "CSV" ? "csv" : "xlsx"}`
	try {
		if (props.source.desk) await exportWebReport(deskExportArgs({ ...props.source.desk, reportKey: props.source.reportKey, appliedFilters: props.source.appliedFilters }, settings), fallbackName)
		else {
			// Rows may have been replaced (linked values, inline filters) while the dialog was open.
			await prepareRows()
			await exportReportRows(rowsExportArgs({ ...props.source, title: props.title }, requireRows(), settings), fallbackName)
		}
		visible.value = false
	} catch (reason) {
		error.value = reason?.message || "The report could not be exported."
	} finally {
		downloading.value = false
	}
}

function requireRows() {
	const rows = props.getRows()
	if (!rows.length) throw new Error("There are no report rows to export.")
	return rows
}
</script>

<style scoped>
.report-export { display: grid; gap: 8px; }
.report-export label { font-size: var(--erp-font-size-caption); font-weight: var(--erp-font-weight-semibold); }
.report-export__check { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
</style>
