<template>
	<ProcessCostEditor :process-cost-id="processCostId" />
</template>

<script setup>
import ProcessCostEditor from "./ProcessCostEditor.vue"
defineProps({ processCostId: { type: String, default: "" } })
</script>
