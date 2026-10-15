<template>
	<section class="pd-media-panel erp-card" :aria-labelledby="headingId">
		<div class="pd-media-panel__heading">
			<div>
				<span class="pd-media-panel__eyebrow">Trim mapping</span>
				<h2 :id="headingId">Trim Colour Combination</h2>
			</div>
			<span class="pd-media-panel__count">{{ selected.length }} selected</span>
		</div>

		<Message v-if="missingRows.length" severity="warn" :closable="false">
			Select a part and at least one colour before release for: {{ missingRows.join(", ") }}.
		</Message>

		<div v-if="selected.length" class="product-trim-combination__grid">
			<article
				v-for="(row, index) in selected"
				:key="`${row.image_name}-${index}`"
				class="product-trim-card"
				:draggable="!readonly"
				@dragstart="startDragging($event, index)"
				@dragover.prevent
				@drop="dropAt(index)"
				@dragend="draggedIndex = null"
			>
				<div class="product-trim-card__header">
					<div class="product-trim-card__preview">
						<img v-if="row.image_url" :src="row.image_url" :alt="row.image_title || 'Untitled'" />
						<i v-else class="pi pi-image" />
					</div>
					<div>
						<strong>{{ row.image_title || "Untitled" }}</strong>
						<span>{{ row.image_name }}</span>
					</div>
				</div>

				<fieldset v-if="isSetItem" class="product-trim-card__parts">
					<legend>Part</legend>
					<label v-for="part in ['Top', 'Bottom']" :key="part">
						<input
							type="radio"
							:value="part"
							:checked="row.selected_part === part"
							:disabled="readonly"
							@change="changePart(index, part)"
						/>
						<span>{{ part }}</span>
					</label>
				</fieldset>

				<fieldset class="product-trim-card__colours">
					<legend>
						<span>Colours</span>
						<Button
							v-if="!readonly && colourOptions(row).length"
							:label="hasAllColours(row) ? 'Clear all' : 'All colours'"
							severity="secondary"
							text
							size="small"
							@click="toggleAll(index)"
						/>
					</legend>
					<div v-if="colourOptions(row).length" class="product-trim-card__colour-grid">
						<label v-for="colour in colourOptions(row)" :key="colour.colour" class="product-colour-option">
							<input
								type="checkbox"
								:value="colour.colour"
								:checked="(row.selected_colours || []).includes(colour.colour)"
								:disabled="readonly"
								@change="toggleColour(index, colour.colour, $event.target.checked)"
							/>
							<span
								class="product-colour-option__chip"
								:style="{ backgroundColor: colour.colour_code || '#f4f5f7', color: readableTextColour(colour.colour_code) }"
							>{{ colour.colour }}</span>
							<img v-if="colour.image" :src="colour.image" :alt="`${colour.colour} colour`" />
						</label>
					</div>
					<p v-else>No colours are available for this part.</p>
				</fieldset>

				<div v-if="!readonly" class="product-trim-card__actions">
					<Button icon="pi pi-arrow-left" severity="secondary" text rounded :disabled="index === 0" :aria-label="`Move ${row.image_title || 'Untitled'} left`" @click="move(index, index - 1)" />
					<Button icon="pi pi-arrow-right" severity="secondary" text rounded :disabled="index === selected.length - 1" :aria-label="`Move ${row.image_title || 'Untitled'} right`" @click="move(index, index + 1)" />
					<Button icon="pi pi-times" severity="danger" text rounded :aria-label="`Remove ${row.image_title || 'Untitled'}`" @click="remove(index)" />
				</div>
			</article>
		</div>
		<div v-else class="pd-media-empty pd-media-empty--panel"><i class="pi pi-palette" /><span>No trim combinations selected</span></div>

		<div v-if="!readonly" class="product-trim-combination__library">
			<div class="product-trim-combination__search">
				<label :for="searchId">Search Product Images</label>
				<div>
					<InputText :id="searchId" v-model="query" fluid placeholder="Enter at least 2 characters" />
					<Button label="Create" icon="pi pi-plus" severity="secondary" @click="createVisible = true" />
				</div>
			</div>
			<p v-if="searching" class="product-trim-combination__status" role="status"><i class="pi pi-spin pi-spinner" /> Searching…</p>
			<div v-else-if="results.length" class="product-trim-combination__results">
				<button v-for="item in results" :key="item.image_name" type="button" @click="select(item)">
					<span class="product-trim-combination__result-image">
						<img v-if="item.image_url" :src="item.image_url" :alt="item.image_title || 'Untitled'" />
						<i v-else class="pi pi-image" />
					</span>
					<span class="product-trim-combination__result-caption">
						<strong>{{ item.image_title || "Untitled" }}</strong>
						<small>{{ item.image_name }}</small>
					</span>
				</button>
			</div>
			<p v-else-if="hasSearched" class="product-trim-combination__status">No Product Images match this search.</p>
		</div>

		<ProductImageCreateDialog v-model:visible="createVisible" :readonly="readonly" @created="handleCreated" />
		<DocumentErrorDialog :message="actionError" title="Product Images could not be searched" @dismiss="actionError = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import { computed, ref } from "vue"

