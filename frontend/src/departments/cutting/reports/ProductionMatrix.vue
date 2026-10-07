<template>
	<div class="production-stack">
		<article
			v-for="(group, groupIndex) in groups"
			:key="`${group.style_no}-${group.lot_no}-${groupIndex}`"
			class="production-card"
		>
			<header class="production-card__header">
				<div class="production-card__identity">
					<span class="production-card__mark" aria-hidden="true"><i class="pi pi-box" /></span>
					<div>
						<p>Item / style</p>
						<h3>{{ group.style_no || "Unspecified item" }}</h3>
						<div class="production-card__meta">
							<span><i class="pi pi-tag" />{{ group.lot_no || "No lot" }}</span>
							<span><i class="pi pi-map-marker" />{{ group.location || "No location" }}</span>
							<span><i class="pi pi-users" />{{ cutterCount(group) }} cutters</span>
						</div>
					</div>
				</div>
				<div class="production-card__totals" aria-label="Group totals">
					<div class="production-total production-total--accent">
						<span>Today</span><strong>{{ number(group.total_sum) }}</strong>
					</div>
					<div class="production-total">
						<span>Planned</span><strong>{{ number(group.total_planned_sum) }}</strong>
					</div>
					<div class="production-total">
						<span>Cumulative</span><strong>{{ number(group.total_received_sum) }}</strong>
					</div>
					<div class="production-total" :class="varianceTone(groupPending(group))">
						<span>Pending</span><strong>{{ signed(groupPending(group)) }}</strong>
					</div>
				</div>
			</header>

			<div class="production-card__legend">
				<span><i class="legend-dot legend-dot--output" />Cut output</span>
				<span class="erp-count-badge">{{ group.items?.length || 0 }} rows</span>
			</div>

			<div class="production-table-wrap" role="region" :aria-label="`${group.style_no || 'Unspecified item'} production matrix`" tabindex="0">
				<table class="production-table">
					<thead>
						<tr class="production-table__bands">
							<th rowspan="2" class="production-table__serial">#</th>
							<th v-for="attribute in visibleAttributes(group)" :key="attribute" rowspan="2">{{ attribute }}</th>
							<th rowspan="2">Cutter</th>
							<th :colspan="group.primary_attribute_values?.length || 1" class="production-table__size-band">Size-wise production</th>
							<th colspan="4" class="production-table__comparison-band">Production comparison</th>
						</tr>
						<tr>
							<th v-if="!group.primary_attribute_values?.length" class="production-table__size">Size</th>
							<th v-for="value in group.primary_attribute_values || []" :key="value" class="production-table__size">{{ value }}</th>
							<th class="production-table__number production-table__today">Today total</th>
							<th class="production-table__number">Planned</th>
							<th class="production-table__number">Cumulative</th>
							<th class="production-table__number">Pending</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, rowIndex) in group.items || []" :key="rowIndex">
							<td class="production-table__serial">{{ rowIndex + 1 }}</td>
							<td v-for="attribute in visibleAttributes(group)" :key="attribute" class="production-table__attribute">
								{{ attributeValue(row, attribute) }}
							</td>
							<td><span class="cutter-chip"><i class="pi pi-user" />{{ row.cutter || "Unassigned" }}</span></td>
							<td v-if="!group.primary_attribute_values?.length" class="production-table__number">—</td>
							<td v-for="value in group.primary_attribute_values || []" :key="value" class="production-table__number production-table__size-cell">
								<strong v-if="Number(row.values?.[value])">{{ quantity(row.values[value]) }}</strong>
								<span v-else class="cell-empty">—</span>
							</td>
							<td class="production-table__number production-table__today production-table__strong">{{ number(row.total_qty) }}</td>
							<td class="production-table__number">{{ number(row.planned) }}</td>
							<td class="production-table__number">{{ number(row.cumulative) }}</td>
							<td class="production-table__number">
								<span class="variance-chip" :class="varianceTone(pending(row))">{{ signed(pending(row)) }}</span>
							</td>
						</tr>
					</tbody>
					<tfoot>
						<tr>
							<td class="production-table__serial"></td>
							<td :colspan="Math.max(1, visibleAttributes(group).length + 1)" class="production-table__total-label">
								Total production
							</td>
							<td v-if="!group.primary_attribute_values?.length" class="production-table__number">0</td>
							<td v-for="value in group.primary_attribute_values || []" :key="value" class="production-table__number">{{ number(sizeTotal(group, value)) }}</td>
							<td class="production-table__number production-table__today">{{ number(group.total_sum) }}</td>
							<td class="production-table__number">{{ number(group.total_planned_sum) }}</td>
							<td class="production-table__number">{{ number(group.total_received_sum) }}</td>
							<td class="production-table__number"><span class="variance-chip" :class="varianceTone(groupPending(group))">{{ signed(groupPending(group)) }}</span></td>
						</tr>
					</tfoot>
				</table>
			</div>
		</article>
	</div>
