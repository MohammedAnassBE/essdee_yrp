<template>
	<FabricStore
		store-name="Purchase"
		base-path="/purchase"
		:workspace-keys="['purchase_orders', 'stock_transfers', 'box_stickers', 'reports']"
		:report-keys="['stock_balance', 'purchase_order_itemwise', 'lot_cut_quantity']"
		:extra-workspaces="purchaseLauncherItems()"
		:extra-capabilities-loader="getPurchaseCapabilities"
	/>
</template>

<script setup>
import { getPurchaseCapabilities } from "../api/purchase.js"
import FabricStore from "./FabricStore.vue"
import { purchaseLauncherItems } from "./purchase/purchaseViews.js"
</script>
