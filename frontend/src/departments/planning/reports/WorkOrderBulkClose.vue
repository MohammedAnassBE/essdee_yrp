<template>
	<section aria-label="Work Order Bulk Close">
		<ReportShell :export-source="{ doctype: 'YRP Work Order' }" title="Work Order Bulk Close" generate-label="Load Work Orders" :generated="generated" :loading="loading" :error="loadError" :has-results="rows.length > 0" :generate-disabled="Boolean(filterHint) || busy" empty-title="No open Work Orders for this supplier and filters." empty-description="" @generate="loadWorkOrders" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.supplier" doctype="Supplier" label="Supplier" required :show-open-button="false" show-clear :disabled="busy" />
				<AsyncLinkMultiSelect v-model="filters.lot" doctype="SD YRP Lot" label="Lots" :disabled="busy" />
				<AsyncLinkMultiSelect v-model="filters.item" doctype="Item" label="Items" :disabled="busy" />
				<DateField v-model="filters.wo_from_date" label="WO From Date" show-clear :disabled="busy" />
				<DateField v-model="filters.wo_to_date" label="WO To Date" show-clear :disabled="busy" />
				<small v-if="filterHint" class="erp-help-text" role="status">{{ filterHint }}</small>
			</template>
			<template #actions>
				<Button v-if="permissions.can_write" :label="`Close Selected (${selectedNames.length})`" icon="pi pi-lock" :disabled="!selectedNames.length || loading || busy" @click="openCloseDialog" />
			</template>
			<div class="finishing-scroll bulk-close-scroll" role="region" aria-label="Open Work Orders" tabindex="0">
				<table class="finishing-table report-table">
					<thead><tr>
						<th class="report-align-center"><input type="checkbox" aria-label="Select all shown Work Orders" :checked="allSelected" :indeterminate="selectedNames.length > 0 && !allSelected" :disabled="busy" @change="selectAll($event.target.checked)" /></th>
						<th class="report-cell--text">Work Order</th><th class="report-cell--date" :aria-sort="dateSort === 'asc' ? 'ascending' : 'descending'"><Button label="WO Date" :icon="dateSort === 'asc' ? 'pi pi-sort-amount-up' : 'pi pi-sort-amount-down'" text @click="dateSort = dateSort === 'asc' ? 'desc' : 'asc'" /></th>
						<th class="report-cell--text">Item</th><th class="report-cell--text">Lot</th><th class="report-cell--text">Process</th><th class="report-cell--num report-align-right">Delivered</th><th class="report-cell--num report-align-right">Received</th><th class="report-cell--num report-align-right">Difference</th><th class="report-cell--text">Actions</th>
					</tr><ReportFilterRow :columns="filterColumns" :filter="inlineFilter" /></thead>
					<tbody><tr v-for="row in visibleRows" :key="row.name">
						<td class="report-align-center"><input v-model="selection" type="checkbox" :value="row.name" :aria-label="`Select Work Order ${row.name}`" :disabled="busy" /></td>
						<td class="report-cell--text bulk-close-id"><RouterLink :to="'/planning/work-orders/' + encodeURIComponent(row.name)">{{ row.name }}</RouterLink></td>
						<td class="report-cell--date">{{ formatDisplayDate(row.wo_date, "") }}</td><td class="report-cell--text">{{ row.item }}</td><td class="report-cell--text">{{ row.lot }}</td><td class="report-cell--text">{{ row.process_name }}</td>
						<td class="report-cell--num report-align-right">{{ quantity(row.total_delivered) }}</td><td class="report-cell--num report-align-right">{{ quantity(row.total_received) }}</td><td class="report-cell--num report-align-right">{{ quantity(row.difference) }}</td>
						<td class="report-cell--last-column"><Button label="View" text size="small" @click="viewDetails(row.name)" /></td>
					</tr></tbody>
				</table>
			</div>
		</ReportShell>
		<Dialog v-model:visible="detailsVisible" modal :header="`Pending Items — ${detailName}`" class="erp-dialog--xl">
			<Skeleton v-if="detailsLoading" height="12rem" />
			<WorkspaceLoadError v-else-if="detailsError" :message="detailsError" @retry="viewDetails(detailName)" />
			<div v-else-if="details" class="bulk-close-details">
				<h3>Pending groups</h3>
				<WorkOrderItemMatrix v-if="pendingGroups.length" :groups="pendingGroups" mode="summary" />
				<Message v-else severity="info" :closable="false">All items fully received.</Message>
				<section v-if="details.recut_details?.length" class="bulk-close-details">
					<h3>WO Recut Details</h3>
					<div v-for="recut in details.recut_details" :key="recut.name"><h4>{{ recut.name }}</h4><WorkOrderItemMatrix :groups="recut.items" /></div>
				</section>
				<section v-if="details.debits?.length">
					<h3>Debits</h3>
					<div class="finishing-scroll"><table class="finishing-table report-table"><thead><tr><th class="report-cell--text">Name</th><th class="report-cell--text">Debit Type</th><th class="report-cell--text">Debit No</th><th class="report-cell--num report-align-right">Debit Value</th><th class="report-cell--text">Inspection</th><th class="report-cell--text">Status</th></tr></thead>
						<tbody><tr v-for="debit in details.debits" :key="debit.name"><td class="report-cell--text">{{ debit.name }}</td><td class="report-cell--text">{{ debit.debit_type }}</td><td class="report-cell--text">{{ debit.debit_no }}</td><td class="report-cell--num report-align-right">{{ quantity(debit.debit_value) }}</td><td class="report-cell--text">{{ debit.inspection ? 'Yes' : 'No' }}</td><td class="report-cell--text report-cell--last-column">{{ debit.status }}</td></tr></tbody>
					</table></div>
				</section>
			</div>
		</Dialog>
		<Dialog v-model:visible="closeVisible" modal header="Close Selected Work Orders" class="erp-dialog--sm" :closable="!busy" :dismissable-mask="false">
			<div class="bulk-close-details">
				<p>{{ closeNames.join(', ') }}</p>
				<label class="common-field"><span class="erp-field-label">Close Reason</span><Select v-model="closeValues.close_reason" :options="CLOSE_REASONS" aria-label="Close Reason" :disabled="busy" fluid /></label>
				<label v-if="closeValues.close_reason === 'Others'" class="common-field"><span class="erp-field-label">Other Reason *</span><InputText v-model="closeValues.close_other_reason" aria-label="Other Reason" required :disabled="busy" /></label>
				<label class="common-field"><span class="erp-field-label">Remarks</span><Textarea v-model="closeValues.close_remarks" aria-label="Remarks" :disabled="busy" rows="3" /></label>
				<small v-if="reasonHint" class="erp-help-text" role="status">{{ reasonHint }}</small>
			</div>
			<template #footer><Button label="Cancel" text severity="secondary" :disabled="busy" @click="closeVisible = false" /><Button label="Review and confirm" :disabled="Boolean(reasonHint) || busy" @click="requestConfirmation" /></template>
		</Dialog>
		<DocumentConfirmationDialog v-model:visible="confirmVisible" title="Confirm Work Order close" :message="`Submit close for ${closeNames.join(', ')}? Depending on your role, this may create a Close Request for approval.`" confirm-label="Close Selected" cancel-label="Keep reviewing" :busy="busy" @confirm="confirmClose" />
		<DocumentErrorDialog :message="actionError" @dismiss="actionError = ''" />
	</section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"
