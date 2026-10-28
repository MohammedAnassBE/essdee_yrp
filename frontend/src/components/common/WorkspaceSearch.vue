<template>
	<div class="workspace-search" @keydown.capture="onKeydown">
		<AutoComplete
			ref="input"
			v-model="value"
			:input-id="inputId"
			:suggestions="suggestions"
			option-label="label"
			option-group-label="label"
			option-group-children="items"
			:placeholder="placeholder"
			:pt="autocompletePt"
			aria-label="Search cards and reports"
			title="Search cards and reports (/ or Ctrl+K)"
			dropdown
			show-clear
			complete-on-focus
			auto-option-focus
			focus-on-hover
			fluid
			@complete="complete"
			@item-select="select($event.value)"
			@clear="emit('select-card', '')"
			@update:model-value="onInput"
		>
			<template #optiongroup="{ option }">
				<span class="workspace-search__group">{{ option.label }}</span>
			</template>
			<template #option="{ option }">
				<span class="workspace-search__option">
					<i :class="option.icon" aria-hidden="true" />
					<span>{{ option.label }}</span>
					<small v-if="option.group">{{ option.group }}</small>
				</span>
			</template>
			<template #empty>No card or report matches.</template>
		</AutoComplete>
	</div>
</template>

<script setup>
import PrimeAutoComplete from "primevue/autocomplete"
import { onBeforeUnmount, onMounted, ref, useId } from "vue"
import { useRouter } from "vue-router"

import { handleAutocompleteKey, withAutocompleteCompositionGuard } from "./autocompleteKeys.js"
import { isWorkspaceSearchShortcut, workspaceReportTarget, workspaceSearchGroups } from "./workspaceSearch.js"

/** Department search: pick a card to show only it, or a report to open it. */
const props = defineProps({
	cards: { type: Array, default: () => [] },
	reports: { type: Array, default: () => [] },
	reportsTo: { type: [String, Object], default: "" },
	reportQueryKey: { type: String, default: "report" },
	placeholder: { type: String, default: "Search cards and reports  ( / )" },
})
const emit = defineEmits(["select-card"])
const AutoComplete = withAutocompleteCompositionGuard(PrimeAutoComplete)
const router = useRouter()
const input = ref(null)
const inputId = `workspace-search-${useId()}`
const value = ref("")
const suggestions = ref([])
const autocompletePt = {
	option: { onMousedown: (event) => event.preventDefault() },
	dropdown: { "aria-label": "Show all cards and reports", title: "Show all cards and reports" },
}

function complete(event) {
	suggestions.value = workspaceSearchGroups(props.cards, props.reports, event.query)
}

function select(option) {
	if (option.type === "card") return emit("select-card", option.key)
	value.value = ""
	emit("select-card", "")
	router.push(workspaceReportTarget(props.reportsTo, option.key, props.reportQueryKey))
}

function onInput(next) {
	if (next === "" || next == null) emit("select-card", "")
}

function onKeydown(event) {
	handleAutocompleteKey(event, input.value)
}

function onWindowKeydown(event) {
	if (!isWorkspaceSearchShortcut(event)) return
	event.preventDefault()
	document.getElementById(inputId)?.focus()
}

onMounted(() => window.addEventListener("keydown", onWindowKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onWindowKeydown))
</script>

<style scoped>
.workspace-search {
	width: 100%;
	min-width: 0;
}

.workspace-search__group {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	font-weight: var(--erp-font-weight-semibold);
	text-transform: uppercase;
	letter-spacing: 0.04em;
}

.workspace-search__option {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr) auto;
	width: 100%;
	align-items: center;
	gap: var(--erp-space-2);
}

.workspace-search__option i {
	color: var(--erp-accent-ink);
}

.workspace-search__option small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}
</style>
