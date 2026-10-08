<template>
	<div class="fabric-reports">
		<StockBalanceReport />
	</div>
</template>

<script setup>
import StockBalanceReport from "../../components/reports/StockBalanceReport.vue"
</script>

<style scoped>
.fabric-reports {
	display: grid;
	min-width: 0;
	gap: var(--erp-space-2);
}

</style>
