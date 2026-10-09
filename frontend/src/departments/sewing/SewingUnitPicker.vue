<template>
	<div class="sewing-unit-picker">
		<LinkField
			:model-value="supplier"
			doctype="Supplier"
			label="Sewing Unit"
			placeholder="Search Sewing Units"
			:filters="{ is_company_location: 1 }"
			:show-open-button="false"
			show-clear
			@update:model-value="setSupplier"
		/>
	</div>
</template>

<script setup>
import LinkField from "../../components/common/LinkField.vue"
import { useSewingContext } from "./useSewingContext.js"

const { supplier, setSupplier } = useSewingContext()
</script>

<style scoped>
.sewing-unit-picker { width: 100%; max-width: 380px; min-width: 0; }
</style>
