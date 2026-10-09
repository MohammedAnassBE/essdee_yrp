<template>
	<label class="async-multi">
		<span class="erp-field-label">{{ label }}</span>
		<AutoComplete
			v-model="selected"
			:input-id="inputId"
			:aria-label="label"
			:suggestions="suggestions"
			option-label="label"
			:placeholder="placeholder"
			:delay="300"
			multiple
			fluid
			@complete="complete"
		/>
		<small v-if="helpText" class="erp-help-text">{{ helpText }}</small>
	</label>
</template>

<script setup>
import AutoComplete from "primevue/autocomplete"
import { computed, ref, watch } from "vue"

import { searchLink } from "../../../api/frappe.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	doctype: { type: String, required: true },
	label: { type: String, required: true },
	placeholder: { type: String, default: "Search and add…" },
	helpText: { type: String, default: "" },
	filters: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:modelValue"])

const inputId = computed(() => `async-multi-${props.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`)

const selected = ref([])
const suggestions = ref([])
let sequence = 0

watch(
	() => props.modelValue,
	(value) => {
		const names = selected.value.map((row) => row.name)
		if (JSON.stringify(names) !== JSON.stringify(value || [])) {
			selected.value = (value || []).map((name) => ({ name, label: name }))
		}
	},
	{ immediate: true },
)

watch(
	selected,
	(value) => emit("update:modelValue", (value || []).map((row) => row.name || row).filter(Boolean)),
	{ deep: true },
)

async function complete(event) {
	const request = ++sequence
	try {
		const rows = await searchLink(props.doctype, event.query || "", props.filters, 20)
		if (request !== sequence) return
		const chosen = new Set(selected.value.map((row) => row.name))
		suggestions.value = (rows || [])
			.map((row) => ({ ...row, name: row.name, label: row.label || row.name }))
			.filter((row) => !chosen.has(row.name))
	} catch {
		if (request === sequence) suggestions.value = []
	}
}

</script>

<style scoped>
.async-multi {
	display: block;
	min-width: 0;
}

.async-multi :deep(.p-autocomplete-multiple) {
	min-height: var(--erp-control-height);
}

.async-multi :deep(.p-autocomplete-chip) {
	font-size: var(--erp-font-size-min);
}
</style>
