<template>
	<section class="purchase-invoice-items erp-card" aria-label="Purchase Invoice items">
		<div v-if="rows.length" class="purchase-invoice-items__table" role="region" tabindex="0">
			<table v-entry-table="{ fixed: false }">
				<thead>
					<tr>
						<th>Item</th>
						<th>Lot</th>
						<th class="purchase-invoice-items__number">Qty</th>
						<th>UOM</th>
						<th class="purchase-invoice-items__number">Source Rate</th>
						<th class="purchase-invoice-items__number">Rate</th>
						<th>Tax</th>
						<th class="purchase-invoice-items__number">Amount</th>
						<th v-if="erpSyncEnabled">Expense Head</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in rows" :key="row.group_key || `${row.item}-${row.lot}-${index}`">
						<td><strong><DocumentLink doctype="Item" :name="row.item" :label="value(row.item)" /></strong></td>
						<td><DocumentLink doctype="SD YRP Lot" :name="row.lot" :label="value(row.lot)" /></td>
						<td class="purchase-invoice-items__number">{{ number(row.qty) }}</td>
						<td><DocumentLink doctype="UOM" :name="row.uom" :label="value(row.uom)" /></td>
						<td class="purchase-invoice-items__number">{{ money(row.source_rate) }}</td>
						<td class="purchase-invoice-items__number purchase-invoice-items__rate">
							<InputNumber
								v-if="editable"
								:model-value="numeric(row.rate)"
								:input-aria-label="`Rate for ${row.item || `row ${index + 1}`}`"
								:min="0"
								:max-fraction-digits="6"
								:use-grouping="false"
								fluid
								@update:model-value="updateRate(index, $event)"
							/>
							<template v-else>{{ money(row.rate) }}</template>
						</td>
						<td><DocumentLink doctype="YRP Tax Slab" :name="row.tax" :label="value(row.tax)" /></td>
						<td class="purchase-invoice-items__number purchase-invoice-items__amount">{{ money(row.amount) }}</td>
						<td v-if="erpSyncEnabled">{{ value(row.expense_head) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else class="purchase-invoice-items__empty">
			<i class="pi pi-inbox" aria-hidden="true" />
			<span>No grouped items are available.</span>
		</div>
	</section>
</template>

<script setup>
import { vEntryTable } from "../../../components/common/childGrid/entryTable.js"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import InputNumber from "primevue/inputnumber"

const props = defineProps({
	rows: { type: Array, default: () => [] },
	erpSyncEnabled: { type: Boolean, default: false },
	editable: { type: Boolean, default: false },
})
const emit = defineEmits(["update:rows"])

function numeric(input) {
	const numericValue = Number(input)
	return Number.isFinite(numericValue) ? numericValue : 0
}

function updateRate(index, rate) {
	const nextRows = props.rows.map((row, rowIndex) => rowIndex === index
		? { ...row, rate: numeric(rate), amount: numeric(row.qty) * numeric(rate) }
		: row)
	emit("update:rows", nextRows)
}

function value(input) {
	return input === null || input === undefined || input === "" ? "—" : String(input)
}

function number(input) {
	if (input === null || input === undefined || input === "") return "—"
	const numericValue = Number(input)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { maximumFractionDigits: 3 })
		: "—"
}

function money(input) {
	if (input === null || input === undefined || input === "") return "—"
	const numericValue = Number(input)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: "—"
}
</script>

<style scoped>
.purchase-invoice-items { min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.purchase-invoice-items__table { max-width: 100%; overflow: auto; }
.purchase-invoice-items__table:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.purchase-invoice-items table { width: 100%; min-width: 920px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.purchase-invoice-items th, .purchase-invoice-items td { padding: 9px 10px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.purchase-invoice-items th { position: sticky; z-index: 1; top: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .025em; background: var(--erp-surface-muted); }
.purchase-invoice-items th:last-child, .purchase-invoice-items td:last-child { border-right: 0; }
.purchase-invoice-items tbody tr:last-child td { border-bottom: 0; }
.purchase-invoice-items tbody tr:hover { background: color-mix(in srgb, var(--erp-accent-soft) 32%, var(--erp-surface)); }
.purchase-invoice-items td strong { color: var(--erp-text); font-weight: 720; }
.purchase-invoice-items__number { text-align: right !important; font-variant-numeric: tabular-nums; }
.purchase-invoice-items__rate, .purchase-invoice-items__amount { color: var(--erp-accent-hover); font-weight: 740; }
.purchase-invoice-items__rate :deep(.p-inputnumber) { min-width: 104px; }
.purchase-invoice-items__rate :deep(.p-inputnumber-input) { text-align: right; font-variant-numeric: tabular-nums; }
.purchase-invoice-items__empty { display: grid; min-height: 150px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); place-content: center; justify-items: center; gap: 8px; }
.purchase-invoice-items__empty i { color: var(--erp-accent); font-size: 1.15rem; }
@media (max-width: 780px) { .purchase-invoice-items__table { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } }
</style>
