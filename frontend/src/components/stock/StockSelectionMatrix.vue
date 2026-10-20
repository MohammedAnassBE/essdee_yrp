<template>
	<section class="selection-matrix">
		<header class="selection-matrix__header">
			<div><span>Available stock</span><h3>Select by item attributes</h3><p>Choose the exact attribute quantities to include in this transaction.</p></div>
			<div class="selection-matrix__summary"><strong>{{ modelValue.length }}</strong><span>selected</span></div>
		</header>

		<div v-if="groups.length" class="selection-matrix__groups">
			<article v-for="(group, groupIndex) in groups" :key="groupKey(group, groupIndex)" class="selection-matrix__group">
				<header><div><i class="pi pi-th-large"></i><strong>{{ group.primary_attribute ? `${group.primary_attribute} matrix` : "Quantity" }}</strong></div><span>{{ group.items?.length || 0 }} rows</span></header>
				<div class="selection-matrix__scroll" role="region" tabindex="0" :aria-label="`Available stock group ${groupIndex + 1}`">
					<table>
						<thead><tr><th>#</th><th>Item</th><th>Lot</th><th>Received Type</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="value in primaryValues(group)" :key="value" class="selection-matrix__number">{{ valueLabel(group, value) }}</th><th v-if="group.primary_attribute" class="selection-matrix__number">Available</th><th>UOM</th></tr></thead>
						<tbody>
							<tr v-for="(row, rowIndex) in group.items || []" :key="`${row.name}-${rowIndex}`">
								<td class="selection-matrix__index">{{ rowIndex + 1 }}</td>
								<td class="selection-matrix__item"><strong>{{ row.name }}</strong><small v-if="row.primary_attribute">{{ row.primary_attribute }}</small></td>
								<td>{{ row.lot || "—" }}</td><td>{{ row.received_type || "—" }}</td>
								<td v-for="attribute in group.attributes || []" :key="attribute"><span class="selection-matrix__attribute">{{ row.attributes?.[attribute] || "—" }}</span></td>
								<td v-for="value in primaryValues(group)" :key="value" class="selection-matrix__number">
									<label v-if="cell(row, value).selection_key" class="selection-matrix__cell" :class="{ 'selection-matrix__cell--selected': isSelected(cell(row, value).selection_key) }">
										<input type="checkbox" :checked="isSelected(cell(row, value).selection_key)" :aria-label="`Select ${row.name}, ${valueLabel(group, value)}, quantity ${formatQty(cell(row, value).qty)}`" @change="toggle(cell(row, value).selection_key)" />
										<strong>{{ formatQty(cell(row, value).qty) }}</strong>
									</label>
									<span v-else class="selection-matrix__missing">—</span>
								</td>
								<td v-if="group.primary_attribute" class="selection-matrix__number selection-matrix__total">{{ formatQty(rowTotal(row)) }}</td><td>{{ row.default_uom || "—" }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</article>
		</div>
		<div v-else class="selection-matrix__empty"><i class="pi pi-inbox"></i><span>No positive stock balance is available for this Cutting Plan.</span></div>
	</section>
</template>

<script setup>
const props = defineProps({ groups: { type: Array, default: () => [] }, modelValue: { type: Array, default: () => [] } })
const emit = defineEmits(["update:modelValue"])

function primaryValues(group) { return group.primary_attribute ? (group.primary_attribute_values || []) : ["default"] }
function valueLabel(group, value) { return group.primary_attribute ? value : "Quantity" }
function cell(row, value) { return row.values?.[value] || {} }
function isSelected(key) { return props.modelValue.includes(key) }
function toggle(key) { emit("update:modelValue", isSelected(key) ? props.modelValue.filter((value) => value !== key) : [...props.modelValue, key]) }
function rowTotal(row) { return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0) }
function formatQty(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 }) }
function groupKey(group, index) { return `${group.primary_attribute || "quantity"}-${(group.attributes || []).join("-")}-${index}` }
</script>

<style scoped>
.selection-matrix {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.selection-matrix__header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-4);
	padding: 10px var(--erp-space-3);
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.selection-matrix__header > div:first-child {
	display: grid;
	gap: 2px;
}

.selection-matrix__header > div:first-child > span {
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.055em;
	text-transform: uppercase;
}

.selection-matrix__header h3 {
	margin: 0;
	color: var(--erp-text);
	font-size: 14px;
}

