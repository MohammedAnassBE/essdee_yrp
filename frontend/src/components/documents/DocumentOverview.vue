<template>
	<div class="document-overview" :aria-label="ariaLabel">
		<section
			v-for="group in groups"
			:key="group.key"
			class="document-overview__section"
			:class="{ 'document-overview__section--wide': group.wide }"
			:aria-labelledby="`${idPrefix}-${group.key}`"
		>
			<header>
				<div class="document-overview__icon" aria-hidden="true"><i :class="group.icon || 'pi pi-file'" /></div>
				<div>
					<h2 :id="`${idPrefix}-${group.key}`">{{ group.label }}</h2>
					<p v-if="group.description">{{ group.description }}</p>
				</div>
			</header>
			<dl class="document-overview__facts">
				<div v-for="field in group.fields" :key="field.fieldname" :class="{ 'document-overview__fact--wide': isWide(field) }">
					<dt>{{ field.label }}</dt>
					<dd :title="String(formatDocumentOverviewValue(field))">{{ formatDocumentOverviewValue(field) }}</dd>
				</div>
			</dl>
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { buildDocumentOverviewGroups, formatDocumentOverviewValue } from "../../utils/documentOverview.js"

const props = defineProps({
	fields: { type: Array, default: () => [] },
	definitions: { type: Array, default: () => [] },
	ariaLabel: { type: String, default: "Document overview" },
	idPrefix: { type: String, default: "document-overview" },
	includeUnclaimed: { type: Boolean, default: false },
	includeEmpty: { type: Boolean, default: false },
	unclaimedDefinition: { type: Object, default: () => ({}) },
})

const groups = computed(() => buildDocumentOverviewGroups(props.fields, props.definitions, {
	includeUnclaimed: props.includeUnclaimed,
	includeEmpty: props.includeEmpty,
	unclaimedDefinition: props.unclaimedDefinition,
}))

const multilineFieldtypes = new Set(["Small Text", "Text", "Long Text", "Text Editor", "Code"])
function isWide(field) {
	return multilineFieldtypes.has(field.fieldtype) && /address|comments?|notes?|remarks?|terms?/i.test(field.fieldname)
}
</script>

<style scoped>
.document-overview { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: var(--erp-space-3); }
.document-overview__section { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.document-overview__section--wide { grid-column: 1 / -1; }
.document-overview__section > header { display: flex; min-height: 64px; align-items: center; gap: 10px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface-soft) 78%, white); }
.document-overview__icon { display: inline-grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center; color: var(--erp-accent-hover); border: 1px solid var(--erp-accent-border); border-radius: 9px; background: var(--erp-accent-soft); }
.document-overview__icon i { font-size: .88rem; }
.document-overview__section header > div:last-child { min-width: 0; }
.document-overview__section h2 { margin: 0; color: var(--erp-text); font-size: 14px; font-weight: 760; letter-spacing: -.01em; }
.document-overview__section p { margin: 2px 0 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); line-height: 1.35; }
.document-overview__facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }
.document-overview__facts > div { display: grid; min-width: 0; min-height: 62px; align-content: center; gap: 4px; padding: 10px 13px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.document-overview__facts > div:nth-child(2n) { border-right: 0; }
.document-overview__facts > div:nth-last-child(-n + 2) { border-bottom: 0; }
.document-overview__facts > .document-overview__fact--wide { grid-column: 1 / -1; border-right: 0; }
.document-overview__facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .035em; text-transform: uppercase; }
.document-overview__facts dd { min-width: 0; margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; line-height: 1.4; overflow-wrap: anywhere; text-overflow: ellipsis; white-space: nowrap; }
.document-overview__fact--wide dd { white-space: pre-line; }
@media (max-width: 760px) { .document-overview { grid-template-columns: 1fr; } .document-overview__section--wide { grid-column: auto; } }
</style>