import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import {
	addImage,
	colourOptionsFor,
	moveItem,
	readableTextColour,
	retainColoursForPart,
	rowsMissingTrimDetails,
	toggleAllColours,
} from "../pdViews.js"
import ProductImageCreateDialog from "./ProductImageCreateDialog.vue"
import { useProductImageSearch } from "./useProductImageSearch.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	colours: { type: Object, default: () => ({ is_set_item: false, top: [], bottom: [], all: [] }) },
	isSetItem: { type: Boolean, default: false },
	readonly: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const createVisible = ref(false)
const draggedIndex = ref(null)
const selected = computed(() => props.modelValue || [])
const missingRows = computed(() => rowsMissingTrimDetails(selected.value, props.isSetItem))
const { query, results, searching, hasSearched, actionError, refreshSearch } = useProductImageSearch()
const identity = Math.random().toString(36).slice(2)
const headingId = `product-trim-combination-${identity}`
const searchId = `${headingId}-search`

function update(rows) {
	emit("update:modelValue", rows)
}

function updateRow(index, row) {
	update(selected.value.map((current, rowIndex) => rowIndex === index ? row : current))
}

function select(item) {
	update(addImage(selected.value, item, {
		allowDuplicates: props.isSetItem,
		isSetItem: props.isSetItem,
		withColours: true,
	}))
}

function remove(index) {
	update(selected.value.filter((_row, rowIndex) => rowIndex !== index))
}

function move(from, to) {
	update(moveItem(selected.value, from, to))
}

function startDragging(event, index) {
	if (props.readonly) return
	draggedIndex.value = index
	event.dataTransfer.effectAllowed = "move"
}

function dropAt(targetIndex) {
	if (draggedIndex.value === null || props.readonly) return
	move(draggedIndex.value, targetIndex)
	draggedIndex.value = null
}

function colourOptions(row) {
	return colourOptionsFor(props.colours, row.selected_part)
}

function changePart(index, part) {
	const row = { ...selected.value[index], selected_part: part }
	updateRow(index, retainColoursForPart(row, props.colours))
}

function toggleColour(index, colour, checked) {
	const values = new Set(selected.value[index].selected_colours || [])
	if (checked) values.add(colour)
	else values.delete(colour)
	updateRow(index, { ...selected.value[index], selected_colours: [...values] })
}

function hasAllColours(row) {
	const names = colourOptions(row).map((colour) => colour.colour)
	const selectedColours = new Set(row.selected_colours || [])
	return names.length > 0 && names.every((name) => selectedColours.has(name))
}

function toggleAll(index) {
	updateRow(index, toggleAllColours(selected.value[index], colourOptions(selected.value[index])))
}

async function handleCreated(name) {
	await refreshSearch(name)
}
</script>

