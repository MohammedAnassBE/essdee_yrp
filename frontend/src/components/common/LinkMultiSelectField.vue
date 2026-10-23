<template>
	<MultiSelectField
		v-bind="$attrs"
		:model-value="modelValue"
		:options="options"
		option-label="label"
		option-value="value"
		:label="label"
		:help-text="helpText"
		:placeholder="placeholder || `Search ${label || doctype}…`"
		:disabled="disabled"
		:invalid="invalid"
		:loading="searching"
		filter-match-mode="link-search-server"
		:reset-filter-on-hide="true"
		@update:model-value="update"
		@before-show="search()"
		@filter="queueSearch($event.value)"
	/>
</template>

<script setup>
import { FilterService } from "@primevue/core/api"
import { computed, onBeforeUnmount, ref } from "vue"

import { searchLink } from "../../api/frappe.js"
import MultiSelectField from "./MultiSelectField.vue"

/** Checkbox multi-select over a Link doctype, searched server-side with two-line options. */
defineOptions({ inheritAttrs: false })

// The server already matched the typed text (name, title, item or supplier name).
FilterService.register("link-search-server", () => true)

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	doctype: { type: String, required: true },
	label: { type: String, default: "" },
	helpText: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	filters: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	allowVariants: { type: Boolean, default: false },
	pageLength: { type: Number, default: 20 },
	delay: { type: Number, default: 300 },
})
const emit = defineEmits(["update:modelValue"])

const suggestions = ref([])
const known = ref(new Map())
const searching = ref(false)
let sequence = 0
let timer = null

const options = computed(() => {
	const byValue = new Map(suggestions.value.map((option) => [option.value, option]))
	for (const value of props.modelValue || []) {
		if (!byValue.has(value)) byValue.set(value, known.value.get(value) || { label: String(value), value })
	}
	return [...byValue.values()]
})

function update(values) {
	const next = new Map(known.value)
	for (const option of suggestions.value) if (values.includes(option.value)) next.set(option.value, option)
	known.value = next
	emit("update:modelValue", values)
}

function queueSearch(text = "") {
	clearTimeout(timer)
	timer = setTimeout(() => search(text), props.delay)
}

async function search(text = "") {
	clearTimeout(timer)
	const request = ++sequence
	searching.value = true
	try {
		const allowVariants = props.allowVariants || /variant/i.test(props.label)
		const rows = await searchLink(props.doctype, text, props.filters, props.pageLength, true, { allowVariants })
		if (request !== sequence) return
		suggestions.value = (rows || []).map((row) => ({
			value: row.name,
			label: row.label || row.name,
			...(row.description ? { description: row.description } : {}),
		}))
	} catch {
		if (request === sequence) suggestions.value = []
	} finally {
		if (request === sequence) searching.value = false
	}
}

onBeforeUnmount(() => clearTimeout(timer))

defineExpose({ search })
</script>
