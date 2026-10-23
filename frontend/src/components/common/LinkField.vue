<template>
	<div class="common-field" :class="{ 'common-field--invalid': invalid || validationError }" @keydown.capture="onKeydown">
		<label v-if="label" class="common-field__label erp-field-label" :for="resolvedInputId">{{ labelParts.text }}<span v-if="labelParts.required" class="erp-required-mark" aria-hidden="true">*</span></label>
		<span class="link-field__control">
			<AutoComplete
				ref="input"
				:input-id="resolvedInputId"
				:model-value="inputValue"
				:suggestions="suggestions"
				:option-label="optionLabel"
				:placeholder="placeholder || `Search ${doctype || 'record'}…`"
				:disabled="disabled"
				:invalid="invalid || Boolean(validationError)"
				:dropdown="dropdown"
				:delay="delay"
				:show-clear="showClear"
				:aria-label="ariaLabel || label || undefined"
				:pt="autocompletePt"
				auto-option-focus
				focus-on-hover
				fluid
				@complete="complete"
				@item-select="select"
				@clear="clearFromControl"
				@before-show="focusFirstOption"
				@blur="onBlur"
				@update:model-value="updateInput"
			>
				<template #option="{ option }">
					<span class="link-field__option">
						<strong>{{ option.label }}</strong>
						<small v-if="option.name && option.name !== option.label">{{ option.name }}</small>
						<small v-if="option.description">{{ formatDatesInText(option.description) }}</small>
					</span>
				</template>
				<template #empty>
					<span class="link-field__empty" role="status" aria-live="polite">
						<i v-if="searching" class="pi pi-spin pi-spinner" />
						{{ emptyStateMessage }}
					</span>
				</template>
				<template v-if="showCreate" #footer>
					<button type="button" class="link-field__create" @mousedown.prevent @click="openCreate">
						<i class="pi pi-plus" aria-hidden="true" /> Create a new {{ createTarget }}
					</button>
				</template>
			</AutoComplete>
			<Button
				v-if="canOpen && openHandler"
				icon="pi pi-arrow-up-right"
				severity="secondary"
				text
				rounded
				:aria-label="`Open ${modelValue}`"
				:title="`Open ${modelValue}`"
				@click.prevent="openHandler(doctype, modelValue)"
			/>
			<DocumentLink
				v-else-if="canOpen"
				:doctype="doctype"
				:name="modelValue"
				class="link-field__open"
				:aria-label="`Open ${modelValue}`"
				:title="`Open ${modelValue}`"
			><i class="pi pi-arrow-up-right" aria-hidden="true" /></DocumentLink>
		</span>
		<QuickEntryDialog
			v-if="createVisible"
			v-model:visible="createVisible"
			:doctype="createTarget"
			:presets="linkCreateValues(filters, createValues)"
			:query="createQuery"
			@created="selectCreated"
		/>
		<small v-if="validationError && showValidationMessage" :id="`${resolvedInputId}-link-error`" class="link-field__error" role="alert">{{ validationError }}</small>
		<small v-if="helpText" class="common-field__help">{{ helpText }}</small>
	</div>
</template>

<script setup>
import PrimeAutoComplete from "primevue/autocomplete"
import Button from "primevue/button"
import { computed, nextTick, ref, useId, watch } from "vue"

import { invalidatePendingReads, searchLink } from "../../api/frappe.js"
import { canCreateDoctype, canReadDoctype } from "../../utils/linkTarget.js"
import { linkCreateValues } from "../../utils/quickEntry.js"
import QuickEntryDialog from "./asyncQuickEntryDialog.js"
import DocumentLink from "./DocumentLink.vue"
import { formatDatesInText } from "../../utils/dateFormat.js"
import { handleAutocompleteKey, withAutocompleteCompositionGuard } from "./autocompleteKeys.js"

const AutoComplete = withAutocompleteCompositionGuard(PrimeAutoComplete)

const props = defineProps({
	resetVersion: { type: Number, default: 0 },
	modelValue: { type: [String, Number], default: "" },
	doctype: { type: String, required: true },
	label: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	inputId: { type: String, default: "" },
	helpText: { type: String, default: "" },
	filters: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	showValidationMessage: { type: Boolean, default: true },
	cellEditor: { type: Boolean, default: false },
	dropdown: { type: Boolean, default: true },
	delay: { type: Number, default: 150 },
	pageLength: { type: Number, default: 20 },
	matchVisibleOnly: { type: Boolean, default: false },
	fieldname: { type: String, default: "" },
	allowVariants: { type: Boolean, default: false },
	showClear: { type: Boolean, default: false },
	showOpenButton: { type: Boolean, default: true },
	required: { type: Boolean, default: false },
	ariaLabel: { type: String, default: "" },
	ariaDescribedby: { type: String, default: "" },
	emptyMessage: { type: String, default: "" },
	dependencyMessage: { type: String, default: "Select the related field first" },
	searchHandler: { type: Function, default: null },
	openHandler: { type: Function, default: null },
	allowCreate: { type: Boolean, default: true },
	createDoctype: { type: String, default: "" },
	createValues: { type: Object, default: null },
	createValueField: { type: String, default: "name" },
})

