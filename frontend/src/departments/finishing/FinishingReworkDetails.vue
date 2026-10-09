<template>
	<DepartmentPage title="Rework Details" accent="#087c91" back-to="/finishing" back-label="Finishing" :show-title="false" flat full-width inline-navigation>
		<div class="finishing-rework erp-workspace" data-finishing-page="rework-details">
			<ReportShell title="Rework Details" :generated="generated" :loading="loading" :has-results="seriesRows.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
				<template #filters>
					<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
					<LinkField v-model="filters.item" doctype="Item" label="Item" placeholder="Search item…" :show-open-button="false" show-clear />
					<label class="common-field"><span class="finishing-field-label">Colour</span><InputText v-model="filters.colour" placeholder="Colour" fluid /></label>
					<LinkField v-model="filters.receivedType" doctype="YRP Received Type" label="Received Type" placeholder="Search received type…" :show-open-button="false" show-clear />
					<label class="finishing-report-toggle"><Checkbox v-model="filters.showReworked" binary input-id="rework-show-reworked" /><span>Show Reworked</span></label>
				</template>
				<template #metrics>
					<div class="report-metric"><i class="pi pi-list" /><div><span>Sources</span><strong>{{ formatQuantity(seriesRows.length) }}</strong></div></div>
					<div v-for="type in data.types" :key="type" class="report-metric"><i class="pi pi-replay" /><div><span>{{ type }}</span><strong>{{ formatQuantity((data.total_detail?.[type] || 0) - (data.total_rejection_detail?.[type] || 0)) }}</strong></div></div>
					<div class="report-metric"><i class="pi pi-hourglass" /><div><span>{{ appliedShowReworked ? "Reworked" : "Pending" }}</span><strong>{{ formatQuantity((data.total_sum || 0) - (data.total_rejection || 0)) }}</strong></div></div>
				</template>
				<div class="finishing-stack">
					<FinishingReportHeading title="Rework Details" :period="period">
						<Button label="Download Excel" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" :loading="downloading" @click="download" />
					</FinishingReportHeading>
					<p v-if="!canWrite && !appliedShowReworked" class="finishing-empty">You have read-only access. GRN Rework Item write permission is required to clear stock.</p>
					<FinishingSeriesTable :rows="seriesRows" :types="data.types || []" :expanded="expanded" label="Rework sources" printable @toggle="toggle" @open-grn="openGrn" @print="printRework">
						<template #detail="{ detail }">
							<FinishingReworkEntry
								v-for="(group, key) in detail.rework_detail"
								:key="key"
								:title="key"
								:subtitle="detail.warehouse || ''"
								:received-type="key.split('-')[0]"
								:size-field="detail.size"
								:items="group.items"
								:editable="canWrite && !appliedShowReworked"
								:busy="busy"
								@changed="group.changed = 1"
								@update-rejection="updateRejection(group, detail.lot)"
								@update-reworked="updateReworked(group, detail.lot)"
								@complete="complete(group, detail.lot)"
							/>
						</template>
					</FinishingSeriesTable>
				</div>
			</ReportShell>
		</div>
		<RelatedDocumentWorkspaceDialog v-model:visible="grnOpen" doctype="YRP Goods Received Note" :name="grnName" @closed="grnOpen = false" />
		<DocumentErrorDialog :message="error" title="Rework could not be updated" @dismiss="error = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import InputText from "primevue/inputtext"
import { useToast } from "primevue/usetoast"
import { computed, reactive, ref } from "vue"

import { downloadReworkDetails, getReworkDetails, updateReworkPartial, updateReworkRejection } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../components/reports/ReportShell.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import RelatedDocumentWorkspaceDialog from "../fabric-store/RelatedDocumentWorkspaceDialog.vue"
import FinishingReworkEntry from "./components/FinishingReworkEntry.vue"
import FinishingSeriesTable from "./components/FinishingSeriesTable.vue"
import { formatQuantity } from "./finishingViews.js"
import FinishingReportHeading from "./reports/FinishingReportHeading.vue"
import { firstColourLabel } from "./reports/finishingReports.js"
import { reworkRowsError } from "./reports/reworkRules.js"
import { useReportRequest } from "./reports/useReportRequest.js"
import "./finishing.css"

