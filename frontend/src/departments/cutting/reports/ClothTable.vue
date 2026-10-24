<template>
	<div class="erp-table-wrap">
		<table class="erp-data-table report-table cloth-table">
			<thead><tr><th class="report-cell--num">#</th><th class="report-cell--text">Cloth</th><th class="report-cell--text">Cloth type</th><th class="report-cell--text">Colour</th><th class="report-cell--text">Dia</th><th class="erp-number report-cell--num">Required wt.</th><th class="erp-number report-cell--num">Received wt.</th><th class="erp-number report-cell--num">Used wt.</th><th class="erp-number report-cell--num">Balance wt.</th></tr></thead>
			<tbody>
				<tr v-for="(row, index) in rows" :key="index"><td class="report-cell--num">{{ index + 1 }}</td><td class="report-cell--text">{{ row.cloth_item_variant || "—" }}</td><td class="report-cell--text">{{ row.cloth_type || "—" }}</td><td class="report-cell--text">{{ row.colour || "—" }}</td><td class="report-cell--text">{{ row.dia || "—" }}</td><td class="erp-number report-cell--num">{{ number(row.required_weight, 3) }}</td><td class="erp-number report-cell--num">{{ number(row.weight, 3) }}</td><td class="erp-number report-cell--num">{{ number(row.used_weight, 3) }}</td><td class="erp-number report-cell--num report-cell--last-column">{{ number(row.balance_weight, 3) }}</td></tr>
				<tr v-if="totals" class="report-total-row"><td class="report-cell--text">Total</td><td colspan="4"></td><td class="erp-number report-cell--num">{{ number(totals.required, 3) }}</td><td class="erp-number report-cell--num">{{ number(totals.received, 3) }}</td><td class="erp-number report-cell--num">{{ number(totals.used, 3) }}</td><td class="erp-number report-cell--num report-cell--last-column">{{ number(totals.balance, 3) }}</td></tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { number } from "../../../components/reports/reportUtils.js"
defineProps({ rows: { type: Array, default: () => [] }, totals: { type: Object, default: null } })
</script>

<style scoped>
.cloth-table { min-width: 880px; }
</style>
