<template>
	<div class="finishing-scroll report-table-frame series-table__frame" role="region" tabindex="0" :aria-label="label">
		<table class="finishing-table report-table series-table">
			<thead>
				<tr>
					<th v-if="!expandAll" class="series-table__toggle series-table__sticky"><span class="sr-only">Expand</span></th>
					<th v-if="printable && !expandAll" class="series-table__toggle series-table__sticky series-table__sticky--print">Print</th>
					<th class="series-table__sticky" :class="seriesStickyClass">Series No</th>
					<th class="report-cell--date">Date</th>
					<th>GRN Number</th>
					<th>Lot</th>
					<th class="report-cell--text">Item</th>
					<th class="report-cell--text">Colour</th>
					<th v-for="type in types" :key="type" class="erp-number report-cell--num">{{ type }}</th>
					<th class="erp-number report-cell--num">Total</th>
				</tr>
			</thead>
			<tbody>
				<template v-for="row in rows" :key="row.series">
					<tr class="series-table__row" :class="{ 'is-open': isOpen(row), 'is-toggleable': !expandAll }" :tabindex="expandAll ? undefined : 0" @click="rowClicked($event, row)" @keydown="rowKeydown($event, row)">
						<td v-if="!expandAll" class="series-table__toggle series-table__sticky">
							<button type="button" class="series-table__expand" :aria-expanded="expanded === row.series" :aria-label="`${expanded === row.series ? 'Collapse' : 'Expand'} ${row.series}`" @click="emit('toggle', row.series)">
								<i :class="expanded === row.series ? 'pi pi-chevron-down' : 'pi pi-chevron-right'" aria-hidden="true" />
							</button>
						</td>
						<td v-if="printable && !expandAll" class="series-table__toggle series-table__sticky series-table__sticky--print">
							<button type="button" class="series-table__expand" :aria-label="`Print ${row.detail.grn_number}`" :title="`Print ${row.detail.grn_number}`" @click="emit('print', row.detail.grn_number)"><i class="pi pi-print" aria-hidden="true" /></button>
						</td>
						<td class="series-table__sticky" :class="seriesStickyClass"><strong>{{ row.series }}</strong></td>
						<td class="report-cell--date">{{ formatDate(row.detail.date) }}</td>
						<td><button type="button" class="series-table__link" @click="emit('open-grn', row.detail.grn_number)">{{ row.detail.grn_number }}</button></td>
						<td>{{ row.detail.lot }}</td>
						<td class="report-cell--text">{{ row.detail.item }}</td>
						<td class="report-cell--text">{{ row.colour }}</td>
						<td v-for="type in types" :key="type" class="erp-number report-cell--num">{{ formatQuantity(row.values[type] || 0) }}</td>
						<td class="erp-number report-cell--num finishing-table__row-total report-cell--last-column">{{ formatQuantity(row.total) }}</td>
					</tr>
					<tr v-if="isOpen(row)" class="series-table__detail">
						<td class="report-cell--last-column" :colspan="7 + types.length + (expandAll ? 0 : 1 + (printable ? 1 : 0))"><div class="finishing-stack series-table__detail-panel"><slot name="detail" :detail="row.detail" :series="row.series" /></div></td>
					</tr>
				</template>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { formatDate } from "../../../components/reports/reportUtils.js"
import { isRowToggleClick, isRowToggleKey } from "../../../utils/rowToggle.js"
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
const seriesStickyClass = computed(() => props.expandAll ? "" : props.printable ? "series-table__sticky--after-two" : "series-table__sticky--after-one")

function rowClicked(event, row) {
	if (!props.expandAll && isRowToggleClick(event)) emit("toggle", row.series)
}

function rowKeydown(event, row) {
	if (props.expandAll || !isRowToggleKey(event)) return
	event.preventDefault()
	emit("toggle", row.series)
}
</script>

<style scoped>
.series-table__toggle { width: 40px; min-width: 40px; max-width: 40px; padding: 2px 4px !important; }
.series-table__sticky { position: sticky; left: 0; z-index: 1; background: var(--erp-surface); }
.series-table__sticky--print, .series-table__sticky--after-one { left: 40px; }
.series-table__sticky--after-two { left: 80px; }
.series-table__sticky--after-one, .series-table__sticky--after-two { box-shadow: inset -1px 0 0 var(--erp-border); }
thead th.series-table__sticky { z-index: 3; background: var(--erp-surface-muted); }
.series-table__row.is-toggleable { cursor: pointer; }
.series-table__row.is-toggleable:not(.is-open):hover > td { background: var(--erp-surface-soft); }
.series-table__row:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: -2px; }
.series-table__expand { display: grid; width: 32px; height: 32px; place-items: center; color: var(--erp-text-secondary); background: none; border: 0; border-radius: var(--erp-control-radius); cursor: pointer; }
.series-table__expand:hover, .series-table__expand:focus-visible { color: var(--erp-accent-dark); background: var(--erp-accent-soft); }
.series-table__row.is-open > td { background: color-mix(in srgb, var(--erp-accent-soft) 45%, var(--erp-surface)); }
.series-table__link { padding: 0; color: var(--erp-accent-dark); background: none; border: 0; font: inherit; font-weight: 650; cursor: pointer; }
.series-table__link:hover, .series-table__link:focus-visible { text-decoration: underline; }
.series-table__detail > td { padding: 10px 12px !important; white-space: normal !important; background: var(--erp-surface-soft); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
