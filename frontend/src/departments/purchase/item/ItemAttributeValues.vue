<template>
	<section class="attribute-values-view" aria-label="Attribute values">
		<h3>Attribute values</h3>
		<div class="attribute-values-grid">
			<article v-for="row in rows" :key="row.attribute" class="attribute-values-card">
				<header>
					<strong>{{ row.attribute }}</strong>
					<span>{{ attributeValuesSummary(row.values) }}</span>
					<Button v-if="editable" label="Edit" icon="pi pi-pencil" severity="secondary" text size="small" :aria-label="`Edit ${row.attribute} values`" @click="edit(row.attribute, $event)" />
				</header>
				<div v-if="!row.values.length" class="attribute-values__all">
					<strong>All {{ row.attribute }} values</strong>
					<span>No restriction<template v-if="row.value_count != null"> · {{ row.value_count }} values available</template></span>
					<span v-if="editable">Edit to restrict to specific values</span>
				</div>
				<div v-else class="attribute-values-card__chips">
					<span v-for="value in row.values" :key="value" :class="{ 'is-new': row.new_values?.includes(value) }">{{ value }}<small v-if="row.new_values?.includes(value)">New</small></span>
				</div>
			</article>
		</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"

import { attributeValueLabels, attributeValuesSummary } from "../purchaseViews.js"

const props = defineProps({
	attributes: { type: Array, default: () => [] },
	editable: { type: Boolean, default: false },
})
const emit = defineEmits(["edit"])

const rows = computed(() => props.attributes
	.filter((row) => row.attribute)
	.map((row) => ({ ...row, values: attributeValueLabels(row.values) })))

function edit(attribute, event) {
	event.currentTarget?.focus()
	emit("edit", attribute)
}
</script>

<style scoped>
.attribute-values-view { display: grid; min-width: 0; gap: var(--erp-space-2); }
.attribute-values-view h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.attribute-values-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--erp-space-3); }
.attribute-values-card { display: grid; min-width: 0; align-content: start; gap: var(--erp-space-2); padding: var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface-muted); }
.attribute-values-card > header { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-2); }
.attribute-values-card > header strong { overflow-wrap: anywhere; color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.attribute-values-card > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.attribute-values-card > header :deep(.p-button) { margin-left: auto; }
.attribute-values-card__chips { display: flex; min-width: 0; flex-wrap: wrap; gap: calc(var(--erp-space-1) + 2px); }
.attribute-values-card__chips span { display: inline-flex; max-width: 100%; align-items: center; gap: var(--erp-space-1); padding: 4px 8px; overflow-wrap: anywhere; color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 700; border: 1px solid color-mix(in srgb, var(--erp-accent) 20%, var(--erp-border)); border-radius: var(--erp-pill-radius); background: var(--erp-accent-soft); }
.attribute-values-card__chips span.is-new { border-style: dashed; }
.attribute-values-card__chips small { flex-shrink: 0; white-space: nowrap; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; text-transform: uppercase; }
.attribute-values__all { display: grid; min-width: 0; gap: var(--erp-space-1); padding: var(--erp-space-2) var(--erp-space-3); border: 1px solid color-mix(in srgb, var(--erp-accent) 24%, var(--erp-border)); border-radius: var(--erp-control-radius); background: var(--erp-accent-soft); }
.attribute-values__all strong { overflow-wrap: anywhere; color: var(--erp-accent-hover); font-size: var(--erp-font-size-caption); }
.attribute-values__all span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
@media (max-width: 650px) { .attribute-values-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