const labelParts = computed(() => {
	const match = /^(.*?)\s*\*$/.exec(props.label || "")
	return match ? { text: match[1], required: true } : { text: props.label, required: props.required }
})
const canOpen = computed(() => props.showOpenButton && props.modelValue && String(props.modelValue).trim() && canReadDoctype(props.doctype))

const createTarget = computed(() => props.createDoctype || props.doctype)
const showCreate = computed(() => props.allowCreate && !props.cellEditor && !props.disabled && canCreateDoctype(createTarget.value))

const emit = defineEmits(["update:modelValue", "select", "clear", "validation", "finish", "cancel"])

const input = ref(null)
const componentId = useId()
const inputValue = ref(null)
const suggestions = ref([])
const searching = ref(false)
const searchError = ref("")
const validationError = ref("")
const committedName = ref("")
const committedLabel = ref("")
const createVisible = ref(false)
const createQuery = ref("")
let requestSequence = 0
let suggestionSequence = null
let blurredOption = null

const modelLabel = computed(() => committedName.value === props.modelValue
	? committedLabel.value || String(props.modelValue || "")
	: String(props.modelValue || ""))
const optionLabel = computed(() => "label")
// Item pickers hide variants server-side unless this field is an item-variant field.
const searchesVariants = computed(() => props.allowVariants
	|| /variant/i.test(`${props.fieldname} ${props.label} ${props.ariaLabel}`))
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
	option: { onMousedown: (event) => event.preventDefault() },
	dropdown: {
		"aria-label": `Show ${props.ariaLabel || props.label || props.doctype || "record"} options`,
		title: `Show ${props.ariaLabel || props.label || props.doctype || "record"} options`,
	},
	pcInputText: {
		root: {
			title: modelLabel.value || undefined,
			required: props.required || undefined,
			"aria-required": props.required ? "true" : undefined,
			"aria-describedby": [props.ariaDescribedby, validationError.value && props.showValidationMessage ? `${resolvedInputId.value}-link-error` : ""].filter(Boolean).join(" ") || undefined,
		},
	},
}))

watch(
	() => [props.modelValue, props.resetVersion],
	(current, previous) => {
		// An explicit reset must not reuse searches started before it.
		if (previous && current[1] !== previous[1]) invalidatePendingReads()
		blurredOption = null; cancelSearch(); setValidation(); syncModelValue()
	},
	{ immediate: true },
)

async function complete(event) {
	const sequence = ++requestSequence
	suggestionSequence = null
	suggestions.value = []
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
				{ allowVariants: searchesVariants.value },
			)
		if (sequence !== requestSequence) return
		suggestionSequence = sequence
		// Re-arm PrimeVue's suggestions watcher after clearing the previous results.
		if (input.value) input.value.searching = true
		suggestions.value = (rows || []).map((row) =>
			typeof row === "string"
				? { name: row, label: row }
				: { ...row, name: row.name, label: row.label || row.name },
		)
	} catch (error) {
		if (sequence !== requestSequence) return
		if (input.value) input.value.searching = true
		suggestions.value = []
		searchError.value = error.message || "Search failed"
	} finally {
		if (sequence === requestSequence) searching.value = false
	}
}

function select(event) {
	const selected = event.value
	if (suggestionSequence !== requestSequence || !suggestions.value.includes(selected)) {
		restoreCommittedValue()
		return
	}
	setValidation()
	const name = typeof selected === "object" ? selected?.name : selected
	if (name === undefined || name === null || name === "") return
	committedName.value = name
	committedLabel.value = selected.label || String(name)
	inputValue.value = { name, label: committedLabel.value }
	emit("update:modelValue", name)
	emit("select", { name, label: committedLabel.value, row: selected })
}

function openCreate() {
	createQuery.value = typeof inputValue.value === "string" ? inputValue.value.trim() : ""
	input.value?.hide()
	createVisible.value = true
}

function selectCreated({ doc, label }) {
	const name = doc?.[props.createValueField]
	if (name === undefined || name === null || name === "") return
	setValidation()
	committedName.value = name
	committedLabel.value = props.createValueField === "name" ? label || String(name) : String(name)
	inputValue.value = { name, label: committedLabel.value }
	emit("update:modelValue", name)
	emit("select", { name, label: committedLabel.value, row: doc })
}

function updateInput(value) {
	blurredOption = null
	if (typeof value === "string") {
		cancelSearch()
		searchError.value = ""
	}
	setValidation()
	inputValue.value = value
	if (value === "" || value === null) clear()
}

