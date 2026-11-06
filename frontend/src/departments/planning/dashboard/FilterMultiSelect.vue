<template>
	<div class="common-field pd-filter">
		<span :id="labelId" class="erp-field-label">{{ label }}</span>
		<MultiSelect
			:model-value="modelValue"
			:options="shownOptions"
			option-label="value"
			option-value="value"
			:placeholder="placeholder"
			:filter="false"
			:show-toggle-all="false"
			:virtual-scroller-options="shownOptions.length > 80 ? { itemSize: 40 } : undefined"
			:aria-labelledby="labelId"
			scroll-height="320px"
			fluid
			@update:model-value="emit('update:modelValue', $event)"
			@hide="search = ''"
		>
			<template #value>
				<span v-if="!modelValue.length" class="pd-filter__placeholder">{{ placeholder }}</span>
				<span v-else class="pd-filter__chips">
					<span v-for="value in modelValue.slice(0, MAX_CHIPS)" :key="value" class="pd-filter__chip">
						{{ value }}<button type="button" :aria-label="`Remove ${value}`" @mousedown.stop.prevent @click.stop.prevent="remove(value)">×</button>
					</span>
					<span v-if="modelValue.length > MAX_CHIPS" class="pd-filter__chip pd-filter__chip--more">+{{ modelValue.length - MAX_CHIPS }} more</span>
				</span>
			</template>
			<template #header>
				<div class="pd-filter__search">
					<InputText v-model="search" size="small" :placeholder="searchPlaceholder" :aria-label="`Search ${label}`" fluid @keydown.enter.prevent="selectPasted" @keydown.space.stop />
				</div>
			</template>
			<template #option="{ option }">
				<span class="pd-filter__option"><strong>{{ option.value }}</strong><small v-if="option.hint">{{ option.hint }}</small></span>
			</template>
			<template #emptymessage>No matches</template>
		</MultiSelect>
		<small v-if="help" class="common-field__help">{{ help }}</small>
	</div>
</template>

<script setup>
import InputText from "primevue/inputtext"
import MultiSelect from "primevue/multiselect"
import { computed, ref, useId } from "vue"

/** Searchable multi-select; a pasted list (comma, semicolon or new line) plus Enter selects every match. */
const props = defineProps({
	label: { type: String, required: true },
	modelValue: { type: Array, default: () => [] },
	options: { type: Array, default: () => [] },
	placeholder: { type: String, default: "" },
	help: { type: String, default: "" },
	searchPlaceholder: { type: String, default: "Search, or paste values separated by , or ; then Enter" },
})
const emit = defineEmits(["update:modelValue"])
const MAX_CHIPS = 8
const labelId = `pd-filter-${useId()}`
const search = ref("")

const shownOptions = computed(() => {
	const text = search.value.trim().toLowerCase()
	const matching = text && !/[,;\n]/.test(text)
		? props.options.filter((option) => `${option.value} ${option.hint || ""}`.toLowerCase().includes(text))
		: props.options
	const known = new Set(matching.map((option) => option.value))
	return [...matching, ...props.modelValue.filter((value) => !known.has(value)).map((value) => ({ value, hint: "" }))]
})

function remove(value) {
	emit("update:modelValue", props.modelValue.filter((item) => item !== value))
}

function selectPasted() {
	const wanted = new Set(search.value.split(/[,;\n]/).map((value) => value.trim().toLowerCase()).filter(Boolean))
	const matches = props.options.map((option) => option.value).filter((value) => wanted.has(String(value).toLowerCase()))
	if (!matches.length) return
	emit("update:modelValue", [...new Set([...props.modelValue, ...matches])])
	search.value = ""
}
</script>
