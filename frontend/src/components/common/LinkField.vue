<template>
	<div class="common-field" :class="{ 'common-field--invalid': invalid }">
		<label v-if="label" class="common-field__label" :for="resolvedInputId">{{ label }}</label>
		<span class="link-field__control">
			<AutoComplete
				ref="input"
				:input-id="resolvedInputId"
				:model-value="inputValue"
				:suggestions="suggestions"
				:option-label="optionLabel"
				:placeholder="placeholder || `Search ${doctype || 'record'}…`"
				:disabled="disabled"
				:invalid="invalid"
				:dropdown="dropdown"
				:delay="delay"
				:show-clear="showClear"
				:aria-label="ariaLabel || label || undefined"
				:pt="autocompletePt"
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
					<span class="link-field__empty" role="status" aria-live="polite">
						<i v-if="searching" class="pi pi-spin pi-spinner" />
						{{ emptyStateMessage }}
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
	</div>
</template>

<script setup>
import AutoComplete from "primevue/autocomplete"
import Button from "primevue/button"
import { computed, ref, useId, watch } from "vue"

import { searchLink } from "../../api/frappe.js"
import { webDocumentPath } from "../../router/webDocumentRoutes.js"

const props = defineProps({
	modelValue: { type: [String, Number], default: "" },
	doctype: { type: String, required: true },
	label: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	inputId: { type: String, default: "" },
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
	required: { type: Boolean, default: false },
	ariaLabel: { type: String, default: "" },
	ariaDescribedby: { type: String, default: "" },
	emptyMessage: { type: String, default: "" },
	dependencyMessage: { type: String, default: "Select the related field first" },
	searchHandler: { type: Function, default: null },
	openHandler: { type: Function, default: null },
})

const emit = defineEmits(["update:modelValue", "select", "clear"])

const input = ref(null)
const componentId = useId()
const inputValue = ref(null)
const suggestions = ref([])
const searching = ref(false)
const searchError = ref("")
const committedLabel = ref("")
let requestSequence = 0

const optionLabel = computed(() => "label")
const resolvedInputId = computed(() => props.inputId || `link-field-${componentId}`)
const hasIncompleteFilters = computed(() => Object.keys(props.filters || {}).length > 0
	&& Object.values(props.filters || {}).some((value) => value === "" || value === null || value === undefined))
const emptyStateMessage = computed(() => {
	if (searching.value) return "Searching…"
	if (searchError.value) return searchError.value
	if (hasIncompleteFilters.value) return props.dependencyMessage
	if (props.emptyMessage) return props.emptyMessage
	return `No ${props.doctype || "records"} found`
})
const autocompletePt = computed(() => ({
	dropdown: {
		"aria-label": `Show ${props.ariaLabel || props.label || props.doctype || "record"} options`,
		title: `Show ${props.ariaLabel || props.label || props.doctype || "record"} options`,
	},
	pcInputText: {
		root: {
			title: committedLabel.value || String(props.modelValue || "") || undefined,
			required: props.required || undefined,
			"aria-required": props.required ? "true" : undefined,
			"aria-describedby": props.ariaDescribedby || undefined,
		},
	},
}))

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
	const route = webDocumentPath(props.doctype, props.modelValue)
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
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 680;
	transition: color var(--erp-transition-fast);
}

.common-field:focus-within .common-field__label {
	color: var(--erp-accent-hover);
}

.common-field__help,
.link-field__empty {
	font-size: 0.75rem;
	color: var(--erp-text-muted);
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

.link-field__control :deep(.p-autocomplete-input) {
	min-width: 0;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	background: var(--erp-surface);
	border-color: var(--erp-border-strong);
	box-shadow: var(--erp-shadow-xs);
}

.link-field__control :deep(.p-autocomplete:not(.p-disabled):hover .p-autocomplete-input) {
	border-color: color-mix(in srgb, var(--erp-accent) 32%, var(--erp-border-strong));
}

.link-field__control :deep(.p-autocomplete:focus-within .p-autocomplete-input) {
	border-color: var(--erp-accent);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--erp-accent) 11%, transparent);
}

.link-field__control :deep(.p-button:focus-visible) {
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 16%, transparent);
	outline-offset: 1px;
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
	color: var(--erp-text);
	font-size: 0.78rem;
	font-weight: 650;
}

.link-field__option small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}
</style>