<style scoped>
.pd-media-panel { display: grid; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-4); }
.pd-media-panel__heading { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.pd-media-panel__heading > div { display: grid; min-width: 0; gap: 3px; }
.pd-media-panel__heading h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 760; }
.pd-media-panel__eyebrow { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: 0.04em; text-transform: uppercase; }
.pd-media-panel__count { flex: 0 0 auto; padding: 4px 9px; color: var(--erp-text-secondary); border: 1px solid var(--erp-border); border-radius: 999px; background: var(--erp-bg); font-size: var(--erp-font-size-min); font-weight: 680; }
.pd-media-empty { display: grid; align-content: center; justify-items: center; gap: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.pd-media-empty i { font-size: 1.5rem; }
.pd-media-empty--panel { min-height: 120px; border: 1px dashed var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-trim-combination__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); }
.product-trim-card { display: grid; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.product-trim-card[draggable="true"] { cursor: grab; }
.product-trim-card__header { display: grid; grid-template-columns: 110px minmax(0, 1fr); align-items: center; gap: 12px; }
.product-trim-card__header > div:last-child { display: grid; min-width: 0; gap: 4px; }
.product-trim-card__header strong, .product-trim-card__header span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-trim-card__header strong { color: var(--erp-text); font-size: var(--erp-font-size-body); }
.product-trim-card__header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.product-trim-card__preview { display: flex; height: 90px; overflow: hidden; align-items: center; justify-content: center; border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-trim-card__preview img { display: block; width: 100%; height: 100%; background: white; object-fit: contain; }
.product-trim-card fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
.product-trim-card legend { width: 100%; margin-bottom: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; text-transform: uppercase; }
.product-trim-card__colours legend { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.product-trim-card__colours legend :deep(.p-button) { padding-block: 3px; text-transform: none; }
.product-trim-card__parts { display: flex; gap: var(--erp-space-4); }
.product-trim-card__parts label { display: inline-flex; align-items: center; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.product-trim-card__colour-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.product-colour-option { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 7px; padding: 6px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.product-colour-option__chip { overflow: hidden; padding: 5px 8px; border: 1px solid color-mix(in srgb, currentColor 18%, transparent); border-radius: 999px; font-size: var(--erp-font-size-min); text-align: center; text-overflow: ellipsis; white-space: nowrap; }
.product-colour-option img { width: 50px; height: 50px; border-radius: 5px; background: white; object-fit: contain; }
.product-trim-card__colours p, .product-trim-combination__status { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.product-trim-card__actions { display: flex; justify-content: flex-end; gap: 2px; }
.product-trim-combination__library { display: grid; gap: var(--erp-space-3); padding-top: var(--erp-space-3); border-top: 1px solid var(--erp-border); }
.product-trim-combination__search { display: grid; gap: 7px; }
.product-trim-combination__search > label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.product-trim-combination__search > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.product-trim-combination__results { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); }
.product-trim-combination__results button { display: grid; min-width: 0; gap: 8px; padding: 9px; color: var(--erp-text); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); cursor: pointer; text-align: left; }
.product-trim-combination__results button:hover { border-color: var(--erp-accent); background: var(--erp-accent-soft); }
.product-trim-combination__result-image { display: flex; height: 125px; overflow: hidden; align-items: center; justify-content: center; border-radius: calc(var(--erp-control-radius) - 2px); background: var(--erp-bg); }
.product-trim-combination__result-image img { display: block; width: 100%; height: 100%; background: white; object-fit: contain; }
.product-trim-combination__result-caption { display: grid; min-width: 0; gap: 3px; }
.product-trim-combination__result-caption strong, .product-trim-combination__result-caption small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-trim-combination__result-caption strong { font-size: var(--erp-font-size-caption); }
.product-trim-combination__result-caption small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
@media (max-width: 880px) { .product-trim-combination__grid { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .product-trim-card__colour-grid, .product-trim-combination__results { grid-template-columns: 1fr; } }
</style>
