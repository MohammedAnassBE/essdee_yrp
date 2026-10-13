<template>
	<section class="product-size-chips erp-card" aria-label="Sizes from Size Range">
		<span class="product-size-chips__label">Sizes from Size Range</span>
		<div v-if="sizes.length" class="product-size-chips__list">
			<Tag v-for="(size, index) in sizes" :key="`${size.value}-${index}`" :value="size.label" severity="secondary" />
		</div>
		<p v-else>{{ emptyText }}</p>
	</section>
</template>

<script setup>
import Tag from "primevue/tag"
import { computed } from "vue"

const props = defineProps({
	rows: { type: Array, default: () => [] },
	labels: { type: Object, default: () => ({}) },
	hasSizeRange: { type: Boolean, default: false },
})

const sizes = computed(() => (props.rows || []).map((row) => ({
	value: row.attribute_value,
	label: row.size || props.labels[row.attribute_value] || row.attribute_value || "Unknown size",
})))
const emptyText = computed(() => props.hasSizeRange
	? "No sizes are configured for this Size Range."
	: "Choose a Size Range to see its sizes.")
</script>

<style scoped>
.product-size-chips { display: grid; gap: var(--erp-space-3); padding: var(--erp-space-4); border: 1px solid var(--erp-border); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); }
.product-size-chips__label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.product-size-chips__list { display: flex; flex-wrap: wrap; gap: 8px; }
.product-size-chips p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
</style>
