<template>
	<div class="finishing-scroll" role="region" tabindex="0" :aria-label="label">
		<table class="finishing-table series-table">
			<thead>
				<tr>
					<th v-if="!expandAll" class="series-table__toggle"><span class="sr-only">Expand</span></th>
					<th v-if="printable && !expandAll" class="series-table__toggle">Print</th>
					<th>Series No</th>
					<th>Date</th>
					<th>GRN Number</th>
					<th>Lot</th>
					<th>Item</th>
					<th>Colour</th>
					<th v-for="type in types" :key="type" class="erp-number">{{ type }}</th>
					<th class="erp-number">Total</th>
				</tr>
			</thead>
			<tbody>
				<template v-for="row in rows" :key="row.series">
					<tr class="series-table__row" :class="{ 'is-open': isOpen(row) }">
						<td v-if="!expandAll" class="series-table__toggle">
							<button type="button" class="series-table__expand" :aria-expanded="expanded === row.series" :aria-label="`${expanded === row.series ? 'Collapse' : 'Expand'} ${row.series}`" @click="emit('toggle', row.series)">
								<i :class="expanded === row.series ? 'pi pi-chevron-down' : 'pi pi-chevron-right'" aria-hidden="true" />
							</button>
						</td>
						<td v-if="printable && !expandAll" class="series-table__toggle">
							<button type="button" class="series-table__expand" :aria-label="`Print ${row.detail.grn_number}`" :title="`Print ${row.detail.grn_number}`" @click="emit('print', row.detail.grn_number)"><i class="pi pi-print" aria-hidden="true" /></button>
						</td>
						<td><strong>{{ row.series }}</strong></td>
						<td class="series-table__date">{{ formatDate(row.detail.date) }}</td>
						<td><button type="button" class="series-table__link" @click="emit('open-grn', row.detail.grn_number)">{{ row.detail.grn_number }}</button></td>
						<td>{{ row.detail.lot }}</td>
						<td>{{ row.detail.item }}</td>
						<td>{{ row.colour }}</td>
						<td v-for="type in types" :key="type" class="erp-number">{{ formatQuantity(row.values[type] || 0) }}</td>
						<td class="erp-number finishing-table__row-total">{{ formatQuantity(row.total) }}</td>
					</tr>
					<tr v-if="isOpen(row)" class="series-table__detail">
						<td :colspan="7 + types.length + (expandAll ? 0 : 1 + (printable ? 1 : 0))"><div class="finishing-stack series-table__detail-panel"><slot name="detail" :detail="row.detail" :series="row.series" /></div></td>
					</tr>
				</template>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { formatDate } from "../../../components/reports/reportUtils.js"
import { formatQuantity } from "../finishingViews.js"

const props = defineProps({
	rows: { type: Array, default: () => [] },
	types: { type: Array, default: () => [] },
	expanded: { type: String, default: "" },
	label: { type: String, default: "Series results" },
	printable: { type: Boolean, default: false },
	/** Opens every detail row and drops the toggle columns, for Copy Report. */
	expandAll: { type: Boolean, default: false },
})
const emit = defineEmits(["toggle", "open-grn", "print"])
const isOpen = row => props.expandAll || props.expanded === row.series
</script>

<style scoped>
.series-table__toggle { width: 1%; padding: 2px 4px !important; }
.series-table__expand { display: grid; width: 32px; height: 32px; place-items: center; color: var(--erp-text-secondary); background: none; border: 0; border-radius: var(--erp-control-radius); cursor: pointer; }
.series-table__expand:hover, .series-table__expand:focus-visible { color: var(--erp-accent-dark); background: var(--erp-accent-soft); }
.series-table__row.is-open > td { background: color-mix(in srgb, var(--erp-accent-soft) 45%, var(--erp-surface)); }
.series-table__date { font-variant-numeric: tabular-nums; }
.series-table__link { padding: 0; color: var(--erp-accent-dark); background: none; border: 0; font: inherit; font-weight: 650; cursor: pointer; }
.series-table__link:hover, .series-table__link:focus-visible { text-decoration: underline; }
.series-table__detail > td { padding: 10px 12px !important; white-space: normal !important; background: var(--erp-surface-soft); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
