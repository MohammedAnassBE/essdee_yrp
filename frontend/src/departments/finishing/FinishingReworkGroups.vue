<template>
	<DepartmentPage title="Rework Grouped Details" accent="#087c91" back-to="/finishing" back-label="Finishing" :show-title="false" flat full-width inline-navigation>
		<div class="finishing-rework erp-workspace" data-finishing-page="rework-groups">
			<ReportShell title="Rework Grouped Details" :generated="generated" :loading="loading" :has-results="groups.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
				<template #filters>
					<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
					<LinkField v-model="filters.item" doctype="Item" label="Item" placeholder="Search item…" :show-open-button="false" show-clear />
					<label class="common-field"><span class="finishing-field-label">Colour</span><InputText v-model="filters.colour" placeholder="Colour" fluid /></label>
					<label class="finishing-report-toggle"><Checkbox v-model="filters.showReworked" binary input-id="rework-groups-show-reworked" /><span>Show Reworked</span></label>
				</template>
				<template #metrics>
					<div class="report-metric"><i class="pi pi-objects-column" /><div><span>Item / Lot groups</span><strong>{{ formatQuantity(groups.length) }}</strong></div></div>
					<div class="report-metric"><i class="pi pi-list" /><div><span>Rows</span><strong>{{ formatQuantity(rowCount) }}</strong></div></div>
					<div class="report-metric"><i class="pi pi-hourglass" /><div><span>{{ appliedShowReworked ? "Received" : "Pending" }}</span><strong>{{ formatQuantity(receivedTotal) }}</strong></div></div>
				</template>
				<div class="finishing-stack">
					<p v-if="!canWrite && !appliedShowReworked" class="finishing-empty">You have read-only access. GRN Rework Item write permission is required to clear stock.</p>
					<section v-for="group in groups" :key="group.key" class="finishing-section" :aria-label="group.key">
						<h3 class="finishing-section__title">{{ group.key }}</h3>
						<div class="finishing-scroll" role="region" tabindex="0" :aria-label="`${group.key} rework rows`">
							<table class="finishing-table rework-groups__table">
								<thead>
									<tr>
										<th class="finishing-table__colour">Colour</th>
										<th v-if="group.is_set_item">Part</th>
										<th>GRN Number</th>
										<th>Received Type</th>
										<th v-if="editable" class="rework-groups__actions">Actions</th>
										<th>Row</th>
										<th v-for="size in group.sizes" :key="size" class="erp-number">{{ size }}</th>
										<th class="erp-number">Total</th>
									</tr>
								</thead>
								<tbody v-for="(row, index) in group.rows" :key="`${row.grn_number}-${row.colour}-${row.part}-${row.received_type}`">
									<tr>
										<td :rowspan="editable ? 3 : 1" class="finishing-table__colour">{{ row.colour }}</td>
										<td v-if="group.is_set_item" :rowspan="editable ? 3 : 1">{{ row.part }}</td>
										<td :rowspan="editable ? 3 : 1"><button type="button" class="rework-groups__link" @click="openGrn(row.grn_number)">{{ row.grn_number }}</button></td>
										<td :rowspan="editable ? 3 : 1">{{ row.received_type }}</td>
										<td v-if="editable" rowspan="3" class="rework-groups__actions">
											<div role="group" :aria-label="`${row.grn_number} ${row.colour} actions`">
												<Button label="Update Reworked Piece" icon="pi pi-replay" size="small" :disabled="busy" @click="updateReworked(group, index)" />
												<Button label="Update Rejection Qty" severity="secondary" outlined size="small" :disabled="busy" @click="updateRejection(group, index)" />
												<Button label="Complete Rework" icon="pi pi-check" severity="danger" outlined size="small" :disabled="busy" @click="complete(group, index)" />
											</div>
										</td>
										<td class="finishing-table__type">Received</td>
										<td v-for="size in group.sizes" :key="size" class="erp-number">{{ formatQuantity(row.received[size] || 0) }}</td>
										<td class="erp-number finishing-table__row-total">{{ formatQuantity(rowTotal(row.received, group.sizes)) }}</td>
									</tr>
									<tr v-if="editable">
										<td class="finishing-table__type">Rejection</td>
										<td v-for="size in group.sizes" :key="size"><input v-model="inputs[group.key][index].rejection[size]" type="number" min="0" class="finishing-entry-input" :aria-label="`${row.grn_number} ${row.colour} ${size} rejection`" :disabled="busy" /></td>
										<td class="erp-number">{{ formatQuantity(rowTotal(inputs[group.key][index].rejection, group.sizes)) }}</td>
									</tr>
									<tr v-if="editable">
										<td class="finishing-table__type">Reworked</td>
										<td v-for="size in group.sizes" :key="size"><input v-model="inputs[group.key][index].rework[size]" type="number" min="0" class="finishing-entry-input" :aria-label="`${row.grn_number} ${row.colour} ${size} reworked`" :disabled="busy" /></td>
										<td class="erp-number">{{ formatQuantity(rowTotal(inputs[group.key][index].rework, group.sizes)) }}</td>
									</tr>
								</tbody>
							</table>
						</div>
					</section>
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

