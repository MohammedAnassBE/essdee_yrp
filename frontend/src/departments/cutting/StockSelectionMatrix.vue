<template>
	<CommonStockSelectionMatrix
		:groups="groups"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	/>
</template>

<script setup>
import CommonStockSelectionMatrix from "../../components/stock/StockSelectionMatrix.vue"

defineProps({
	groups: { type: Array, default: () => [] },
	modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:modelValue"])
</script>
