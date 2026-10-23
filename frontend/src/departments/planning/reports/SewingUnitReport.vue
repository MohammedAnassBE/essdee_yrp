<template>
	<section class="sewing-unit-report" aria-label="Sewing Unit report">
		<SewingUnitPicker />
		<component :is="report" v-if="supplier" :key="supplier" v-bind="reportProps" />
		<Message v-else severity="info" :closable="false">Select a Sewing Unit to run this report.</Message>
	</section>
</template>

<script setup>
import Message from "primevue/message"

import SewingUnitPicker from "../../sewing/SewingUnitPicker.vue"
import { useSewingContext } from "../../sewing/useSewingContext.js"

/** Runs a Sewing Unit-scoped report once a unit is chosen; the unit lives in `?supplier=`. */
defineProps({
	report: { type: [Object, Function], required: true },
	reportProps: { type: Object, default: () => ({}) },
})
const { supplier } = useSewingContext()
</script>

<style scoped>
.sewing-unit-report { display: grid; min-width: 0; gap: var(--erp-space-3); }
</style>
