<template>
	<CommonStockItemComposer
		:model-value="modelValue"
		:operation="operation"
		:purpose="purpose"
		:update-type="updateType"
		:editor="editor"
		:schema-loader="loadSchema"
		:row-preparer="prepareRow"
		@update:model-value="emit('update:modelValue', $event)"
		@dirty="emit('dirty')"
	/>
</template>

<script setup>
import CommonStockItemComposer from "../../components/stock/StockItemComposer.vue"
import { getStockItemSchema } from "./cpmApi.js"
import { getStockUpdateRates } from "../../api/fabricStore.js"
import { prepareStockUpdateRow } from "../../utils/stockItemComposer.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	cuttingPlan: { type: String, required: true },
	operation: { type: String, required: true },
	purpose: { type: String, default: "" },
	updateType: { type: String, default: "" },
	warehouse: { type: String, default: "" },
	editor: { type: Object, required: true },
})
const emit = defineEmits(["update:modelValue", "dirty"])

function loadSchema(operation, item) {
	return getStockItemSchema(props.cuttingPlan, operation, item)
}

async function prepareRow(row) {
	if (props.operation !== "stock_update") return row
	return prepareStockUpdateRow(row, props.warehouse, getStockUpdateRates)
}
</script>
