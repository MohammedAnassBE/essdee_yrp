<template>
	<CuttingPlanSidebar
		:parent-doctype="parentDoctype"
		:parent-name="parentName"
		:parent-field="parentField"
		:data="data"
		:loading="loading"
		:error="error"
		@refresh="emit('refresh')"
	/>
</template>

<script setup>
import CuttingPlanSidebar from "../CuttingPlanSidebar.vue"

defineProps({
	parentDoctype: { type: String, required: true },
	parentName: { type: String, required: true },
	parentField: { type: String, required: true },
	data: { type: Object, default: () => ({}) },
	loading: Boolean,
	error: { type: String, default: "" },
})
const emit = defineEmits(["refresh"])
</script>
