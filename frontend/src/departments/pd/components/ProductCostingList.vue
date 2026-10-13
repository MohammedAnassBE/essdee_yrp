<template>
	<section class="pd-media-panel erp-card" aria-labelledby="product-costing-heading">
		<div class="pd-media-panel__heading">
			<div>
				<span class="pd-media-panel__eyebrow">Commercial view</span>
				<h2 id="product-costing-heading">Product Costing</h2>
			</div>
			<RouterLink
				v-if="canCreate && !readonly"
				class="product-costing__new"
				:to="{ name: 'pd-lotwise-item-profit-new', query: { product: productName } }"
			>
				<i class="pi pi-plus" /> New Costing
			</RouterLink>
		</div>

		<div v-if="rows.length" class="product-costing__table-wrap">
			<table>
				<thead>
					<tr>
						<th scope="col">S.No</th>
						<th scope="col">Avg Rate per Pcs</th>
						<th scope="col">Total Qty</th>
						<th scope="col">Profit % (Markdown)</th>
						<th scope="col">Open</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in rows" :key="row.name">
						<td>{{ index + 1 }}</td>
						<td>{{ value(row.avg_rate_per_piece) }}</td>
						<td>{{ value(row.total_qty) }}</td>
						<td>{{ value(row.profit_percent_markdown) }}</td>
						<td><RouterLink :to="{ name: 'pd-lotwise-item-profit', params: { profitId: row.name } }">Open</RouterLink></td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else class="pd-media-empty pd-media-empty--panel"><i class="pi pi-calculator" /><span>There is no costing for this Product</span></div>
	</section>
</template>

<script setup>
import { RouterLink } from "vue-router"

defineProps({
	rows: { type: Array, default: () => [] },
	productName: { type: String, required: true },
	canCreate: { type: Boolean, default: false },
	readonly: { type: Boolean, default: false },
})

function value(entry) {
	return entry === null || entry === undefined || entry === "" ? "—" : entry
}
</script>

<style scoped>
.pd-media-panel { display: grid; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-4); }
.pd-media-panel__heading { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.pd-media-panel__heading > div { display: grid; min-width: 0; gap: 3px; }
.pd-media-panel__heading h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 760; }
.pd-media-panel__eyebrow { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: 0.04em; text-transform: uppercase; }
.pd-media-empty { display: grid; align-content: center; justify-items: center; gap: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.pd-media-empty i { font-size: 1.5rem; }
.pd-media-empty--panel { min-height: 120px; border: 1px dashed var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-costing__new { display: inline-flex; align-items: center; gap: 7px; min-height: 38px; padding: 7px 13px; color: white; border-radius: var(--erp-control-radius); background: var(--erp-accent); font-size: var(--erp-font-size-caption); font-weight: 700; text-decoration: none; }
.product-costing__new:hover { background: var(--erp-accent-hover); }
.product-costing__table-wrap { overflow-x: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.product-costing__table-wrap table { width: 100%; border-collapse: collapse; color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.product-costing__table-wrap th, .product-costing__table-wrap td { padding: 11px 12px; border-bottom: 1px solid var(--erp-border); text-align: left; white-space: nowrap; }
.product-costing__table-wrap th { color: var(--erp-text-secondary); background: var(--erp-bg); font-size: var(--erp-font-size-min); font-weight: 740; text-transform: uppercase; }
.product-costing__table-wrap tbody tr:last-child td { border-bottom: 0; }
.product-costing__table-wrap td a { color: var(--erp-accent-hover); font-weight: 700; text-decoration: none; }
</style>
