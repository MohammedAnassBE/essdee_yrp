<template>
	<section class="accounts-sewing-dpr" aria-label="Sewing DPR">
		<SewingUnitPicker />
		<SewingDpr v-if="supplier" :key="supplier" :filters="filters" />
		<Message v-else severity="secondary" :closable="false">Choose a Sewing Unit to generate the DPR.</Message>
	</section>
</template>

<script setup>
import Message from "primevue/message"
import { reactive } from "vue"

import SewingUnitPicker from "../../sewing/SewingUnitPicker.vue"
import { useSewingContext } from "../../sewing/useSewingContext.js"
import SewingDpr from "../../sewing/reports/SewingDpr.vue"

const { supplier } = useSewingContext()
const filters = reactive({
	mode: "daily",
	date: "",
	fromDate: "",
	toDate: "",
	workStation: "",
	inputType: "",
})
</script>

<style scoped>
.accounts-sewing-dpr { display: grid; min-width: 0; gap: var(--erp-space-3); }
</style>
