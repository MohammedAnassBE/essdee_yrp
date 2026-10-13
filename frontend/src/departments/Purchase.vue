<template>
	<FabricStore
		store-name="Purchase"
		base-path="/purchase"
		:workspace-keys="['purchase_orders', 'stock_transfers', 'box_stickers', 'reports']"
		:report-keys="['stock_balance', 'purchase_order_itemwise', 'lot_cut_quantity']"
	/>
</template>

<script setup>
import FabricStore from "./FabricStore.vue"
</script>
