<template>
	<fieldset ref="root" class="ipd-choices" :disabled="readonly" tabindex="-1">
		<legend v-if="label || showSelectAll" class="erp-field-label">
			<span class="ipd-choices__header">
				<span v-if="label">{{ label }}</span>
				<button v-if="showSelectAll" type="button" class="ipd-choices__toggle"
					:aria-label="`${allSelected ? 'Clear all' : 'Select all'} ${label || 'values'}`"
					:aria-pressed="allSelected" @click="toggleAll">
					{{ allSelected ? 'Clear all' : 'Select all' }}
				</button>
			</span>
		</legend>
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
import { computed, ref } from 'vue'

const emit = defineEmits(["toggle"])
const props = defineProps({
	label: { type: String, default: "" },
	choices: { type: Array, default: () => [] },
	selected: { type: Array, default: () => [] },
	readonly: { type: Boolean, default: false },
	selectAll: { type: Boolean, default: true },
	emptyText: { type: String, default: "Nothing to choose yet." },
})
const root = ref(null)
const showSelectAll = computed(() => props.selectAll && props.choices.length >= 2 && !props.readonly)
const allSelected = computed(() => props.choices.every(choice => props.selected.includes(choice)))

function toggleAll() {
	if (props.readonly) return
	const on = !allSelected.value
	const changed = props.choices.filter(choice => props.selected.includes(choice) !== on)
	for (const choice of changed) emit('toggle', choice, on)
}

function focus() {
	if (!root.value?.querySelector('input')) return false
	const target = root.value.querySelector('input:not(:disabled)') || root.value
	target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
	target.focus({ preventScroll: true })
	return document.activeElement === target
}
defineExpose({ focus })
</script>
