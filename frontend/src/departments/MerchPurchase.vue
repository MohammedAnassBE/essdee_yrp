<template>
	<Merch title="Merch & Purchase" :items="merchPurchaseLauncherItems()" :load-capabilities="getMerchPurchaseCapabilities" report-department="merch-purchase" />
</template>

<script setup>
import { getMerchPurchaseCapabilities } from "../api/merch.js"
import Merch from "./Merch.vue"
import { merchPurchaseLauncherItems } from "./merch-purchase/merchPurchaseViews.js"
</script>
