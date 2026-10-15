<template>
	<section class="pd-media-panel erp-card" :aria-labelledby="headingId">
		<div class="pd-media-panel__heading">
			<div>
				<span class="pd-media-panel__eyebrow">Image library</span>
				<h2 :id="headingId">{{ label }} Images</h2>
			</div>
			<span class="pd-media-panel__count">{{ selected.length }} selected</span>
		</div>

		<div v-if="selected.length" class="product-image-picker__selected">
			<article
				v-for="(item, index) in selected"
				:key="item.image_name"
				class="product-image-card"
				:draggable="!readonly"
				@dragstart="startDragging($event, index)"
				@dragover.prevent
				@drop="dropAt(index)"
				@dragend="draggedIndex = null"
			>
				<div class="product-image-card__preview">
					<img v-if="item.image_url" :src="item.image_url" :alt="item.image_title || 'Untitled'" />
					<div v-else class="pd-media-empty"><i class="pi pi-image" /><span>No preview</span></div>
				</div>
				<div class="product-image-card__caption">
					<strong>{{ item.image_title || "Untitled" }}</strong>
					<span>{{ item.image_name }}</span>
				</div>
				<div v-if="!readonly" class="product-image-card__actions">
					<Button
						icon="pi pi-arrow-left"
						severity="secondary"
						text
						rounded
						:disabled="index === 0"
						:aria-label="`Move ${item.image_title || 'Untitled'} left`"
						@click="move(index, index - 1)"
					/>
					<Button
						icon="pi pi-arrow-right"
						severity="secondary"
						text
						rounded
						:disabled="index === selected.length - 1"
						:aria-label="`Move ${item.image_title || 'Untitled'} right`"
						@click="move(index, index + 1)"
					/>
					<Button
						icon="pi pi-times"
						severity="danger"
						text
						rounded
						:aria-label="`Remove ${item.image_title || 'Untitled'}`"
						@click="remove(index)"
					/>
				</div>
			</article>
		</div>
		<div v-else class="pd-media-empty pd-media-empty--panel"><i class="pi pi-images" /><span>No {{ label.toLowerCase() }} images selected</span></div>

		<div v-if="!readonly" class="product-image-picker__library">
			<div class="product-image-picker__search">
				<label :for="searchId">Search Product Images</label>
				<div>
					<InputText :id="searchId" v-model="query" fluid placeholder="Enter at least 2 characters" />
					<Button label="Create" icon="pi pi-plus" severity="secondary" @click="createVisible = true" />
				</div>
			</div>
			<p v-if="searching" class="product-image-picker__status" role="status"><i class="pi pi-spin pi-spinner" /> Searching…</p>
			<div v-else-if="results.length" class="product-image-picker__results">
				<button v-for="item in results" :key="item.image_name" type="button" @click="select(item)">
					<span class="product-image-picker__result-image">
						<img v-if="item.image_url" :src="item.image_url" :alt="item.image_title || 'Untitled'" />
						<i v-else class="pi pi-image" />
					</span>
					<span class="product-image-picker__result-caption">
						<strong>{{ item.image_title || "Untitled" }}</strong>
						<small>{{ item.image_name }}</small>
					</span>
				</button>
			</div>
			<p v-else-if="hasSearched" class="product-image-picker__status">No Product Images match this search.</p>
		</div>

		<ProductImageCreateDialog v-model:visible="createVisible" :readonly="readonly" @created="handleCreated" />
		<DocumentErrorDialog
			:message="actionError"
			title="Product Images could not be searched"
			@dismiss="actionError = ''"
		/>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import { computed, ref } from "vue"

import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { addImage, moveItem } from "../pdViews.js"
import ProductImageCreateDialog from "./ProductImageCreateDialog.vue"
import { useProductImageSearch } from "./useProductImageSearch.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	label: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const createVisible = ref(false)
const draggedIndex = ref(null)
const selected = computed(() => props.modelValue || [])
const { query, results, searching, hasSearched, actionError, refreshSearch } = useProductImageSearch()
const identity = Math.random().toString(36).slice(2)
const headingId = `product-${props.label.toLowerCase()}-${identity}`
const searchId = `${headingId}-search`

function update(rows) {
	emit("update:modelValue", rows)
}

function select(item) {
	update(addImage(selected.value, item, { allowDuplicates: false }))
}

function remove(index) {
	update(selected.value.filter((_item, itemIndex) => itemIndex !== index))
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
.product-image-picker__selected,
.product-image-picker__results { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); }
.product-image-card { position: relative; display: grid; min-width: 0; overflow: hidden; gap: 9px; padding: 10px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.product-image-card[draggable="true"] { cursor: grab; }
.product-image-card__preview { display: flex; height: 150px; overflow: hidden; align-items: center; justify-content: center; border-radius: calc(var(--erp-control-radius) - 2px); background: var(--erp-bg); }
.product-image-card__preview img { display: block; width: 100%; height: 100%; background: white; object-fit: contain; }
.product-image-card__caption { display: grid; min-width: 0; gap: 3px; text-align: center; }
.product-image-card__caption strong, .product-image-card__caption span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-image-card__caption strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.product-image-card__caption span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.product-image-card__actions { display: flex; justify-content: center; gap: 2px; }
.product-image-picker__library { display: grid; gap: var(--erp-space-3); padding-top: var(--erp-space-3); border-top: 1px solid var(--erp-border); }
.product-image-picker__search { display: grid; gap: 7px; }
.product-image-picker__search > label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.product-image-picker__search > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.product-image-picker__results button { display: grid; min-width: 0; gap: 8px; padding: 9px; color: var(--erp-text); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); cursor: pointer; text-align: left; }
.product-image-picker__results button:hover { border-color: var(--erp-accent); background: var(--erp-accent-soft); }
.product-image-picker__result-caption { display: grid; min-width: 0; gap: 3px; }
.product-image-picker__result-caption strong, .product-image-picker__result-caption small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-image-picker__result-caption strong { font-size: var(--erp-font-size-caption); }
.product-image-picker__result-caption small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.product-image-picker__result-image { display: flex; height: 125px; overflow: hidden; align-items: center; justify-content: center; border-radius: calc(var(--erp-control-radius) - 2px); background: var(--erp-bg); }
.product-image-picker__result-image img { display: block; width: 100%; height: 100%; background: white; object-fit: contain; }
.product-image-picker__status { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
@media (max-width: 880px) { .product-image-picker__selected, .product-image-picker__results { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .product-image-picker__selected, .product-image-picker__results { grid-template-columns: 1fr; } }
</style>