import { RouterLink } from "vue-router"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import { useToast } from "primevue/usetoast"
import { getOpenWorkOrders, getWorkOrderCloseDetails, closeWorkOrders } from "../../../api/planning.js"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportFilterRow from "../../../components/reports/ReportFilterRow.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { useInlineFilters } from "../../../composables/useInlineFilters.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import WorkOrderItemMatrix from "../../fabric-store/WorkOrderItemMatrix.vue"
import { CLOSE_REASONS, bulkCloseFilterHint, closeReasonHint, pendingSummary, sortedWorkOrders } from "./workOrderBulkClose.js"

const props = defineProps({ permissions: { type: Object, default: () => ({}) } })
const toast = useToast()
function defaultFilters() { return { supplier: "", lot: [], item: [], wo_from_date: "", wo_to_date: "" } }
const filters = reactive(defaultFilters())
const filterHint = computed(() => bulkCloseFilterHint(filters))
const rows = ref([])
const selection = ref([])
const dateSort = ref("desc")
const listedRows = computed(() => sortedWorkOrders(rows.value, dateSort.value))
const filterColumns = [
	{ fieldname: "select", filterable: false }, { fieldname: "name", label: "Work Order" }, { fieldname: "wo_date", label: "WO Date", fieldtype: "Date" },
	{ fieldname: "item", label: "Item" }, { fieldname: "lot", label: "Lot" }, { fieldname: "process_name", label: "Process" },
	{ fieldname: "total_delivered", label: "Delivered", fieldtype: "Float" }, { fieldname: "total_received", label: "Received", fieldtype: "Float" },
	{ fieldname: "difference", label: "Difference", fieldtype: "Float" }, { fieldname: "actions", filterable: false },
]
const inlineFilter = useInlineFilters(listedRows, filterColumns, {
	cellValue: (row, column) => row[column.fieldname],
	cellText: (row, column) => cellText(row, column),
})
const visibleRows = inlineFilter.filteredRows
// Selection acts on the shown rows only, so a column filter never closes a hidden Work Order.
const selectedNames = computed(() => visibleRows.value.filter((row) => selection.value.includes(row.name)).map((row) => row.name))
const allSelected = computed(() => visibleRows.value.length > 0 && selectedNames.value.length === visibleRows.value.length)
const loading = ref(false)
const generated = ref(false)
const loadError = ref("")
const busy = ref(false)
const actionError = ref("")
const detailsVisible = ref(false)
const detailsLoading = ref(false)
const detailsError = ref("")
const detailName = ref("")
const details = ref(null)
const pendingGroups = computed(() => pendingSummary(details.value?.summary?.item_detail))
const closeVisible = ref(false)
const confirmVisible = ref(false)
const closeNames = ref([])
const closeValues = reactive({ close_reason: "", close_other_reason: "", close_remarks: "" })
const reasonHint = computed(() => closeReasonHint(closeValues))
let listRequest = 0
let detailRequest = 0

