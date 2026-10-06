<template>
	<CommonStockItemComposer
		:model-value="modelValue"
		:operation="operation"
		:purpose="purpose"
		:update-type="updateType"
		:editor="editor"
		:schema-loader="loadSchema"
		@update:model-value="emit('update:modelValue', $event)"
		@dirty="emit('dirty')"
	/>
</template>

<script setup>
import CommonStockItemComposer from "../../components/stock/StockItemComposer.vue"
import { getStockItemSchema } from "./cpmApi.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	cuttingPlan: { type: String, required: true },
	operation: { type: String, required: true },
	purpose: { type: String, default: "" },
	updateType: { type: String, default: "" },
	editor: { type: Object, required: true },
})
const emit = defineEmits(["update:modelValue", "dirty"])

function loadSchema(operation, item) {
	return getStockItemSchema(props.cuttingPlan, operation, item)
}
</script>
