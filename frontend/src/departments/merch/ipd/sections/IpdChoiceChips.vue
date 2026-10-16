<template>
	<fieldset ref="root" class="ipd-choices" :disabled="readonly" tabindex="-1">
		<legend v-if="label" class="erp-field-label">{{ label }}</legend>
		<div class="ipd-choices__list">
			<label v-for="choice in choices" :key="choice" class="ipd-choice" :class="{ 'is-on': selected.includes(choice) }">
				<input type="checkbox" :checked="selected.includes(choice)" :disabled="readonly" @change="emit('toggle', choice, $event.target.checked)">
				<span>{{ choice }}</span>
			</label>
			<span v-if="!choices.length" class="erp-help-text">{{ emptyText }}</span>
		</div>
	</fieldset>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(["toggle"])
defineProps({
	label: { type: String, default: "" },
	choices: { type: Array, default: () => [] },
	selected: { type: Array, default: () => [] },
	readonly: { type: Boolean, default: false },
	emptyText: { type: String, default: "Nothing to choose yet." },
})
const root = ref(null)
function focus() {
	if (!root.value?.querySelector('input')) return false
	const target = root.value.querySelector('input:not(:disabled)') || root.value
	target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
	target.focus({ preventScroll: true })
	return document.activeElement === target
}
defineExpose({ focus })
</script>
