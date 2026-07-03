<!--
  LinkField — a Link / Dynamic Link input: PrimeVue AutoComplete + a "go to
  linked document" button (mirrors the Frappe Desk link arrow). The button opens
  the linked record's /web detail (or the Desk form, for doctypes not in the /web
  registry) in a NEW TAB, so the current form/edit isn't lost.

  The parent resolves the target doctype (incl. Dynamic Links → the controlling
  field's value) and passes it as `target-doctype`. Search is internal.
-->
<template>
	<div class="link-field">
		<AutoComplete
			:modelValue="modelValue"
			@update:modelValue="onModelUpdate"
			:suggestions="suggestions"
			optionLabel="label"
			@complete="onComplete"
			@item-select="onItemSelect"
			@change="$emit('change', $event)"
			:disabled="disabled"
			:invalid="invalid"
			:placeholder="placeholder || ('Search ' + (targetDoctype || '') + '…')"
			:dropdown="dropdown"
			completeOnFocus
			class="fld fld-link"
			fluid
		>
			<!-- Q14: honest empty state — searching vs no-matches vs a retryable
			     search error, so a flaky-network failure never reads as "nothing
			     exists". -->
			<template #empty>
				<div class="lf-empty">
					<span v-if="searching"><i class="pi pi-spin pi-spinner" /> Searching…</span>
					<span
						v-else-if="errored"
						class="lf-retry"
						@mousedown.prevent="retrySearch"
					><i class="pi pi-refresh" /> Couldn’t search — retry</span>
					<span v-else>No matches</span>
				</div>
			</template>
		</AutoComplete>
		<Button
			v-if="modelValue && targetDoctype"
			icon="pi pi-arrow-up-right"
			text
			rounded
			size="small"
			class="link-goto"
			v-tooltip.top="'Open ' + modelValue"
			@click="openLinked"
		/>
	</div>
</template>

<script setup>
import { ref } from "vue"
import AutoComplete from "primevue/autocomplete"
import Button from "primevue/button"
import Tooltip from "primevue/tooltip"
import { searchLink } from "@/api/client"
import { getRegistryByDoctype } from "@/config/doctypes"

const vTooltip = Tooltip

const props = defineProps({
	modelValue: { type: [String, Number], default: "" },
	// Resolved target doctype (parent resolves Dynamic Links before passing).
	targetDoctype: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	filters: { type: Object, default: () => ({}) },
	// Show the select-style dropdown chevron. Default true (existing pickers).
	// Pass false for a clean "Link field" look — a search/typeahead input with no
	// select chevron (suggestions still appear on focus + as you type).
	dropdown: { type: Boolean, default: true },
	// Optional custom search: async (query) => Array<{ name }>. When provided,
	// it replaces the default name-like search (used for Addresses where the
	// link is via Dynamic Link rather than a direct field, so a plain filter
	// can't reach the parent party — see `searchAddressForParty`).
	searchHandler: { type: Function, default: null },
})
const emit = defineEmits(["update:modelValue", "item-select", "change"])

// Suggestions are objects { name, label } — `label` (title/search-field text) is
// shown via optionLabel, while `name` is the value stored on select. A search
// handler may still return plain {name} rows (no label) — we normalise those so
// the dropdown always has a label to render.
const suggestions = ref([])
// Q14: search lifecycle so the empty panel can tell pending / failed / no-match
// apart. `lastQuery` lets the error state offer a retry of the same search.
const searching = ref(false)
const errored = ref(false)
let lastQuery = ""

function normaliseRows(rows) {
	return (rows || []).map((r) =>
		typeof r === "string"
			? { name: r, label: r }
			: { name: r.name, label: r.label || r.name },
	)
}

async function runSearch(query) {
	lastQuery = query
	if (!props.searchHandler && !props.targetDoctype) {
		suggestions.value = []
		return
	}
	searching.value = true
	errored.value = false
	try {
		const rows = props.searchHandler
			? await props.searchHandler(query)
			: await searchLink(props.targetDoctype, query, props.filters)
		suggestions.value = normaliseRows(rows)
	} catch (_) {
		suggestions.value = []
		errored.value = true
	} finally {
		searching.value = false
	}
}

function onComplete(e) {
	runSearch(e.query || "")
}
function retrySearch() {
	runSearch(lastQuery)
}

// Selecting a suggestion stores its `name` (the Link value), not the object.
function onItemSelect(e) {
	const name = e?.value?.name ?? e?.value ?? ""
	emit("update:modelValue", name)
	emit("item-select", { value: name, originalEvent: e?.originalEvent })
}

// Free-text typing / clearing comes through as a string; an object can slip
// through if PrimeVue echoes the selected suggestion — normalise to the name.
function onModelUpdate(v) {
	emit("update:modelValue", v && typeof v === "object" ? v.name : v)
}

// Open the linked record (new tab): /web detail if the doctype is in the registry,
// else the Desk form. New tab keeps the current form/edit intact.
function openLinked() {
	if (!props.modelValue || !props.targetDoctype) return
	const reg = getRegistryByDoctype(props.targetDoctype)
	const path = reg
		? `/web/${reg.route}/${encodeURIComponent(props.modelValue)}`
		: `/app/${encodeURIComponent(props.targetDoctype.toLowerCase().replace(/ /g, "-"))}/${encodeURIComponent(props.modelValue)}`
	window.open(window.location.origin + path, "_blank", "noopener")
}
</script>

<style scoped>
.link-field {
	display: flex;
	align-items: center;
	gap: 4px;
}
.link-field .fld-link {
	flex: 1;
	min-width: 0;
}
.link-goto {
	flex-shrink: 0;
	color: var(--esd-accent-700);
}

/* Q14: empty-panel states. */
.lf-empty {
	padding: 8px 12px;
	font-size: 12.5px;
	color: var(--esd-muted);
}
.lf-empty .pi {
	font-size: 11px;
	margin-right: 4px;
}
.lf-retry {
	color: var(--esd-accent-700);
	font-weight: 600;
	cursor: pointer;
}
.lf-retry:hover {
	text-decoration: underline;
}
</style>
