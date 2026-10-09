<template>
	<section
		class="document-field-group-grid"
		:class="[rootClass, { 'document-field-group-grid--wide-last-odd': wideLastOdd }]"
		:aria-label="ariaLabel"
	>
		<article
			v-for="(group, index) in groups"
			:key="group.key"
			class="document-field-group-grid__card"
			:class="cardClass"
			:data-group="group.key"
			:aria-labelledby="headingId(group, index)"
		>
			<header class="document-field-group-grid__header">
				<div>
					<span>{{ group.eyebrow }}</span>
					<h2 :id="headingId(group, index)">{{ group.label }}</h2>
				</div>
				<small v-if="group.description">{{ group.description }}</small>
			</header>
			<div
				class="document-field-group-grid__content"
				:class="[contentClass, { 'document-field-group-grid__content--facts': facts }]"
			>
				<slot :group="group" />
			</div>
		</article>
	</section>
</template>

<script setup>
import { useId } from "vue"

defineProps({
	groups: { type: Array, default: () => [] },
	ariaLabel: { type: String, required: true },
	rootClass: { type: [String, Array, Object], default: "" },
	cardClass: { type: [String, Array, Object], default: "" },
	contentClass: { type: [String, Array, Object], default: "" },
	facts: { type: Boolean, default: false },
	wideLastOdd: { type: Boolean, default: false },
})

const componentId = useId()

function headingId(group, index) {
	return `${componentId}-${group.key || index}-heading`
}
</script>

<style scoped>
.document-field-group-grid { display: grid; min-width: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); overflow: visible; border: 0; border-radius: 0; background: transparent; }
.document-field-group-grid__card { overflow: hidden; min-width: 0; align-content: start; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 5px 18px rgb(28 61 45 / 3.5%); }
.document-field-group-grid__header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.document-field-group-grid__header > div { display: grid; gap: 2px; }
.document-field-group-grid__header span { color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .055em; text-transform: uppercase; }
.document-field-group-grid__header h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.document-field-group-grid__header > small { max-width: 46%; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); line-height: 1.35; text-align: right; }
.document-field-group-grid__content { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 10px; padding: 10px 12px 12px; }
.document-field-group-grid__content :deep(.form-field--wide) { grid-column: 1 / -1; }
@media (min-width: 1201px) {
	.document-field-group-grid--wide-last-odd .document-field-group-grid__card:last-child:nth-child(odd) { grid-column: 1 / -1; }
}
@media (max-width: 1200px) {
	.document-field-group-grid { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
	.document-field-group-grid__header { align-items: flex-start; }
	.document-field-group-grid__header > small { display: none; }
	.document-field-group-grid__content { grid-template-columns: 1fr; gap: 4px; padding: 10px; }
	.document-field-group-grid__content--facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