</template>

<script setup>
import { attributeValue, number, pending, quantity } from "../../../components/reports/reportUtils.js"

defineProps({ groups: { type: Array, default: () => [] } })

function cutterCount(group) {
	return new Set((group.items || []).map((row) => row.cutter || "Unassigned")).size
}

function groupPending(group) {
	return Number(group.total_received_sum || 0) - Number(group.total_planned_sum || 0)
}

function sizeTotal(group, value) {
	return (group.items || []).reduce((total, row) => total + Number(row.values?.[value] || 0), 0)
}

function visibleAttributes(group) {
	return (group.attributes || []).filter((attribute) => !["panel", "panels"].includes(String(attribute).trim().toLowerCase()))
}

function varianceTone(value) {
	if (Number(value) < 0) return "variance--negative"
	if (Number(value) > 0) return "variance--positive"
	return "variance--neutral"
}

function signed(value) {
	const parsed = Number(value || 0)
	return `${parsed > 0 ? "+" : ""}${number(parsed)}`
}
</script>

<style scoped>
.production-stack {
	display: grid;
	gap: var(--erp-space-3);
}

.production-card {
	min-width: 0;
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
}

.production-card__header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-4);
	padding: var(--erp-space-3) var(--erp-space-4);
	background: var(--erp-surface-soft);
	border-bottom: 1px solid var(--erp-border);
}

.production-card__identity {
	display: flex;
	min-width: 0;
	align-items: center;
	gap: 11px;
	flex: 1 1 auto;
}

.production-card__identity > div {
	min-width: 0;
}

.production-card__mark {
	display: grid;
	width: 36px;
	height: 36px;
	flex: 0 0 auto;
	color: var(--erp-accent);
	background: var(--erp-accent-soft);
	border: 1px solid var(--erp-accent-border);
	border-radius: var(--erp-control-radius);
	place-items: center;
}

.production-card__identity p {
	margin: 0 0 2px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.055em;
	text-transform: uppercase;
}

