<template>
	<div v-for="(group, groupIndex) in groups" :key="groupIndex" class="erp-table-wrap completion-wrap">
		<div v-if="!group.is_set_item && panelNames(group).length" class="panel-strip"><strong>Panels</strong><span v-for="panel in panelNames(group)" :key="panel">{{ panel }}</span></div>
		<table class="erp-data-table report-table completion-table">
			<thead><tr><th class="report-cell--num">#</th><th v-for="attribute in group.attributes || []" :key="attribute" class="report-cell--text">{{ attribute }}</th><th v-for="size in group.primary_attribute_values || []" :key="size" class="erp-number report-cell--num">{{ size }}</th><th class="erp-number report-cell--num">Total</th><th v-if="showAverages" class="erp-number report-cell--num">Avg piece wt.</th><th v-if="showAverages" class="erp-number report-cell--num">Avg reqd. wt.</th><th v-if="group.is_set_item" class="report-cell--text">Panels</th></tr></thead>
			<tbody>
				<tr v-for="(row, rowIndex) in group.items || []" :key="rowIndex">
					<td class="report-cell--num">{{ rowIndex + 1 }}</td>
					<td v-for="attribute in group.attributes || []" :key="attribute" class="report-cell--text">{{ attributeValue(row, attribute) }}</td>
					<td v-for="size in group.primary_attribute_values || []" :key="size" class="erp-number report-cell--num">{{ quantity(row.values?.[size]) }}</td>
					<td class="erp-number report-cell--num cell-strong" :class="lastColumnClass(group, 'total')">{{ quantity(row.total_qty) }}</td>
					<td v-if="showAverages" class="erp-number report-cell--num">{{ averageFor(row, averagePieceWeight) }}</td>
					<td v-if="showAverages" class="erp-number report-cell--num" :class="lastColumnClass(group, 'average')">{{ averageFor(row, averageRequiredWeight) }}</td>
					<td v-if="group.is_set_item" class="report-cell--text report-cell--last-column"><div class="panel-chips"><span v-for="panel in rowPanels(group, row)" :key="panel" class="panel-chip">{{ panel }}</span></div></td>
				</tr>
				<tr class="report-total-row"><td class="report-cell--text">Total</td><td v-for="attribute in group.attributes || []" :key="attribute"></td><td v-for="size in group.primary_attribute_values || []" :key="size" class="erp-number report-cell--num">{{ quantity(group.total_qty?.[size]) }}</td><td class="erp-number report-cell--num" :class="lastColumnClass(group, 'total')">{{ quantity(totalQty) }}</td><td v-if="showAverages"></td><td v-if="showAverages" :class="lastColumnClass(group, 'average')"></td><td v-if="group.is_set_item" class="report-cell--last-column"></td></tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { attributeValue, number, quantity, rowColour } from "../../../components/reports/reportUtils.js"

const props = defineProps({
	groups: { type: Array, default: () => [] },
	totalQty: { type: [Number, String], default: 0 },
	averagePieceWeight: { type: Object, default: () => ({}) },
	averageRequiredWeight: { type: Object, default: () => ({}) },
	showAverages: { type: Boolean, default: false },
})

function panelNames(group) { return group?.[group.stiching_attr] || [] }
function rowPanels(group, row) { return group?.[group.stiching_attr]?.[row?.attributes?.[group.set_item_attr]] || [] }
function lastColumnClass(group, column) {
	const last = group?.is_set_item ? "panels" : props.showAverages ? "average" : "total"
	return { "report-cell--last-column": last === column }
}
function averageFor(row, values) {
	const value = values?.[rowColour(row)]
	return value === undefined || value === null ? "—" : number(value, 4)
}
</script>

<style scoped>
.completion-wrap + .completion-wrap {
	margin-top: 10px;
}

.completion-table {
	min-width: 760px;
}

.panel-strip {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 6px;
	padding: var(--erp-space-2) 10px;
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.panel-strip strong {
	color: var(--erp-text);
}

.panel-strip span,
.panel-chip {
	display: inline-flex;
	padding: 2px 6px;
	border-radius: var(--erp-pill-radius);
	background: var(--erp-accent-soft);
	color: #315e4c;
	font-size: var(--erp-font-size-min);
}

.panel-chips {
	display: flex;
	min-width: 220px;
	flex-wrap: wrap;
	gap: var(--erp-space-1);
}

.cell-strong {
	font-weight: 800;
}
</style>
