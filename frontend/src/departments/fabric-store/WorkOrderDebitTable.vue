<template>
	<div class="work-order-debit-table" role="region" tabindex="0" :aria-label="label">
		<table>
			<thead>
				<tr>
					<th>S.No.</th>
					<th v-if="showWorkOrder">Work Order</th>
					<th>Debit</th>
					<th>Debit Type</th>
					<th>Debit No</th>
					<th class="work-order-debit-table__number">Debit Value</th>
					<th>Reason</th>
					<th>Inspection</th>
					<th>On Close</th>
					<th>Status</th>
					<th v-if="hasApproveColumn">Action</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="(debit, index) in debits" :key="debit.name">
					<td>{{ index + 1 }}</td>
					<td v-if="showWorkOrder"><DocumentLink doctype="YRP Work Order" :name="debit.work_order" :label="value(debit.work_order)" /></td>
					<td><DocumentLink doctype="YRP Debit" :name="debit.name" :label="value(debit.name)" /></td>
					<td>{{ value(debit.debit_type) }}</td>
					<td>{{ value(debit.debit_no) }}</td>
					<td class="work-order-debit-table__number">{{ money(debit.debit_value) }}</td>
					<td>{{ value(debit.reason) }}</td>
					<td>{{ debit.inspection ? "Yes" : "No" }}</td>
					<td>{{ debit.on_close ? "Yes" : "No" }}</td>
					<td><DocumentStatusBadge :label="debit.status || ''" :docstatus="1" /></td>
					<td v-if="hasApproveColumn">
						<Button
							v-if="debit.status !== 'Approved'"
							label="Approve"
							size="small"
							severity="secondary"
							outlined
							:loading="approving === debit.name"
							:disabled="Boolean(approving)"
							@click="emit('approve', debit.name)"
						/>
					</td>
				</tr>
			</tbody>
			<tfoot>
				<tr>
					<th :colspan="showWorkOrder ? 5 : 4">Total</th>
					<th class="work-order-debit-table__number">{{ money(total) }}</th>
					<th :colspan="hasApproveColumn ? 5 : 4"></th>
				</tr>
			</tfoot>
		</table>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"

import DocumentLink from "../../components/common/DocumentLink.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"

const props = defineProps({
	debits: { type: Array, default: () => [] },
	label: { type: String, default: "Debits" },
	showWorkOrder: { type: Boolean, default: false },
	canApprove: { type: Boolean, default: false },
	approving: { type: String, default: "" },
})
const emit = defineEmits(["approve"])
const total = computed(() => props.debits.reduce((sum, debit) => sum + Number(debit.debit_value || 0), 0))
const hasApproveColumn = computed(() => props.canApprove && props.debits.some((debit) => debit.status !== "Approved"))

function value(input) {
	return input === null || input === undefined || input === "" ? "—" : String(input)
}

function money(input) {
	const numericValue = Number(input || 0)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: "—"
}
</script>

<style scoped>
.work-order-debit-table { max-width: 100%; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.work-order-debit-table:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.work-order-debit-table table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.work-order-debit-table th, .work-order-debit-table td { padding: 8px 9px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.work-order-debit-table th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; background: var(--erp-surface-muted); }
.work-order-debit-table th:last-child, .work-order-debit-table td:last-child { border-right: 0; }
.work-order-debit-table tfoot th { color: var(--erp-text); border-bottom: 0; background: var(--erp-accent-soft); }
.work-order-debit-table a { color: var(--erp-accent-hover); text-decoration: none; }
.work-order-debit-table a:hover { text-decoration: underline; }
.work-order-debit-table__number { text-align: right !important; font-variant-numeric: tabular-nums; }
@media (max-width: 1024px), (pointer: coarse) { .work-order-debit-table :deep(.p-button) { min-height: 44px; } }
</style>
