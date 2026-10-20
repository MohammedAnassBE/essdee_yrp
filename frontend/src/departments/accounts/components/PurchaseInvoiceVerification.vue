<template>
	<div class="purchase-invoice-verification">
		<div v-if="verification.length" class="purchase-invoice-verification__work-orders">
			<section v-for="item in verification" :key="item.work_order" class="verification-work-order erp-card">
				<header class="verification-work-order__header">
					<div>
						<span>Work Order verification</span>
						<h2>
							<RouterLink :to="documentRoute('YRP Work Order', item.work_order)">{{ value(item.work_order) }}</RouterLink>
							<template v-if="item.lot"> · <DocumentLink doctype="SD YRP Lot" :name="item.lot" :label="item.lot" /></template>
							<template v-if="item.item_name"> · {{ item.item_name }}</template>
						</h2>
					</div>
					<Button
						v-if="closeConfiguration(item.work_order)"
						:label="closeLabel(closeConfiguration(item.work_order).close_mode)"
						icon="pi pi-lock"
						severity="warn"
						outlined
						@click="openClosePanel(closeConfiguration(item.work_order))"
					/>
				</header>

				<div class="verification-work-order__body">
					<section v-if="item.bills?.length" class="verification-previous-invoices">
						<h3>Previous invoices</h3>
						<div>
							<RouterLink
								v-for="bill in item.bills"
								:key="bill.pi_name"
								:to="documentRoute('YRP Purchase Invoice', bill.pi_name)"
							>
								{{ bill.pi_name }}
							</RouterLink>
						</div>
					</section>

					<div class="verification-table" role="region" tabindex="0" :aria-label="`Verification quantities for ${item.work_order}`">
						<table>
							<thead>
								<tr>
									<th>S.No.</th>
									<th>{{ item.packing_attr || "Colour" }}</th>
									<th v-if="item.is_set_item">{{ item.set_attr || "Part" }}</th>
									<th>Type</th>
									<th v-for="size in item.sizes || []" :key="size" class="verification-table__number">{{ size }}</th>
									<th class="verification-table__number">Total</th>
								</tr>
							</thead>
							<tbody v-for="([colour, colourData], colourIndex) in colourEntries(item)" :key="colour">
								<tr v-for="(definition, rowIndex) in verificationRows" :key="definition.key">
									<td v-if="rowIndex === 0" :rowspan="verificationRows.length">{{ colourIndex + 1 }}</td>
									<td v-if="rowIndex === 0" :rowspan="verificationRows.length">{{ colourLabel(colour) }}</td>
									<td v-if="item.is_set_item && rowIndex === 0" :rowspan="verificationRows.length">
										{{ value(colourData.part) }}
									</td>
									<td>{{ definition.label }}</td>
									<td v-for="size in item.sizes || []" :key="size" class="verification-table__number">
										{{ number(cellValue(colourData.data?.[size], definition.key)) }}
									</td>
									<td class="verification-table__number verification-table__total">
										{{ number(colourTotal(item.total_qty?.[colour], definition.key)) }}
									</td>
								</tr>
							</tbody>
							<tbody v-if="item.grand_total" class="verification-table__grand-total">
								<tr v-for="(definition, index) in verificationRows" :key="definition.key">
									<th
										v-if="index === 0"
										:rowspan="verificationRows.length"
										:colspan="item.is_set_item ? 3 : 2"
									>
										Grand Total
									</th>
									<th>{{ definition.label }}</th>
									<th v-for="size in item.sizes || []" :key="size" class="verification-table__number">
										{{ number(item.grand_total.sizes?.[size]?.[definition.key]) }}
									</th>
									<th class="verification-table__number">{{ number(item.grand_total.total?.[definition.key]) }}</th>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</section>
		</div>
		<div v-else class="purchase-invoice-verification__empty">
			<i class="pi pi-inbox" aria-hidden="true" />
			<span>No Work Order verification quantities are available.</span>
		</div>

		<section v-if="debitSummary.length" class="verification-summary erp-card" aria-labelledby="purchase-invoice-debits">
			<header><h2 id="purchase-invoice-debits">Debits</h2><span>{{ debitSummary.length }}</span></header>
			<div class="verification-summary__table" role="region" tabindex="0" aria-label="Purchase Invoice debits">
				<table>
					<thead><tr><th>Work Order</th><th>Debit</th><th>Debit No</th><th class="verification-table__number">Value</th><th>Status</th><th>Reason</th></tr></thead>
					<tbody>
						<tr v-for="debit in debitSummary" :key="debit.name">
							<td><RouterLink :to="documentRoute('YRP Work Order', debit.work_order)">{{ value(debit.work_order) }}</RouterLink></td>
							<td><DocumentLink doctype="YRP Debit" :name="debit.name" :label="value(debit.name)" /></td>
							<td>{{ value(debit.debit_no) }}</td>
							<td class="verification-table__number">{{ money(debit.debit_value) }}</td>
							<td>{{ value(debit.status) }}</td>
							<td>{{ value(debit.reason) }}</td>
						</tr>
					</tbody>
					<tfoot><tr><th colspan="3">Total</th><th class="verification-table__number">{{ money(debitTotal) }}</th><th colspan="2"></th></tr></tfoot>
				</table>
			</div>
		</section>

		<section v-if="approvals.length" class="verification-summary erp-card" aria-labelledby="purchase-invoice-approvals">
			<header><h2 id="purchase-invoice-approvals">Approvals</h2><span>{{ approvals.length }}</span></header>
			<div class="verification-summary__table" role="region" tabindex="0" aria-label="Purchase Invoice approvals">
				<table>
					<thead><tr><th>Approved by</th><th>Approved on</th><th>Comments</th></tr></thead>
					<tbody>
						<tr v-for="(approval, index) in approvals" :key="`${approval.user}-${approval.approved_time}-${index}`">
							<td><DocumentLink doctype="User" :name="approval.user" :label="value(approval.user)" /></td>
							<td>{{ dateTime(approval.approved_time) }}</td>
							<td>{{ value(approval.comments) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>

	<WorkOrderActionPanel
		v-model:visible="closePanelVisible"
		:mode="selectedCloseMode"
		:work-order="selectedWorkOrder"
		@changed="workOrderChanged"
	/>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import Button from "primevue/button"
import { computed, ref } from "vue"

import { webDocumentPath } from "../../../router/webDocumentRoutes.js"
import WorkOrderActionPanel from "../../fabric-store/WorkOrderActionPanel.vue"

const props = defineProps({
	verification: { type: Array, default: () => [] },
	debitSummary: { type: Array, default: () => [] },
	approvals: { type: Array, default: () => [] },
	workOrders: { type: Array, default: () => [] },
})
const emit = defineEmits(["changed"])
const closePanelVisible = ref(false)
const selectedCloseMode = ref("")
const selectedWorkOrder = ref({})
const verificationRows = [
	{ key: "total_delivered", label: "Total Delivered" },
	{ key: "total_received", label: "Total Received" },
	{ key: "difference", label: "Difference" },
	{ key: "total_billed", label: "Total Billed" },
	{ key: "pending_for_bill", label: "Pending For Bill" },
	{ key: "grn_quantity", label: "GRN Quantity" },
]
const workOrdersByName = computed(() => new Map(props.workOrders.map((workOrder) => [workOrder.name, workOrder])))
const debitTotal = computed(() => props.debitSummary.reduce((total, row) => total + Number(row.debit_value || 0), 0))

function documentRoute(doctype, name) {
	return webDocumentPath(doctype, name).replace(/^\/web(?=\/)/, "")
}

function closeConfiguration(workOrder) {
	const configuration = workOrdersByName.value.get(workOrder)
	return configuration?.close_mode ? configuration : null
}

function closeLabel(mode) {
	return { close: "Close", request_close: "Request Close", approve_close: "Approve Close" }[mode] || "Close"
}

function openClosePanel(workOrder) {
	selectedCloseMode.value = workOrder.close_mode
	selectedWorkOrder.value = {
		name: workOrder.name,
		modified: workOrder.modified,
		expected_delivery_date: workOrder.expected_delivery_date,
	}
	closePanelVisible.value = true
}

function workOrderChanged(payload) {
	emit("changed", payload)
}

function colourEntries(item) {
	return Object.entries(item.colours || {})
}

function colourLabel(colour) {
	return String(colour || "").split("@")[0].trim() || "—"
}

function cellValue(cell = {}, key) {
	if (key === "difference") return Number(cell.total_delivered || 0) - Number(cell.total_received || 0)
	if (key === "pending_for_bill") return Number(cell.total_received || 0) - Number(cell.billed || 0)
	if (key === "total_billed") return cell.billed
	if (key === "grn_quantity") return cell.quantity
	return cell[key]
}

function colourTotal(totals = {}, key) {
	if (key === "difference") return Number(totals.total_delivered || 0) - Number(totals.total_received || 0)
	if (key === "pending_for_bill") return Number(totals.total_received || 0) - Number(totals.total_billed || 0)
	if (key === "grn_quantity") return totals.total_quantity
	return totals[key]
}

function value(input) {
	return input === null || input === undefined || input === "" ? "—" : String(input)
}

function number(input) {
	const numericValue = Number(input || 0)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { maximumFractionDigits: 3 })
		: "—"
}

function money(input) {
	const numericValue = Number(input || 0)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: "—"
}

function dateTime(input) {
	if (!input) return "—"
	const match = String(input).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/)
	return match ? `${match[3]}-${match[2]}-${match[1]}${match[4] ? ` · ${match[4]}:${match[5]}` : ""}` : String(input)
}
</script>