watch(filters, () => {
	++listRequest
	rows.value = []; selection.value = []; generated.value = false; loading.value = false; loadError.value = ""
}, { deep: true, flush: "sync" })

function selectAll(checked) { selection.value = checked ? visibleRows.value.map((row) => row.name) : [] }
function cellText(row, column) {
	if (column.fieldtype === "Float") return quantity(row[column.fieldname])
	return column.fieldtype === "Date" ? formatDisplayDate(row[column.fieldname], "") : row[column.fieldname]
}
function quantity(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }

async function loadWorkOrders() {
	if (filterHint.value || busy.value) return
	const request = ++listRequest
	loading.value = true
	loadError.value = ""
	try {
		const result = await getOpenWorkOrders(JSON.parse(JSON.stringify(filters)))
		if (request !== listRequest) return
		rows.value = result || []
		selection.value = []
		generated.value = true
	} catch (error) {
		if (request === listRequest) loadError.value = error.message || "Unable to load Work Orders."
	} finally {
		if (request === listRequest) loading.value = false
	}
}

function reset() {
	if (busy.value) return
	++listRequest
	Object.assign(filters, defaultFilters())
	rows.value = []; selection.value = []; generated.value = false; loading.value = false; loadError.value = ""
}

async function viewDetails(name) {
	const request = ++detailRequest
	detailName.value = name
	detailsVisible.value = true
	detailsLoading.value = true
	detailsError.value = ""
	details.value = null
	try {
		const result = await getWorkOrderCloseDetails(name)
		if (request === detailRequest) details.value = result
	} catch (error) {
		if (request === detailRequest) detailsError.value = error.message || "Unable to load Work Order details."
	} finally {
		if (request === detailRequest) detailsLoading.value = false
	}
}

function openCloseDialog() {
	if (!props.permissions.can_write || !selectedNames.value.length || loading.value || busy.value) return
	closeNames.value = [...selectedNames.value]
	Object.assign(closeValues, { close_reason: "", close_other_reason: "", close_remarks: "" })
	closeVisible.value = true
}

function requestConfirmation() {
	if (props.permissions.can_write && !reasonHint.value && closeNames.value.length && !busy.value) confirmVisible.value = true
}

async function confirmClose() {
	if (!confirmVisible.value || !props.permissions.can_write || reasonHint.value || !closeNames.value.length || busy.value) return
	busy.value = true
	actionError.value = ""
	try {
		const response = await closeWorkOrders([...closeNames.value], { ...closeValues, close_other_reason: closeValues.close_reason === "Others" ? closeValues.close_other_reason.trim() : "" })
		for (const result of response.results || []) toast.add({ severity: "success", summary: result.work_order, detail: result.open_status, life: 8000 })
		closeVisible.value = false
		confirmVisible.value = false
		selection.value = []
	} catch (error) {
		confirmVisible.value = false
		actionError.value = error.message || "Unable to close Work Orders."
		return
	} finally {
		busy.value = false
	}
	await loadWorkOrders()
}

onBeforeUnmount(() => { ++listRequest; ++detailRequest })
</script>

<style scoped>
.bulk-close-scroll { max-height: 70vh; }
.finishing-table td.bulk-close-id { white-space: nowrap; }
.bulk-close-details { display: grid; min-width: 0; gap: var(--erp-space-3); }
.bulk-close-details :is(h3, h4, p) { margin: 0; }
.bulk-close-details p { overflow-wrap: anywhere; }
input[type="checkbox"] { accent-color: var(--erp-accent); }
</style>
