<template>
	<FabricStore
		store-name="Purchase"
		base-path="/purchase"
		:workspace-keys="PURCHASE_STORE_WORKSPACE_KEYS"
		:report-keys="PURCHASE_REPORT_KEYS"
		:extra-workspaces="purchaseLauncherItems()"
		:extra-capabilities-loader="getPurchaseCapabilities"
	/>
</template>

<script setup>
import { getPurchaseCapabilities } from "../api/purchase.js"
import FabricStore from "./FabricStore.vue"
import { PURCHASE_REPORT_KEYS, PURCHASE_STORE_WORKSPACE_KEYS, purchaseLauncherItems } from "./purchase/purchaseViews.js"
</script>
