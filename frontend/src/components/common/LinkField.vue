<template>
	<label class="common-field" :class="{ 'common-field--invalid': invalid }">
		<span v-if="label" class="common-field__label">{{ label }}</span>
		<span class="link-field__control">
			<AutoComplete
				ref="input"
				:model-value="inputValue"
				:suggestions="suggestions"
				:option-label="optionLabel"
				:placeholder="placeholder || `Search ${doctype || 'record'}…`"
				:disabled="disabled"
				:invalid="invalid"
				:dropdown="dropdown"
				:delay="delay"
				:show-clear="showClear"
				force-selection
				fluid
				@complete="complete"
				@item-select="select"
				@clear="clear"
				@blur="restoreCommittedValue"
				@update:model-value="inputValue = $event"
			>
				<template #option="{ option }">
					<span class="link-field__option">
						<strong>{{ option.label }}</strong>
						<small v-if="option.name && option.name !== option.label">{{ option.name }}</small>
					</span>
				</template>
				<template #empty>
					<span class="link-field__empty">
						<i v-if="searching" class="pi pi-spin pi-spinner" />
						{{ searching ? "Searching…" : searchError || "No matches" }}
					</span>
				</template>
			</AutoComplete>
			<Button
				v-if="showOpenButton && modelValue"
				icon="pi pi-arrow-up-right"
				severity="secondary"
				text
				rounded
				:aria-label="`Open ${modelValue}`"
				:title="`Open ${modelValue}`"
				@click.prevent="openRecord"
			/>
		</span>
		<small v-if="helpText" class="common-field__help">{{ helpText }}</small>
	</label>
</template>

<script setup>
import AutoComplete from "primevue/autocomplete"
import Button from "primevue/button"
import { computed, ref, watch } from "vue"

import { searchLink } from "../../api/frappe.js"

const props = defineProps({
	modelValue: { type: [String, Number], default: "" },
	doctype: { type: String, required: true },
	label: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	helpText: { type: String, default: "" },
	filters: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	dropdown: { type: Boolean, default: true },
	delay: { type: Number, default: 300 },
	pageLength: { type: Number, default: 20 },
	matchVisibleOnly: { type: Boolean, default: false },
	showClear: { type: Boolean, default: false },
	showOpenButton: { type: Boolean, default: true },
	searchHandler: { type: Function, default: null },
	openHandler: { type: Function, default: null },
})

const emit = defineEmits(["update:modelValue", "select", "clear"])

const input = ref(null)
const inputValue = ref(null)
const suggestions = ref([])
const searching = ref(false)
const searchError = ref("")
const committedLabel = ref("")
let requestSequence = 0

const optionLabel = computed(() => "label")

watch(
	() => props.modelValue,
	(value) => {
		if (!value) {
			committedLabel.value = ""
			inputValue.value = null
			return
		}
		const currentName = typeof inputValue.value === "object" ? inputValue.value?.name : ""
		if (currentName !== value) {
			committedLabel.value = String(value)
			inputValue.value = { name: value, label: String(value) }
		}
	},
	{ immediate: true },
)

async function complete(event) {
	const sequence = ++requestSequence
	searching.value = true
	searchError.value = ""
	try {
		const rows = props.searchHandler
			? await props.searchHandler(event.query || "")
			: await searchLink(
				props.doctype,
				event.query || "",
				props.filters,
				props.pageLength,
				props.matchVisibleOnly,
			)
		if (sequence !== requestSequence) return
		suggestions.value = (rows || []).map((row) =>
			typeof row === "string"
				? { name: row, label: row }
				: { ...row, name: row.name, label: row.label || row.name },
		)
	} catch (error) {
		if (sequence !== requestSequence) return
		suggestions.value = []
		searchError.value = error.message || "Search failed"
	} finally {
		if (sequence === requestSequence) searching.value = false
	}
}

function select(event) {
	const selected = event.value || {}
	const name = selected.name || selected
	committedLabel.value = selected.label || String(name)
	inputValue.value = { name, label: committedLabel.value }
	emit("update:modelValue", name)
	emit("select", { name, label: committedLabel.value, row: selected })
}

function clear() {
	committedLabel.value = ""
	inputValue.value = null
	emit("update:modelValue", "")
	emit("clear")
}

function restoreCommittedValue() {
	inputValue.value = props.modelValue
		? { name: props.modelValue, label: committedLabel.value || String(props.modelValue) }
		: null
}

function openRecord() {
	if (props.openHandler) {
		props.openHandler(props.doctype, props.modelValue)
		return
	}
	const route = `/app/${encodeURIComponent(props.doctype.toLowerCase().replaceAll(" ", "-"))}/${encodeURIComponent(props.modelValue)}`
	window.open(route, "_blank", "noopener")
}

function focus() {
	input.value?.$el?.querySelector("input")?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.common-field {
	display: grid;
	gap: 6px;
	width: 100%;
}

.common-field__label {
	font-size: 0.8rem;
	font-weight: 650;
	color: #34413a;
}

.common-field__help,
.link-field__empty {
	font-size: 0.75rem;
	color: #77827c;
}

.link-field__control {
	display: flex;
	align-items: center;
	gap: 4px;
}

.link-field__control :deep(.p-autocomplete) {
	flex: 1;
	min-width: 0;
}

.link-field__empty {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	padding: 8px 10px;
}

.link-field__option {
	display: grid;
	gap: 2px;
}

.link-field__option strong {
	color: #26372d;
	font-size: 0.78rem;
	font-weight: 650;
}

.link-field__option small {
	color: #7b877f;
	font-size: 0.67rem;
}
</style>