import { getReworkGroups, updateReworkPartial, updateReworkRejection } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../components/reports/ReportShell.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import RelatedDocumentWorkspaceDialog from "../fabric-store/RelatedDocumentWorkspaceDialog.vue"
import { formatQuantity } from "./finishingViews.js"
import { groupRowInputs, groupRowPayload, reworkRowsError, rowTotal } from "./reports/reworkRules.js"
import { useReportRequest } from "./reports/useReportRequest.js"
import "./finishing.css"

const toast = useToast()
const confirmAction = useActionConfirmation()
const filters = reactive(defaultFilters())
const data = ref({})
const applied = ref({})
const appliedShowReworked = ref(false)
const inputs = ref({})
const busy = ref(false)
const grnOpen = ref(false)
const grnName = ref("")
const { loading, generated, error, run, clear } = useReportRequest()
const canWrite = computed(() => Boolean(data.value.permissions?.can_write))
const editable = computed(() => canWrite.value && !appliedShowReworked.value)
const groups = computed(() => Object.entries(data.value.groups || {}).map(([key, group]) => ({ key, ...group })))
const rowCount = computed(() => groups.value.reduce((sum, group) => sum + group.rows.length, 0))
const receivedTotal = computed(() => groups.value.reduce((sum, group) => sum + group.rows.reduce((inner, row) => inner + rowTotal(row.received, group.sizes), 0), 0))

function defaultFilters() {
	return { lot: "", item: "", colour: "", showReworked: false }
}

function generate(refresh = false) {
	const request = refresh === true ? applied.value : { lot: filters.lot, item: filters.item, colour: filters.colour, show_reworked: filters.showReworked ? 1 : 0 }
	run("", () => getReworkGroups(request), (value) => {
		data.value = value || {}
		applied.value = request
		appliedShowReworked.value = Boolean(request.show_reworked)
		inputs.value = Object.fromEntries(Object.entries(value?.groups || {}).map(([key, group]) => [key, group.rows.map((row) => groupRowInputs(row, group.sizes))]))
	})
}

function payload(group, index, mode) {
	return groupRowPayload(group.rows[index], inputs.value[group.key][index], group.size_attr, mode)
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

function updateRejection(group, index) {
	const rows = payload(group, index, "rejection")
	if (!rows.some((row) => Number(row.rejected) > 0)) return (error.value = "There is nothing changed in this row.")
	const message = reworkRowsError(rows)
	if (message) return (error.value = message)
	mutate(() => updateReworkRejection(rows, 0, group.rows[index].lot), "Rejection quantity updated")
}

function updateReworked(group, index) {
	const rows = payload(group, index, "rework")
	if (!rows.some((row) => Number(row.rework) > 0)) return (error.value = "No reworked quantities entered.")
	const message = reworkRowsError(rows)
	if (message) return (error.value = message)
	confirmAction({ header: "Convert to reworked?", message: "Are you sure want to convert the entered pieces to reworked (Accepted) stock?", acceptLabel: "Convert", acceptIcon: "pi pi-replay", acceptSeverity: "primary", rejectLabel: "No", accept: () => mutate(() => updateReworkPartial(rows, group.rows[index].lot), "Reworked quantity updated") })
}

function complete(group, index) {
	const rows = payload(group, index, "complete")
	const message = reworkRowsError(rows)
	if (message) return (error.value = message)
	confirmAction({ header: "Complete rework?", message: "Are you sure want to final the item? Remaining pieces become Accepted and entered Rejection pieces become Rejected.", acceptLabel: "Complete Rework", acceptIcon: "pi pi-check", rejectLabel: "No", accept: () => mutate(() => updateReworkRejection(rows, 1, group.rows[index].lot), "Rework completed") })
}

function openGrn(name) {
	grnName.value = name
	grnOpen.value = true
}

function reset() {
	Object.assign(filters, defaultFilters())
	data.value = {}
	inputs.value = {}
	clear()
}
</script>

<style scoped>
.finishing-rework { min-width: 0; padding-top: 0; }
.rework-groups__link { padding: 0; color: var(--erp-accent-dark); background: none; border: 0; font: inherit; font-weight: 650; cursor: pointer; }
.rework-groups__link:hover, .rework-groups__link:focus-visible { text-decoration: underline; }
.rework-groups__actions { vertical-align: middle !important; }
.rework-groups__actions { width: 216px; min-width: 216px; }
.rework-groups__actions > div { display: grid; gap: 6px; }
.rework-groups__actions :deep(.p-button) { justify-content: center; white-space: nowrap; }
.rework-groups__table tbody + tbody tr:first-child > * { border-top: 1px solid var(--erp-border-strong); }
</style>
