<template>
	<section class="pd-media-panel erp-card" aria-labelledby="product-measurement-heading">
		<div class="pd-media-panel__heading">
			<div>
				<span class="pd-media-panel__eyebrow">Reference details</span>
				<h2 id="product-measurement-heading">Measurement Details</h2>
			</div>
		</div>

		<div v-if="images.length" class="product-measurement__images" :class="{ 'product-measurement__images--set': isSetItem }">
			<figure v-for="(image, index) in images" :key="`${image.label}-${image.url}`">
				<figcaption>{{ imageLabel(image, index) }}</figcaption>
				<img :src="image.url" :alt="imageLabel(image, index)" />
			</figure>
		</div>

		<div v-if="groupEntries.length" class="product-measurement__groups">
			<article v-for="([group, rows]) in groupEntries" :key="group">
				<h3>{{ group }} Description</h3>
				<div class="product-measurement__rows">
					<label v-for="(row, index) in rows" :key="index">
						<span>{{ index + 1 }}</span>
						<input type="text" :value="description(row)" readonly :aria-label="`${group} description ${index + 1}`" />
					</label>
				</div>
			</article>
		</div>
		<div v-else-if="!images.length" class="pd-media-empty pd-media-empty--panel">
			<i class="pi pi-chart-bar" /><span>No measurement details available</span>
		</div>
	</section>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	measurement: { type: Object, default: () => ({ groups: {}, images: [] }) },
	isSetItem: { type: Boolean, default: false },
	readonly: { type: Boolean, default: true },
})

const images = computed(() => props.measurement?.images || [])
const groupEntries = computed(() => Object.entries(props.measurement?.groups || {}))

function imageLabel(image, index) {
	if (!props.isSetItem) return "Measurement Image"
	if (image.label === "Bottom" || index === 1) return "Bottom Measurement Image"
	return "Top Measurement Image"
}

function description(row) {
	return String(row?.description ?? row ?? "")
}
</script>

<style scoped>
.pd-media-panel { display: grid; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-4); }
.pd-media-panel__heading { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.pd-media-panel__heading > div { display: grid; min-width: 0; gap: 3px; }
.pd-media-panel__heading h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 760; }
.pd-media-panel__eyebrow { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: 0.04em; text-transform: uppercase; }
.pd-media-empty { display: grid; align-content: center; justify-items: center; gap: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.pd-media-empty i { font-size: 1.5rem; }
.pd-media-empty--panel { min-height: 120px; border: 1px dashed var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-measurement__images { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--erp-space-3); }
.product-measurement__images--set { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.product-measurement__images figure { display: grid; min-width: 0; gap: 8px; margin: 0; }
.product-measurement__images figcaption { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 720; text-align: center; }
.product-measurement__images img { width: 100%; height: 270px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: white; object-fit: contain; }
.product-measurement__groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: var(--erp-space-3); }
.product-measurement__groups article { display: grid; align-content: start; gap: 10px; padding: var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.product-measurement__groups h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); font-weight: 720; }
.product-measurement__rows { display: grid; gap: 8px; }
.product-measurement__rows label { display: grid; grid-template-columns: 32px minmax(0, 1fr); align-items: center; gap: 8px; }
.product-measurement__rows label > span { display: grid; min-height: 34px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); border: 1px solid var(--erp-border); border-radius: 5px; background: var(--erp-bg); place-items: center; }
.product-measurement__rows input { min-width: 0; min-height: 36px; padding: 7px 10px; color: var(--erp-text); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); font: inherit; }
@media (max-width: 720px) { .product-measurement__images--set { grid-template-columns: 1fr; } }
</style>