.selection-matrix__header p {
	margin: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.selection-matrix__summary {
	display: grid;
	min-width: 58px;
	justify-items: center;
	padding: 6px 10px;
	border-radius: var(--erp-control-radius);
	background: var(--erp-accent-soft);
	color: var(--erp-accent);
}

.selection-matrix__summary strong {
	font-size: 14px;
}

.selection-matrix__summary span {
	font-size: var(--erp-font-size-min);
	text-transform: uppercase;
}

.selection-matrix__groups {
	display: grid;
	max-height: 470px;
	overflow: auto;
	gap: 10px;
	padding: 10px;
	background: var(--erp-surface-soft);
}

.selection-matrix__group {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.selection-matrix__group > header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: var(--erp-space-2) 10px;
	border-bottom: 1px solid var(--erp-border);
}

.selection-matrix__group > header > div {
	display: flex;
	align-items: center;
	gap: 7px;
}

.selection-matrix__group > header i {
	color: var(--erp-accent);
	font-size: var(--erp-font-size-caption);
}

.selection-matrix__group > header strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.selection-matrix__group > header span,
.selection-matrix__item small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.selection-matrix__scroll {
	overflow: auto;
}

.selection-matrix__scroll:focus-visible {
	outline: 2px solid var(--erp-accent-dark);
	outline-offset: -2px;
}

.selection-matrix table {
	width: 100%;
	min-width: 840px;
	border-collapse: separate;
	border-spacing: 0;
	font-size: var(--erp-font-size-caption);
}

.selection-matrix th {
	position: sticky;
	z-index: 1;
	top: 0;
	padding: var(--erp-space-2) 9px;
	border-bottom: 1px solid var(--erp-border-strong);
	background: var(--erp-surface-muted);
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	text-align: left;
	text-transform: uppercase;
	white-space: nowrap;
}

.selection-matrix td {
	padding: var(--erp-space-2) 9px;
	border-bottom: 1px solid var(--erp-border-subtle);
	color: var(--erp-text-secondary);
	vertical-align: middle;
	white-space: nowrap;
}

.selection-matrix tbody tr:last-child td {
	border-bottom: 0;
}

.selection-matrix tbody tr:hover td {
	background: color-mix(in srgb, var(--erp-accent) 3%, var(--erp-surface));
}

.selection-matrix__index {
	color: var(--erp-text-muted) !important;
	text-align: center;
}

.selection-matrix__item {
	display: grid;
	min-width: 170px;
	gap: 1px;
	white-space: normal !important;
}

.selection-matrix__item strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.selection-matrix__attribute {
	display: inline-flex;
	padding: 3px 7px;
	border: 1px solid var(--erp-border);
	border-radius: 6px;
	background: var(--erp-surface-soft);
	font-size: var(--erp-font-size-min);
}

.selection-matrix__number {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.selection-matrix__cell {
	display: inline-flex;
	min-width: 66px;
	align-items: center;
	justify-content: flex-end;
	gap: 6px;
	padding: 5px 7px;
	border: 1px solid var(--erp-border-strong);
	border-radius: 7px;
	background: var(--erp-surface);
	cursor: pointer;
}

.selection-matrix__cell:hover,
.selection-matrix__cell--selected {
	border-color: var(--erp-accent-border);
	background: var(--erp-mint);
	color: var(--erp-accent);
}

.selection-matrix__cell:focus-within {
	border-color: var(--erp-accent);
	background: var(--erp-accent-soft);
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 14%, transparent);
	outline-offset: 1px;
}

.selection-matrix__cell input {
	width: 13px;
	height: 13px;
	margin: 0;
	accent-color: var(--erp-accent);
}

.selection-matrix__cell strong {
	font-size: var(--erp-font-size-caption);
}

.selection-matrix__missing {
	color: var(--erp-text-muted);
}

.selection-matrix__total {
	color: var(--erp-accent) !important;
	font-weight: 800;
}

.selection-matrix__empty {
	display: grid;
	align-items: center;
	justify-content: center;
	justify-items: center;
	gap: 7px;
	min-height: 132px;
	padding: 30px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	text-align: center;
	background: var(--erp-surface);
}

.selection-matrix__empty i {
	color: var(--erp-accent);
	font-size: 1.2rem;
}

@media (max-width: 700px) {
	.selection-matrix__scroll {
		-webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
		mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
	}

	.selection-matrix__header {
		align-items: flex-start;
		flex-direction: column;
	}

	.selection-matrix__summary {
		grid-auto-flow: column;
		justify-content: start;
		gap: 5px;
	}
}
</style>
