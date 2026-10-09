<template>
	<section class="ppo-matrix erp-card" aria-label="Production Order quantities">
		<header class="ppo-matrix__header">
			<div><span>SIZE MATRIX</span><h2>Total Order Quantity</h2></div>
			<strong>{{ formatNumber(totalQuantity) }} pcs</strong>
		</header>
		<div class="ppo-matrix__table-wrap" tabindex="0" role="region" aria-label="Production Order size matrix">
			<table class="ppo-matrix__main" :style="tableStyle">
				<thead><tr><th>Size</th><th v-for="row in rows" :key="`size-${row.size}`">{{ row.size || "—" }}</th><th>Total</th></tr></thead>
				<tbody>
					<tr class="ppo-matrix__row--quantity">
						<th>Quantity</th>
						<td v-for="row in rows" :key="`quantity-${row.size}`">
							<InputNumber v-if="editable" :model-value="number(row.quantity)" :min="0" :max-fraction-digits="0" :use-grouping="false" :input-aria-label="`${row.size} quantity`" fluid @update:model-value="update(row, 'quantity', $event)" />
							<strong v-else>{{ formatNumber(row.quantity) }}</strong>
						</td>
						<td class="ppo-matrix__total">{{ formatNumber(totalQuantity) }}</td>
					</tr>
					<tr class="ppo-matrix__row--ratio">
						<th>Ratio</th>
						<td v-for="row in rows" :key="`ratio-${row.size}`">
							<InputNumber v-if="editable" :model-value="number(row.ratio)" :min="0" :max-fraction-digits="3" :use-grouping="false" :input-aria-label="`${row.size} ratio`" fluid @update:model-value="update(row, 'ratio', $event)" />
							<span v-else>{{ formatNumber(row.ratio) }}</span>
						</td>
						<td class="ppo-matrix__total">{{ formatNumber(totalRatio) }}</td>
					</tr>
					<tr v-for="price in priceRows" :key="price.key" :class="`ppo-matrix__row--${price.key}`">
						<th>{{ price.label }}</th>
						<td v-for="row in rows" :key="`${price.key}-${row.size}`">{{ formatNumber(priceValue(row, price.key)) }}</td>
						<td class="ppo-matrix__empty">—</td>
					</tr>
				</tbody>
			</table>
		</div>

		<section v-if="lotGroups.length" class="ppo-matrix__lots" aria-label="Lotwise Ordered Detail">
			<header><span>ORDERED</span><h3>Lotwise Ordered Detail</h3></header>
			<div class="ppo-matrix__lot-list">
				<article v-for="lot in lotGroups" :key="lot.name" class="ppo-matrix__lot">
					<header>
						<span>Lot</span>
						<button v-if="lotClickable" type="button" class="ppo-matrix__lot-link" :aria-label="`View OCR details for ${lot.name}`" @click="emit('open-lot', lot.name)">
							<strong>{{ lot.name }}</strong><i class="pi pi-arrow-up-right" aria-hidden="true" />
						</button>
						<strong v-else>{{ lot.name }}</strong>
					</header>
					<div class="ppo-matrix__lot-table-wrap">
						<table :style="tableStyle">
							<thead><tr><th>Size</th><th v-for="row in rows" :key="`${lot.name}-${row.size}`">{{ row.size || "—" }}</th><th>Total</th></tr></thead>
							<tbody><tr><th>Quantity</th><td v-for="row in rows" :key="`${lot.name}-quantity-${row.size}`">{{ formatNumber(lot.quantities[row.size]) }}</td><td class="ppo-matrix__total">{{ formatNumber(lotTotal(lot)) }}</td></tr></tbody>
						</table>
					</div>
				</article>
			</div>
		</section>
	</section>
</template>

<script setup>
import InputNumber from "primevue/inputnumber"
import { computed } from "vue"

