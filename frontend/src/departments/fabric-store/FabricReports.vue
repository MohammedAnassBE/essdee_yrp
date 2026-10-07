<template>
	<div class="fabric-reports">
		<header class="fabric-reports__header">
			<div>
				<span>Inventory report</span>
				<h1>Stock Balance</h1>
			</div>
			<i class="pi pi-warehouse" aria-hidden="true" />
		</header>
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

.fabric-reports__header {
	display: flex;
	min-height: 46px;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
	padding: 5px 3px 7px;
}

.fabric-reports__header > div {
	display: grid;
	gap: 1px;
}

.fabric-reports__header span {
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	letter-spacing: .055em;
	text-transform: uppercase;
}

.fabric-reports__header h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: 18px;
	letter-spacing: -.018em;
}

.fabric-reports__header > i {
	display: grid;
	width: 36px;
	height: 36px;
	color: var(--erp-accent-dark);
	background: var(--erp-accent-soft);
	border: 1px solid color-mix(in srgb, var(--erp-accent) 18%, var(--erp-border));
	border-radius: var(--erp-control-radius);
	place-items: center;
}
</style>
