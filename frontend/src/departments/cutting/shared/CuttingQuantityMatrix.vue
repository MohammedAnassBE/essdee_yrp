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
			<div class="quantity-table-scroll" role="region" tabindex="0" :aria-label="`Planned quantities group ${groupIndex + 1}`">
				<table>
					<thead>
						<tr>
							<th class="quantity-row-heading" scope="col">Item / Attributes</th>
							<th v-for="size in sizes(group)" :key="size" scope="col">{{ size }}</th>
							<th scope="col">Total</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in group.items || []" :key="row._row_key">
							<th class="quantity-row-heading" scope="row">
								<strong>{{ row.name }}</strong>
								<span class="quantity-attributes">
									<span v-for="(value, key) in row.attributes || {}" :key="key" class="quantity-attribute">
										<small>{{ key }}</small>{{ value }}
									</span>
								</span>
							</th>
							<td v-for="size in sizes(group)" :key="size" class="quantity-cell">
								<InputNumber
									:model-value="quantity(row, size)"
									:min="0"
									:max-fraction-digits="2"
									:use-grouping="false"
									:disabled="disabled"
									:aria-label="`${row.name} ${size} quantity`"
									fluid
									@update:model-value="updateQuantity(row._row_key, size, $event)"
								/>
							</td>
							<td class="quantity-total">{{ formatNumber(rowTotal(row, group)) }}</td>
						</tr>
					</tbody>
					<tfoot>
						<tr>
							<th scope="row">Total</th>
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

const props = defineProps({
	groups: { type: Array, default: () => [] },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update"])
const rowCount = computed(() => props.groups.reduce((count, group) => count + (group.items?.length || 0), 0))

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
	padding: 4px 9px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	background: var(--erp-surface-muted);
	border: 1px solid var(--erp-border);
	border-radius: 999px;
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
.quantity-table-scroll { max-width: 100%; overflow: auto; }
.quantity-table-scroll:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
table { width: 100%; min-width: 780px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
th, td { min-width: 108px; padding: 9px 10px; text-align: right; border-bottom: 1px solid var(--erp-border); }
thead th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; background: var(--erp-surface-muted); }
.quantity-row-heading { position: sticky; z-index: 1; left: 0; min-width: 260px; max-width: 340px; text-align: left; background: var(--erp-surface); }
thead .quantity-row-heading { z-index: 2; background: var(--erp-surface-muted); }
.quantity-row-heading > strong { display: block; overflow: hidden; color: var(--erp-text); text-overflow: ellipsis; white-space: nowrap; }
.quantity-attributes { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.quantity-attribute { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; color: var(--erp-accent-hover); background: var(--erp-accent-soft); border: 1px solid var(--erp-accent-border); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 650; }
.quantity-attribute small { color: var(--erp-text-muted); font-size: inherit; font-weight: 600; }
.quantity-cell :deep(.p-inputnumber-input) { height: 34px; text-align: right; }
.quantity-total { color: var(--erp-accent-dark); font-weight: 780; font-variant-numeric: tabular-nums; }
tfoot th, tfoot td { color: var(--erp-text); font-weight: 760; background: var(--erp-accent-soft); border-bottom: 0; }
tfoot th { text-align: left; }
@media (max-width: 780px) { .quantity-table-scroll { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } }
</style>