function onKeydown(event) {
	if (event.isComposing || event.keyCode === 229) return
	if (event.target !== input.value?.$el?.querySelector("input")) return
	if (handleCellKey(event)) return
	if (event.key === "Enter" && !canPickSuggestion()) rejectUnselected()
	handleAutocompleteKey(event, input.value, restoreCommittedValue, searching.value || suggestionSequence !== requestSequence)
}
function canPickSuggestion() {
	return input.value?.overlayVisible && suggestions.value.length && suggestionSequence === requestSequence && !searching.value
}
function handleCellKey(event) {
	if (!props.cellEditor || !["Escape", "Tab"].includes(event.key)) return false
	event.stopPropagation()
	if (event.key === "Escape") { event.preventDefault(); emit("cancel") }
	else emit("finish", event)
	return true
}
async function focusFirstOption() {
	await nextTick()
	if (input.value?.overlayVisible) input.value.focusedOptionIndex = input.value.findFirstOptionIndex()
}
function onBlur() {
	// A tab click blurs the input before its before-change handler runs.
	blurredOption = exactOption()
	if (!createVisible.value) rejectUnselected()
	restoreCommittedValue({ keepBlurredOption: true })
	input.value?.hide()
}

function clearFromControl() {
	if (inputValue.value !== null || committedLabel.value) clear()
}

function clear() {
	setValidation()
	cancelSearch()
	committedName.value = ""
	committedLabel.value = ""
	inputValue.value = null
	emit("update:modelValue", "")
	emit("clear")
}

function cancelSearch() {
	requestSequence += 1
	suggestionSequence = null
	suggestions.value = []
	searching.value = false
	if (input.value) {
		clearTimeout(input.value.searchTimeout)
		input.value.searching = false
		input.value.focusedOptionIndex = -1
	}
}

function setValidation(message = "", query = "") {
	validationError.value = message
	emit("validation", { message, query })
}
function rejectUnselected() {
	const query = typeof inputValue.value === "string" ? inputValue.value.trim() : ""
	if (!query || query === modelLabel.value) return
	const message = searchError.value || (hasIncompleteFilters.value ? props.dependencyMessage
		: !searching.value && !suggestions.value.length
			? `No ${props.doctype || "option"} matches "${query}". Pick one from the list.`
			: `Pick a value from the list for "${query}".`)
	setValidation(message, query)
}

function exactOption() {
	if (typeof inputValue.value !== "string" || suggestionSequence !== requestSequence) return null
	const query = inputValue.value.trim()
	return suggestions.value.find((option) => String(option.name) === query || String(option.label) === query) || null
}

function finishEdit({ validate = false } = {}) {
	const option = typeof inputValue.value === "string" ? exactOption() : blurredOption
	if (validate && !option) {
		rejectUnselected()
		if (validationError.value) return undefined
	}
	blurredOption = null
	setValidation()
	restoreCommittedValue()
	input.value?.hide()
	return option?.name ?? null
}

function restoreCommittedValue({ keepBlurredOption = false } = {}) {
	if (!keepBlurredOption) blurredOption = null
	cancelSearch()
	syncModelValue()
}

function syncModelValue() {
	inputValue.value = props.modelValue
		? { name: props.modelValue, label: modelLabel.value }
		: null
}

function focus() {
	input.value?.$el?.querySelector("input")?.focus()
}

async function open(query = "") {
	if (props.disabled) return
	blurredOption = null
	setValidation()
	focus()
	if (query) inputValue.value = query
	else input.value?.$el?.querySelector("input")?.select?.()
	await complete({ query })
	await focusFirstOption()
}

defineExpose({ focus, open, finishEdit })
</script>

<style scoped>
.common-field {
	display: grid;
	gap: 6px;
	width: 100%;
}

.link-field__error {
	color: var(--erp-danger);
	font-size: var(--erp-font-size-caption);
}

.common-field__help,
.link-field__empty {
	font-size: var(--erp-font-size-caption);
	color: var(--erp-text-muted);
}

.link-field__control {
	display: flex;
	align-items: center;
	gap: 4px;
}

.link-field__open {
	display: inline-grid;
	flex: 0 0 auto;
	place-items: center;
	width: var(--erp-control-height);
	height: var(--erp-control-height);
	border-radius: 50%;
}

.link-field__open:hover {
	background: var(--erp-surface-soft);
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
}

.link-field__empty {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	padding: 8px 10px;
}

.link-field__create {
	display: flex;
	align-items: center;
	gap: 6px;
	width: 100%;
	padding: 8px 10px;
	border: 0;
	border-top: 1px solid var(--erp-border);
	background: transparent;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	text-align: left;
	cursor: pointer;
}

.link-field__create:hover {
	background: var(--erp-surface-soft);
}

.link-field__option {
	display: grid;
	gap: 2px;
}

.link-field__option strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-semibold);
}

.link-field__option small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}
</style>
