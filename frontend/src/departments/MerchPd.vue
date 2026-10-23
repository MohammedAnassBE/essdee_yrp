<template>
	<Merch title="Merch PD" :items="merchPdLauncherItems()" :load-capabilities="getMerchPdCapabilities" />
</template>

<script setup>
import { getMerchPdCapabilities } from "../api/merch.js"
import Merch from "./Merch.vue"
import { merchPdLauncherItems } from "./merch-pd/merchPdViews.js"
</script>
