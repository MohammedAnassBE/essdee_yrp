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
					<dd :title="String(formatDocumentOverviewValue(field))">
						<DocumentLink v-if="documentOverviewHasValue(field.value) && linkFieldTarget(field)" v-bind="linkFieldTarget(field)" :label="formatDocumentOverviewValue(field)" />
						<template v-else>{{ formatDocumentOverviewValue(field) }}</template>
					</dd>
				</div>
			</dl>
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"

import DocumentLink from "../common/DocumentLink.vue"
import { linkFieldTarget } from "../../utils/linkTarget.js"
import { buildDocumentOverviewGroups, documentOverviewHasValue, formatDocumentOverviewValue } from "../../utils/documentOverview.js"

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
.document-overview {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(min(420px, 100%), 1fr));
	align-items: start;
	gap: var(--erp-space-4);
}

.document-overview__section {
	min-width: 0;
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-card);
}

.document-overview__section--wide {
	grid-column: 1 / -1;
}

.document-overview__section > header {
	display: flex;
	align-items: center;
	gap: var(--erp-space-2);
	padding: 10px 16px;
	background: var(--erp-surface-soft);
	border-bottom: 1px solid var(--erp-border);
}

.document-overview__icon {
	display: inline-grid;
	flex: 0 0 auto;
	place-items: center;
	color: var(--erp-accent-ink);
}

.document-overview__icon i {
	font-size: var(--erp-font-size-table);
}

.document-overview__section header > div:last-child {
	display: flex;
	min-width: 0;
	flex-wrap: wrap;
	align-items: baseline;
	gap: 2px var(--erp-space-2);
}

.document-overview__section h2 {
	margin: 0;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: .02em;
}

.document-overview__section p {
	margin: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	line-height: 1.35;
}

.document-overview__facts {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	margin: 0;
	padding: 16px 18px 18px;
	gap: 4px 28px;
}

.document-overview__facts > div {
	display: flex;
	min-width: 0;
	flex-direction: column;
	gap: 2px;
	padding: 9px 0;
	border-bottom: 1px solid var(--erp-border);
}

.document-overview__facts > .document-overview__fact--wide {
	grid-column: 1 / -1;
}

.document-overview__facts dt {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: .03em;
	text-transform: uppercase;
	order: 2;
}

.document-overview__facts dd {
	min-width: 0;
	margin: 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
	font-weight: var(--erp-font-weight-semibold);
	line-height: 1.35;
	overflow-wrap: anywhere;
	order: 1;
}

.document-overview__fact--wide dd {
	white-space: pre-line;
}

@media (min-width: 1400px) {
	.document-overview {
		grid-template-columns: repeat(auto-fill, minmax(460px, 1fr));
	}
}

@media (max-width: 640px) {
	.document-overview__facts {
		grid-template-columns: 1fr;
		padding: 8px 14px 12px;
	}
}
</style>
