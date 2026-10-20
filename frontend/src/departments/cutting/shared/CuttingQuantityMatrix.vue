<template>
	<section class="cutting-quantity-matrix" aria-label="Cutting quantities">
		<header class="cutting-quantity-matrix__header">
			<div>
				<h2>Planned Quantities</h2>
				<p>Enter the quantity to cut for each colour and size.</p>
			</div>
			<span class="cutting-quantity-matrix__count">{{ rowCount }} {{ rowCount === 1 ? "row" : "rows" }}</span>
		</header>

		<div v-if="!groups.length" class="cutting-quantity-matrix__empty">
			<i class="pi pi-table" aria-hidden="true" />
			<strong>Select a Lot to load quantities</strong>
		</div>

		<article v-for="(group, groupIndex) in groups" v-else :key="groupIndex" class="quantity-group">
			<p v-if="itemSections(group).length === 1" class="quantity-group-title">
				<span>Item</span><strong>{{ itemSections(group)[0].name }}</strong>
			</p>
			<div class="quantity-table-scroll" role="region" tabindex="0" :aria-label="`Planned quantities group ${groupIndex + 1}`">
				<table>
					<thead>
						<tr>
							<th class="quantity-serial" scope="col">S.No.</th>
							<th v-for="attribute in groupAttributes(group)" :key="attribute" class="quantity-text-cell" scope="col">{{ attribute }}</th>
							<th v-for="size in sizes(group)" :key="size" class="quantity-cell" scope="col">{{ size }}</th>
							<th scope="col">Total</th>
						</tr>
					</thead>
					<tbody v-for="(section, sectionIndex) in itemSections(group)" :key="section.name">
						<tr v-if="itemSections(group).length > 1" class="quantity-item-row">
							<th :colspan="groupAttributes(group).length + sizes(group).length + 2" scope="rowgroup">{{ section.name }}</th>
						</tr>
						<tr v-for="(row, rowIndex) in section.rows" :key="row._row_key">
							<td class="quantity-serial">{{ rowNumber(group, sectionIndex, rowIndex) }}</td>
							<td v-for="attribute in groupAttributes(group)" :key="attribute" class="quantity-text-cell">{{ row.attributes?.[attribute] || "—" }}</td>
							<td v-for="size in sizes(group)" :key="size" class="quantity-cell">
								<InputNumber
									:model-value="quantity(row, size)"
									:min="0"
									:max-fraction-digits="2"
									:use-grouping="false"
									:disabled="disabled"
									:aria-label="`${groupAttributes(group).map((attribute) => row.attributes?.[attribute]).filter(Boolean).join(' ') || row.name} ${size} quantity`"
									fluid
									@update:model-value="updateQuantity(row._row_key, size, $event)"
								/>
							</td>
							<td class="quantity-total">{{ formatNumber(rowTotal(row, group)) }}</td>
						</tr>
					</tbody>
					<tfoot>
						<tr>
							<th :colspan="groupAttributes(group).length + 1" scope="row">Total</th>
							<td v-for="size in sizes(group)" :key="size">{{ formatNumber(sizeTotal(group, size)) }}</td>
							<td>{{ formatNumber(groupTotal(group)) }}</td>
						</tr>
					</tfoot>
				</table>
			</div>
		</article>
	</section>
</template>

<script setup>
import InputNumber from "primevue/inputnumber"
import { computed } from "vue"

import { groupAttributes, itemSections } from "./quantityMatrixLayout.js"

const props = defineProps({
	groups: { type: Array, default: () => [] },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update"])
const rowCount = computed(() => props.groups.reduce((count, group) => count + (group.items?.length || 0), 0))

function rowNumber(group, sectionIndex, rowIndex) {
	return itemSections(group).slice(0, sectionIndex).reduce((count, section) => count + section.rows.length, 0) + rowIndex + 1
}

function sizes(group) {
	return group.primary_attribute_values || Object.keys(group.items?.[0]?.values || {})
}

function quantity(row, size) {
	const value = row.values?.[size]
	return Number(value?.qty ?? value ?? 0)
}

function rowTotal(row, group) {
	return sizes(group).reduce((total, size) => total + quantity(row, size), 0)
}

function sizeTotal(group, size) {
	return (group.items || []).reduce((total, row) => total + quantity(row, size), 0)
}

function groupTotal(group) {
	return sizes(group).reduce((total, size) => total + sizeTotal(group, size), 0)
}

function formatNumber(value) {
	return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function updateQuantity(rowKey, size, value) {
	emit("update", { rowKey, size, quantity: Number(value || 0) })
}
</script>

<style scoped>
.cutting-quantity-matrix {
	display: grid;
	gap: var(--erp-space-3);
	min-width: 0;
}

.cutting-quantity-matrix__header {
	display: flex;
	align-items: flex-end;
	justify-content: space-between;
	gap: var(--erp-space-3);
}

.cutting-quantity-matrix__header h2 {
	margin: 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
	font-weight: 760;
}

.cutting-quantity-matrix__header p {
	margin: 4px 0 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.cutting-quantity-matrix__count {
	flex: 0 0 auto;
	padding: 4px 9px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	background: var(--erp-surface-muted);
	border: 1px solid var(--erp-border);
	border-radius: 999px;
	white-space: nowrap;
}

.cutting-quantity-matrix__empty {
	display: grid;
	min-height: 160px;
	color: var(--erp-text-muted);
	background: var(--erp-surface-muted);
	border: 1px dashed var(--erp-border-strong);
	border-radius: var(--erp-panel-radius);
	place-items: center;
	align-content: center;
	gap: 10px;
}

.cutting-quantity-matrix__empty i { color: var(--erp-accent); font-size: 1.25rem; }
.cutting-quantity-matrix__empty strong { font-size: var(--erp-font-size-caption); }
.quantity-group { min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); overflow: hidden; }
.quantity-group-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; margin: 0; padding: 10px; overflow-wrap: anywhere; }
.quantity-group-title > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.quantity-group-title > strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.quantity-table-scroll { max-width: 100%; overflow: auto; }
.quantity-table-scroll:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
table { width: 100%; min-width: 780px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--erp-border); }
thead th { color: var(--erp-text-secondary); font-size: var(--erp-font-size-min); font-weight: 700; white-space: nowrap; letter-spacing: 0.035em; background: var(--erp-surface-muted); }
.quantity-serial { width: 56px; min-width: 56px; }
.quantity-text-cell { white-space: nowrap; }
.quantity-cell { min-width: 96px; text-align: right; font-variant-numeric: tabular-nums; }
thead th:last-child, .quantity-total { min-width: 88px; text-align: right; }
.quantity-item-row th { color: var(--erp-text); background: var(--erp-surface-muted); overflow-wrap: anywhere; }
.quantity-cell :deep(.p-inputnumber-input) { height: 34px; text-align: right; font-variant-numeric: tabular-nums; }
.quantity-total { color: var(--erp-accent-dark); font-weight: 780; font-variant-numeric: tabular-nums; }
tfoot th, tfoot td { color: var(--erp-text); font-weight: 760; background: var(--erp-accent-soft); border-bottom: 0; }
tfoot td { text-align: right; font-variant-numeric: tabular-nums; }
tfoot th { text-align: left; }
@media (max-width: 780px) { .quantity-table-scroll { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } }
</style>