<style scoped>
.purchase-invoice-verification, .purchase-invoice-verification__work-orders { display: grid; min-width: 0; gap: var(--erp-space-3); }
.verification-work-order, .verification-summary { min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.verification-work-order__header { display: flex; min-height: 64px; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.verification-work-order__header > div { display: grid; min-width: 0; gap: 3px; }
.verification-work-order__header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 740; letter-spacing: .045em; text-transform: uppercase; }
.verification-work-order__header h2 { margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-section); text-overflow: ellipsis; white-space: nowrap; }
.verification-work-order a, .verification-summary a { color: var(--erp-accent-hover); text-decoration: none; }
.verification-work-order a:hover, .verification-summary a:hover { text-decoration: underline; }
.verification-work-order__body { display: grid; gap: 10px; padding: 10px; }
.verification-previous-invoices { display: flex; align-items: flex-start; gap: 12px; padding: 9px 11px; border-left: 3px solid var(--erp-accent); background: var(--erp-accent-soft); }
.verification-previous-invoices h3 { margin: 1px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-caption); white-space: nowrap; }
.verification-previous-invoices > div { display: flex; gap: 6px 12px; flex-wrap: wrap; font-size: var(--erp-font-size-caption); }
.verification-table, .verification-summary__table { max-width: 100%; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.verification-table:focus-visible, .verification-summary__table:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.verification-table table, .verification-summary table { width: 100%; min-width: 800px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.verification-table th, .verification-table td, .verification-summary th, .verification-summary td { padding: 8px 9px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.verification-table th, .verification-summary th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; background: var(--erp-surface-muted); }
.verification-table th:last-child, .verification-table td:last-child, .verification-summary th:last-child, .verification-summary td:last-child { border-right: 0; }
.verification-table tbody:last-child tr:last-child > *, .verification-summary tbody tr:last-child td { border-bottom: 0; }
.verification-table__number { text-align: right !important; font-variant-numeric: tabular-nums; }
.verification-table__total { color: var(--erp-accent-hover); font-weight: 760; background: color-mix(in srgb, var(--erp-accent-soft) 34%, white); }
.verification-table__grand-total th { color: var(--erp-text); font-weight: 780; background: var(--erp-accent-soft); }
.verification-summary > header { display: flex; min-height: 46px; align-items: center; justify-content: space-between; padding: 9px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.verification-summary > header h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.verification-summary > header span { padding: 3px 7px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; border: 1px solid var(--erp-border); border-radius: var(--erp-pill-radius); background: var(--erp-surface-muted); }
.verification-summary__table { margin: 10px; }
.verification-summary tfoot th { color: var(--erp-text); background: var(--erp-accent-soft); }
.purchase-invoice-verification__empty { display: grid; min-height: 140px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-panel-radius); place-content: center; justify-items: center; gap: 8px; }
.purchase-invoice-verification__empty i { color: var(--erp-accent); font-size: 1.15rem; }
@media (max-width: 780px) { .verification-work-order__header { align-items: flex-start; flex-direction: column; } .verification-table, .verification-summary__table { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } }
</style>
