<template>
	<section class="ppo-matrix erp-card" aria-label="Production Order quantities">
		<header class="ppo-matrix__header">
			<div><span>SIZE MATRIX</span><h2>Quantity, ratio & price</h2></div>
			<strong>{{ formatNumber(totalQuantity) }} pcs</strong>
		</header>
		<div class="ppo-matrix__table-wrap" tabindex="0" role="region" aria-label="Production Order size matrix">
			<table>
				<thead><tr><th>Size</th><th>Quantity</th><th>Ratio</th><th>MRP</th><th>Production Order MRP</th><th>Wholesale</th><th>Retail</th></tr></thead>
				<tbody>
					<tr v-for="row in rows" :key="row.size || row.item_variant">
						<th><strong>{{ row.size || "—" }}</strong><small v-if="row.item_variant">{{ row.item_variant }}</small></th>
						<td>
							<InputNumber v-if="editable" :model-value="number(row.quantity)" :min="0" :max-fraction-digits="0" :use-grouping="false" fluid @update:model-value="update(row, 'quantity', $event)" />
							<strong v-else>{{ formatNumber(row.quantity) }}</strong>
						</td>
						<td>
							<InputNumber v-if="editable" :model-value="number(row.ratio)" :min="0" :max-fraction-digits="3" :use-grouping="false" fluid @update:model-value="update(row, 'ratio', $event)" />
							<span v-else>{{ formatNumber(row.ratio) }}</span>
						</td>
						<td>{{ money(row.prices?.mrp ?? row.mrp) }}</td>
						<td>{{ money(row.prices?.production_order_mrp ?? row.production_order_mrp) }}</td>
						<td>{{ money(row.prices?.wholesale_price ?? row.wholesale) }}</td>
						<td>{{ money(row.prices?.retail_price ?? row.retail) }}</td>
					</tr>
				</tbody>
				<tfoot><tr><th>Total</th><th>{{ formatNumber(totalQuantity) }}</th><th>{{ formatNumber(totalRatio) }}</th><td colspan="4"></td></tr></tfoot>
			</table>
		</div>
	</section>
</template>

<script setup>
import InputNumber from "primevue/inputnumber"
import { computed } from "vue"

const props = defineProps({ rows: { type: Array, default: () => [] }, editable: { type: Boolean, default: false } })
const emit = defineEmits(["update"])
const totalQuantity = computed(() => props.rows.reduce((total, row) => total + number(row.quantity), 0))
const totalRatio = computed(() => props.rows.reduce((total, row) => total + number(row.ratio), 0))

function number(value) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0 }
function formatNumber(value) { return number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function money(value) { return `INR ${number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}` }
function update(row, field, value) { emit("update", { size: row.size, field, value: number(value) }) }
</script>

<style scoped>
.ppo-matrix { min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.ppo-matrix__header { display: flex; min-height: 54px; align-items: center; justify-content: space-between; gap: 14px; padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface-soft) 80%, white); }
.ppo-matrix__header > div { display: grid; gap: 2px; }
.ppo-matrix__header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 760; letter-spacing: .06em; }
.ppo-matrix__header h2 { margin: 0; color: var(--erp-text); font-size: 15px; letter-spacing: -.01em; }
.ppo-matrix__header > strong { color: var(--erp-accent-hover); font-size: 16px; font-variant-numeric: tabular-nums; }
.ppo-matrix__table-wrap { min-width: 0; overflow-x: auto; }
.ppo-matrix table { width: 100%; min-width: 840px; border-collapse: collapse; }
.ppo-matrix th, .ppo-matrix td { height: 48px; padding: 7px 12px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); text-align: right; border-bottom: 1px solid var(--erp-border); font-variant-numeric: tabular-nums; }
.ppo-matrix thead th { height: 34px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 760; letter-spacing: .035em; text-transform: uppercase; background: var(--erp-surface-muted); }
.ppo-matrix th:first-child, .ppo-matrix td:first-child { width: 30%; text-align: left; }
.ppo-matrix tbody th { display: table-cell; color: var(--erp-text); }
.ppo-matrix tbody th strong, .ppo-matrix tbody th small { display: block; }
.ppo-matrix tbody th small { max-width: 260px; margin-top: 2px; overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 520; text-overflow: ellipsis; white-space: nowrap; }
.ppo-matrix tbody tr:hover { background: color-mix(in srgb, var(--erp-accent-soft) 34%, white); }
.ppo-matrix tbody td:nth-child(2) strong { color: var(--erp-accent-hover); }
.ppo-matrix tfoot th { color: var(--erp-text); border-bottom: 0; background: var(--erp-surface-soft); }
.ppo-matrix tfoot th:nth-child(2) { color: var(--erp-accent-hover); text-align: right; }
.ppo-matrix tfoot td { border-bottom: 0; background: var(--erp-surface-soft); }
.ppo-matrix :deep(.p-inputnumber) { min-width: 96px; }
.ppo-matrix :deep(.p-inputnumber-input) { height: 34px; text-align: right; }
</style>
