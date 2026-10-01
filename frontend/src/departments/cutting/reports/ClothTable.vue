<template>
	<div class="erp-table-wrap">
		<table class="erp-data-table cloth-table">
			<thead><tr><th>#</th><th>Cloth</th><th>Cloth type</th><th>Colour</th><th>Dia</th><th class="erp-number">Required wt.</th><th class="erp-number">Received wt.</th><th class="erp-number">Used wt.</th><th class="erp-number">Balance wt.</th></tr></thead>
			<tbody>
				<tr v-for="(row, index) in rows" :key="index"><td>{{ index + 1 }}</td><td>{{ row.cloth_item_variant || "—" }}</td><td>{{ row.cloth_type || "—" }}</td><td>{{ row.colour || "—" }}</td><td>{{ row.dia || "—" }}</td><td class="erp-number">{{ number(row.required_weight, 3) }}</td><td class="erp-number">{{ number(row.weight, 3) }}</td><td class="erp-number">{{ number(row.used_weight, 3) }}</td><td class="erp-number">{{ number(row.balance_weight, 3) }}</td></tr>
				<tr v-if="totals" class="cloth-total"><td>Total</td><td colspan="4"></td><td class="erp-number">{{ number(totals.required, 3) }}</td><td class="erp-number">{{ number(totals.received, 3) }}</td><td class="erp-number">{{ number(totals.used, 3) }}</td><td class="erp-number">{{ number(totals.balance, 3) }}</td></tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { number } from "./reportUtils.js"
defineProps({ rows: { type: Array, default: () => [] }, totals: { type: Object, default: null } })
</script>

<style scoped>
.cloth-table { min-width: 880px; }
.cloth-total td { font-weight: 800; background: #f0f7f3; }
</style>