const toast = useToast()
const confirmAction = useActionConfirmation()
const filters = reactive(defaultFilters())
const data = ref({})
const applied = ref({})
const appliedShowReworked = ref(false)
const period = ref("")
const expanded = ref("")
const busy = ref(false)
const downloading = ref(false)
const grnOpen = ref(false)
const grnName = ref("")
const { loading, generated, error, run, clear } = useReportRequest()
const canWrite = computed(() => Boolean(data.value.permissions?.can_write))
const seriesRows = computed(() => Object.entries(data.value.report_detail || {}).map(([series, detail]) => ({
	series,
	detail,
	colour: firstColourLabel(detail.rework_detail),
	values: Object.fromEntries((data.value.types || []).map((type) => [type, (detail.types?.[type] || 0) - (detail.rejection_detail?.[type] || 0)])),
	total: (detail.total || 0) - (detail.total_rejection || 0),
})))

function defaultFilters() {
	return { lot: "", item: "", colour: "", receivedType: "", showReworked: false }
}

function requestFilters() {
	return { lot: filters.lot, item: filters.item, colour: filters.colour, received_type: filters.receivedType, show_reworked: filters.showReworked ? 1 : 0 }
}

function generate(keepExpanded = false) {
	const request = keepExpanded === true ? applied.value : requestFilters()
	run("", () => getReworkDetails(request), (value) => {
		data.value = value || {}
		applied.value = request
		appliedShowReworked.value = Boolean(request.show_reworked)
		if (keepExpanded !== true) expanded.value = ""
		period.value = [request.lot, request.item, request.colour, request.received_type].filter(Boolean).join(" · ")
	})
}

async function mutate(request, message) {
	if (busy.value) return
	busy.value = true
	try {
		await request()
		toast.add({ severity: "success", summary: message, life: 3000 })
		generate(true)
	} catch (reason) {
		error.value = reason?.message || "Unable to update this rework."
	} finally {
		busy.value = false
	}
}

function updateRejection(group, lot) {
	if (!group.changed) return (error.value = "There is nothing changed in this row.")
	const message = reworkRowsError(group.items)
	if (message) return (error.value = message)
	mutate(() => updateReworkRejection(group.items, 0, lot), "Rejection quantity updated")
}

function updateReworked(group, lot) {
	const message = reworkRowsError(group.items, true)
	if (message) return (error.value = message)
	confirmAction({ header: "Convert to reworked?", message: "Are you sure want to convert the entered pieces to reworked (Accepted) stock?", acceptLabel: "Convert", acceptIcon: "pi pi-replay", acceptSeverity: "primary", rejectLabel: "No", accept: () => mutate(() => updateReworkPartial(group.items, lot), "Reworked pieces converted to Accepted") })
}

function complete(group, lot) {
	const message = reworkRowsError(group.items)
	if (message) return (error.value = message)
	confirmAction({ header: "Complete rework?", message: "Are you sure want to final the item? Remaining pieces become Accepted and entered Rejection pieces become Rejected.", acceptLabel: "Complete Rework", acceptIcon: "pi pi-check", rejectLabel: "No", accept: () => mutate(() => updateReworkRejection(group.items, 1, lot), "Rework completed") })
}

async function download() {
	downloading.value = true
	try {
		await downloadReworkDetails(applied.value)
	} catch (reason) {
		error.value = reason?.message || "Unable to download Rework Details."
	} finally {
		downloading.value = false
	}
}

function toggle(series) {
	expanded.value = expanded.value === series ? "" : series
}

function printRework(grn) {
	const query = new URLSearchParams({
		doctype: "YRP Goods Received Note",
		name: grn,
		trigger_print: "1",
		format: appliedShowReworked.value ? "Essdee Reworked Print" : "Essdee Rework Print",
		no_letterhead: "1",
	})
	if (!window.open(`/printview?${query.toString()}`, "_blank")) error.value = "Please enable pop-ups to print."
}

function openGrn(name) {
	grnName.value = name
	grnOpen.value = true
}

function reset() {
	Object.assign(filters, defaultFilters())
	data.value = {}
	clear()
}
</script>

<style scoped>
.finishing-rework { min-width: 0; padding-top: 0; }
</style>
