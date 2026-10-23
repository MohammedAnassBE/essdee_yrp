<template>
	<label class="async-multi" @keydown.capture="onKeydown">
		<span class="erp-field-label">{{ label }}</span>
		<AutoComplete
			ref="input"
			v-model="selected"
			:input-id="inputId"
			:aria-label="label"
			:suggestions="suggestions"
			option-label="label"
			:placeholder="placeholder"
			:delay="300"
			auto-option-focus
			focus-on-hover
			multiple
			fluid
			:disabled="disabled"
			@complete="complete"
			@before-show="focusFirstOption"
		>
			<template #option="{ option }">
				<span class="async-multi__option">
					<strong>{{ option.label }}</strong>
					<small v-if="option.description">{{ formatDatesInText(option.description) }}</small>
				</span>
			</template>
		</AutoComplete>
		<small v-if="helpText" class="erp-help-text">{{ helpText }}</small>
	</label>
</template>

<script setup>
import PrimeAutoComplete from "primevue/autocomplete"
import { computed, nextTick, ref, watch } from "vue"

import { handleAutocompleteKey, withAutocompleteCompositionGuard } from "../../../components/common/autocompleteKeys.js"
import { searchLink } from "../../../api/frappe.js"
import { formatDatesInText } from "../../../utils/dateFormat.js"

const AutoComplete = withAutocompleteCompositionGuard(PrimeAutoComplete)

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	doctype: { type: String, required: true },
	label: { type: String, required: true },
	placeholder: { type: String, default: "Search and add…" },
	helpText: { type: String, default: "" },
	filters: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
	allowVariants: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])

const inputId = computed(() => `async-multi-${props.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`)

const input = ref(null)
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

function onKeydown(event) { handleAutocompleteKey(event, input.value, () => {}, input.value?.searching) }
async function focusFirstOption() {
	await nextTick()
	if (input.value?.overlayVisible) input.value.focusedOptionIndex = input.value.findFirstOptionIndex()
}

async function complete(event) {
	const request = ++sequence
	try {
		const allowVariants = props.allowVariants || /variant/i.test(props.label)
		const rows = await searchLink(props.doctype, event.query || "", props.filters, 20, false, { allowVariants })
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

.async-multi__option {
	display: grid;
	gap: 2px;
}

.async-multi__option small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.async-multi :deep(.p-autocomplete-multiple) {
	min-height: var(--erp-control-height);
}

.async-multi :deep(.p-autocomplete-chip) {
	font-size: var(--erp-font-size-min);
}
</style>