const props = defineProps({
	rows: { type: Array, default: () => [] },
	ordered: { type: [Array, Object], default: () => [] },
	editable: { type: Boolean, default: false },
	lotClickable: { type: Boolean, default: false },
})
const emit = defineEmits(["update", "open-lot"])
const priceRows = [
	{ key: "wholesale_price", label: "Wholesale Price (Piece)" },
	{ key: "retail_price", label: "Retail Price (Piece)" },
	{ key: "mrp", label: "MRP (Piece)" },
	{ key: "production_order_mrp", label: "Production Order MRP (Piece)" },
]
const totalQuantity = computed(() => props.rows.reduce((total, row) => total + number(row.quantity), 0))
const totalRatio = computed(() => props.rows.reduce((total, row) => total + number(row.ratio), 0))
const tableStyle = computed(() => ({ minWidth: `${Math.max(680, 190 + props.rows.length * 104)}px` }))
const lotGroups = computed(() => {
	const groups = new Map()
	if (Array.isArray(props.ordered)) {
		for (const row of props.ordered) {
			const lot = String(row?.lot || "").trim()
			const size = String(row?.size || "").trim()
			if (!lot || !size) continue
			if (!groups.has(lot)) groups.set(lot, {})
			groups.get(lot)[size] = number(groups.get(lot)[size]) + number(row.quantity)
		}
	} else {
		for (const [lot, quantities] of Object.entries(props.ordered || {})) {
			const values = {}
			for (const [size, entry] of Object.entries(quantities || {})) values[size] = number(entry?.qty ?? entry?.quantity ?? entry)
			groups.set(lot, values)
		}
	}
	return [...groups].map(([name, quantities]) => ({ name, quantities }))
})

function number(value) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0 }
function formatNumber(value) { return number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function priceValue(row, key) { return row.prices?.[key] ?? row[key] }
function lotTotal(lot) { return props.rows.reduce((total, row) => total + number(lot.quantities[row.size]), 0) }
function update(row, field, value) { emit("update", { size: row.size, field, value: number(value) }) }
</script>

<style scoped>
.ppo-matrix { min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.ppo-matrix__header { display: flex; min-height: 54px; align-items: center; justify-content: space-between; gap: 14px; padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface-soft) 80%, white); }
.ppo-matrix__header > div { display: grid; gap: 2px; }
.ppo-matrix__header span, .ppo-matrix__lots > header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 760; letter-spacing: .06em; }
.ppo-matrix__header h2, .ppo-matrix__lots h3 { margin: 0; color: var(--erp-text); font-size: 15px; letter-spacing: -.01em; }
.ppo-matrix__header > strong { color: var(--erp-accent-hover); font-size: 16px; font-variant-numeric: tabular-nums; }
.ppo-matrix__table-wrap, .ppo-matrix__lot-table-wrap { min-width: 0; overflow-x: auto; }
.ppo-matrix table { width: 100%; border-collapse: collapse; }
.ppo-matrix th, .ppo-matrix td { height: 43px; padding: 6px 10px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); text-align: center; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); font-variant-numeric: tabular-nums; }
.ppo-matrix th:last-child, .ppo-matrix td:last-child { border-right: 0; }
.ppo-matrix thead th { height: 34px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 780; letter-spacing: .035em; text-transform: uppercase; background: var(--erp-surface-muted); }
.ppo-matrix tbody th { width: 190px; color: var(--erp-text); font-weight: 720; text-align: left; background: color-mix(in srgb, var(--erp-surface-soft) 72%, white); }
.ppo-matrix tbody tr:hover td { background: color-mix(in srgb, var(--erp-accent-soft) 34%, white); }
.ppo-matrix__row--quantity td { color: var(--erp-accent-hover); font-weight: 760; }
.ppo-matrix__total { color: var(--erp-text) !important; font-weight: 800 !important; background: var(--erp-surface-soft); }
.ppo-matrix__empty { color: var(--erp-text-muted); }
.ppo-matrix :deep(.p-inputnumber) { min-width: 82px; }
.ppo-matrix :deep(.p-inputnumber-input) { height: 32px; padding-inline: 8px; text-align: center; }
.ppo-matrix__lots { border-top: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.ppo-matrix__lots > header { display: grid; gap: 2px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); }
.ppo-matrix__lot-list { display: grid; gap: 9px; padding: 10px; }
.ppo-matrix__lot { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.ppo-matrix__lot > header { display: flex; align-items: baseline; gap: 7px; padding: 7px 10px; border-bottom: 1px solid var(--erp-border); }
.ppo-matrix__lot > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .04em; text-transform: uppercase; }
.ppo-matrix__lot > header strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.ppo-matrix__lot-link { display: inline-flex; align-items: center; gap: 6px; margin: -3px 0; padding: 3px 5px; color: var(--erp-accent-hover); background: transparent; border: 0; border-radius: 6px; cursor: pointer; }
.ppo-matrix__lot-link strong { color: inherit !important; }
.ppo-matrix__lot-link i { font-size: 10px; }
.ppo-matrix__lot-link:hover { background: var(--erp-accent-soft); }
.ppo-matrix__lot-link:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
.ppo-matrix__lot tbody tr:last-child > * { border-bottom: 0; }
@media (max-width: 620px) { .ppo-matrix__header { align-items: flex-start; } .ppo-matrix__header > strong { font-size: 14px; } }
</style>
