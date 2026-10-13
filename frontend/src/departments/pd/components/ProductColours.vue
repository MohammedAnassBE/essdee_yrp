<template>
	<section class="product-colours erp-card" aria-labelledby="product-colours-heading">
		<div class="product-colours__heading">
			<div>
				<h2 id="product-colours-heading">Product Colours</h2>
				<span>{{ rows.length }} rows</span>
			</div>
		</div>

		<div v-if="!disabled" class="product-colours__quick-add">
			<label for="product-colour-quick-add">Quick add colours</label>
			<div>
				<MultiSelect
					input-id="product-colour-quick-add"
					:model-value="pending"
					:options="options"
					option-label="colour"
					:filter-fields="filterFields"
					filter
					:show-toggle-all="false"
					display="chip"
					fluid
					:loading="loading"
					placeholder="Select submitted colours"
					@filter="queueSearch"
					@update:model-value="updatePending"
				>
					<template #option="{ option }">
						<span class="product-colours__option">
							<i :style="swatchStyle(option.colour_code)" />
							<strong>{{ option.colour || option.name }}</strong>
							<small>{{ option.colour_code }}</small>
						</span>
					</template>
					<template #chip="{ value }">
						<span class="product-colours__chip"><i :style="swatchStyle(value.colour_code)" />{{ value.colour || value.name }}</span>
					</template>
				</MultiSelect>
				<Button label="Add selected" icon="pi pi-plus" :disabled="!pending.length" @click="addSelected" />
			</div>
			<small>Submitted colours only. Add the same colour again when the tech pack needs a duplicate row.</small>
		</div>

		<div v-if="rows.length" class="product-colours__list">
			<div v-for="(row, index) in rows" :key="row.name || `${row.product_colour}-${index}`" class="product-colours__row">
				<i class="product-colours__swatch" :style="swatchStyle(detailsFor(row).colour_code)" />
				<div>
					<strong>{{ row.product_colour || "Unnamed colour" }}</strong>
					<span>{{ detailsFor(row).colour_code || "No colour code" }}</span>
				</div>
				<Tag v-if="duplicateCount(row.product_colour) > 1" :value="`x${duplicateCount(row.product_colour)}`" severity="secondary" />
				<Button v-if="!disabled" icon="pi pi-times" severity="danger" text rounded :aria-label="`Remove ${row.product_colour || 'colour'}`" @click="remove(index)" />
			</div>
		</div>
		<p v-else class="product-colours__empty">No product colours added.</p>

		<DocumentErrorDialog :message="actionError" title="Colours could not be loaded" @dismiss="actionError = ''" />
	</section>
</template>

<script setup>
import { FilterService } from "@primevue/core/api"
import Button from "primevue/button"
import MultiSelect from "primevue/multiselect"
import Tag from "primevue/tag"
import { computed, onBeforeUnmount, ref, watch } from "vue"

import { getSubmittedColourCodes } from "../../../api/pd.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { appendProductColours, mergeFilteredSelection, renumberRows } from "../pdViews.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const options = ref([])
const pending = ref([])
const loading = ref(false)
const actionError = ref("")
const filterFields = ["colour", "name", "colour_code"]
let loadSequence = 0
let searchTimer = null

const rows = computed(() => props.modelValue || [])
const optionByName = computed(() => new Map(options.value.map((option) => [option.name, option])))
const filterValue = ref("")
const visibleOptions = computed(() => {
	if (!filterValue.value) return options.value
	return FilterService.filter(options.value, filterFields, filterValue.value, "contains")
})
const counts = computed(() => {
	const values = new Map()
	for (const row of rows.value) values.set(row.product_colour, (values.get(row.product_colour) || 0) + 1)
	return values
})

watch(() => props.disabled, (disabled) => {
	if (disabled) {
		filterValue.value = ""
		window.clearTimeout(searchTimer)
	} else if (!options.value.length) loadOptions()
}, { immediate: true })

function queueSearch(event) {
	filterValue.value = event.value || ""
	window.clearTimeout(searchTimer)
	searchTimer = window.setTimeout(() => loadOptions(event.value || ""), 250)
}

function updatePending(value) {
	pending.value = mergeFilteredSelection(pending.value, value, visibleOptions.value)
}

async function loadOptions(query = "") {
	const sequence = ++loadSequence
	loading.value = true
	actionError.value = ""
	try {
		const result = await getSubmittedColourCodes(query)
		if (sequence === loadSequence) {
			const selected = new Map(pending.value.map((option) => [option.name, option]))
			for (const option of result || []) selected.set(option.name, option)
			options.value = [...selected.values()]
		}
	} catch (reason) {
		if (sequence === loadSequence) actionError.value = reason?.message || "Unable to load submitted colours."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function addSelected() {
	if (!pending.value.length || props.disabled) return
	emit("update:modelValue", appendProductColours(rows.value, pending.value))
	pending.value = []
}

function remove(index) {
	if (props.disabled) return
	emit("update:modelValue", renumberRows(rows.value.filter((_row, rowIndex) => rowIndex !== index)))
}

function detailsFor(row) {
	return optionByName.value.get(row.product_colour) || row
}

function duplicateCount(name) {
	return counts.value.get(name) || 0
}

function swatchStyle(code) {
	return { backgroundColor: code || "#f4f5f7" }
}

onBeforeUnmount(() => {
	++loadSequence
	window.clearTimeout(searchTimer)
})
</script>

<style scoped>
.product-colours { display: grid; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-4); border: 1px solid var(--erp-border); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); }
.product-colours__heading > div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.product-colours__heading h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.product-colours__heading span, .product-colours__quick-add small, .product-colours__empty { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.product-colours__quick-add { display: grid; gap: 7px; padding-bottom: var(--erp-space-3); border-bottom: 1px solid var(--erp-border); }
.product-colours__quick-add > label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.product-colours__quick-add > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.product-colours__option, .product-colours__chip { display: inline-flex; min-width: 0; align-items: center; gap: 8px; }
.product-colours__option i, .product-colours__chip i { width: 18px; height: 18px; flex: 0 0 auto; border: 1px solid var(--erp-border-strong); border-radius: 50%; }
.product-colours__option strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-colours__option small { margin-left: auto; color: var(--erp-text-muted); }
.product-colours__list { display: grid; gap: 8px; }
.product-colours__row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: 10px; padding: 9px 10px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-colours__swatch { width: 30px; height: 30px; border: 1px solid var(--erp-border-strong); border-radius: 7px; }
.product-colours__row > div { display: grid; min-width: 0; gap: 2px; }
.product-colours__row strong, .product-colours__row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-colours__row strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.product-colours__row span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.product-colours__empty { margin: 0; }
@media (max-width: 620px) { .product-colours__quick-add > div { grid-template-columns: 1fr; } }
</style>