.production-card__identity h3 {
	max-width: min(520px, 42vw);
	margin: 0;
	overflow: hidden;
	color: var(--erp-text);
	font-size: 15px;
	font-weight: 800;
	letter-spacing: -0.015em;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.production-card__meta {
	display: flex;
	min-width: 0;
	flex-wrap: wrap;
	gap: var(--erp-space-2);
	margin-top: 5px;
}

.production-card__meta span {
	display: inline-flex;
	max-width: 260px;
	align-items: center;
	gap: 4px;
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	text-overflow: ellipsis;
	white-space: nowrap;
}

.production-card__meta i {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.production-card__totals {
	display: grid;
	grid-template-columns: repeat(4, minmax(74px, 1fr));
	gap: 7px;
}

.production-total {
	min-width: 76px;
	padding: 6px var(--erp-space-2);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.production-total span {
	display: block;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.025em;
	text-transform: uppercase;
}

.production-total strong {
	display: block;
	margin-top: 2px;
	color: var(--erp-text-secondary);
	font-size: 13px;
	font-variant-numeric: tabular-nums;
}

.production-total--accent {
	border-color: var(--erp-accent-border);
	background: var(--erp-mint);
}

.production-total--accent strong {
	color: var(--erp-accent);
}

.production-total.variance--negative strong {
	color: var(--erp-danger);
}

.production-total.variance--positive strong {
	color: var(--erp-accent);
}

.production-card__legend {
	display: flex;
	align-items: center;
	gap: var(--erp-space-3);
	padding: var(--erp-space-2) var(--erp-space-3);
	border-bottom: 1px solid var(--erp-border-subtle);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.production-card__legend > span {
	display: inline-flex;
	align-items: center;
	gap: 5px;
}

.production-card__legend .erp-count-badge {
	margin-left: auto;
}

.legend-dot {
	width: 7px;
	height: 7px;
	border-radius: 50%;
}

.legend-dot--output {
	background: var(--erp-accent);
}

.production-table-wrap {
	width: 100%;
	overflow: auto;
	scrollbar-gutter: stable;
}

.production-table-wrap:focus-visible {
	outline: 2px solid color-mix(in srgb, var(--erp-accent) 56%, white);
	outline-offset: -2px;
}

.production-table {
	width: 100%;
	min-width: 1060px;
	border-collapse: separate;
	border-spacing: 0;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-caption);
}

.production-table th {
	position: sticky;
	z-index: 2;
	top: 0;
	padding: var(--erp-space-2) 9px;
	border-right: 1px solid var(--erp-border-subtle);
	border-bottom: 1px solid var(--erp-border-strong);
	background: var(--erp-surface-muted);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.025em;
	text-align: left;
	text-transform: uppercase;
	white-space: nowrap;
}

.production-table th:last-child,
.production-table td:last-child {
	border-right: 0;
}

.production-table__bands th {
	z-index: 3;
	padding-top: 7px;
	padding-bottom: 7px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	text-align: center;
}

.production-table thead tr:nth-child(2) th {
	top: 32px;
}

.production-table__bands th[rowspan] {
	text-align: left;
	vertical-align: bottom;
}

.production-table__size-band {
	color: var(--erp-accent-dark) !important;
	background: var(--erp-accent-soft) !important;
}

.production-table__comparison-band {
	color: var(--erp-info) !important;
	background: var(--erp-info-soft) !important;
}

.production-table td {
	min-height: 42px;
	padding: 9px;
	border-right: 1px solid var(--erp-border-subtle);
	border-bottom: 1px solid var(--erp-border-subtle);
	vertical-align: middle;
}

.production-table tbody tr:nth-child(even) td {
	background: var(--erp-surface);
}

.production-table tbody tr:hover td {
	background: var(--erp-surface-hover);
}

.production-table__serial {
	width: 38px;
	color: var(--erp-text-muted);
	text-align: center !important;
}

.production-table__attribute {
	min-width: 105px;
	color: var(--erp-text-secondary);
	font-weight: var(--erp-font-weight-semibold);
}

.production-table__number {
	min-width: 72px;
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.production-table__size {
	min-width: 66px;
	background: var(--erp-accent-soft) !important;
	color: var(--erp-accent-dark) !important;
	text-align: right !important;
}

.production-table__size-cell {
	vertical-align: top !important;
}

.production-table__size-cell > strong {
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-caption);
}

.production-table__today {
	background: var(--erp-success-soft) !important;
	color: var(--erp-accent) !important;
}

.production-table__strong {
	font-size: 13px;
	font-weight: var(--erp-font-weight-bold);
}

.cell-empty {
	color: var(--erp-text-muted);
}

.cutter-chip {
	display: inline-flex;
	align-items: center;
	gap: 4px;
	padding: 3px 7px;
	border: 1px solid var(--erp-accent-border);
	border-radius: var(--erp-pill-radius);
	background: var(--erp-accent-soft);
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	white-space: nowrap;
}

.cutter-chip i {
	font-size: var(--erp-font-size-min);
}

.variance-chip {
	display: inline-flex;
	min-width: 48px;
	justify-content: flex-end;
	padding: 3px 6px;
	border-radius: 6px;
	font-size: var(--erp-font-size-min);
	font-weight: 800;
}

.variance--negative {
	background: var(--erp-danger-soft);
	color: var(--erp-danger);
}

.variance--positive {
	background: var(--erp-success-soft);
	color: var(--erp-accent);
}

.variance--neutral {
	background: var(--erp-surface-muted);
	color: var(--erp-text-muted);
}

.production-table tfoot td {
	padding: 9px;
	border-top: 1px solid var(--erp-accent-border);
	border-right: 1px solid var(--erp-border-subtle);
	background: var(--erp-accent-soft);
	font-weight: 800;
}

.production-table__total-label {
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	letter-spacing: 0.03em;
	text-transform: uppercase;
}

@media (max-width: 960px) {
	.production-card__header {
		align-items: stretch;
		flex-direction: column;
	}

	.production-card__identity h3 {
		max-width: calc(100vw - 150px);
	}

	.production-card__totals {
		grid-template-columns: repeat(4, minmax(0, 1fr));
	}
}

@media (max-width: 600px) {
	.production-card__totals {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}
</style>
