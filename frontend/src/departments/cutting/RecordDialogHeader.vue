<template>
	<div class="record-dialog-header">
		<DocumentStepButtons
			v-if="previousName || nextName"
			:document-label="documentLabel"
			:previous-name="previousName"
			:next-name="nextName"
			:disabled="disabled"
			@previous="emit('navigate', previousName)"
			@next="emit('navigate', nextName)"
		/>
		<span class="p-dialog-title">{{ title }}</span>
	</div>
</template>

<script setup>
import DocumentStepButtons from "../../components/navigation/DocumentStepButtons.vue"

defineProps({
	title: { type: String, default: "" },
	documentLabel: { type: String, default: "" },
	previousName: { type: String, default: "" },
	nextName: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["navigate"])
</script>

<style scoped>
.record-dialog-header {
	display: flex;
	min-width: 0;
	align-items: center;
	gap: 10px;
}
</style>
