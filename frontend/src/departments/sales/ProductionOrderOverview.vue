<template>
	<section class="ppo-overview erp-card" aria-labelledby="ppo-overview-heading">
		<header><h2 id="ppo-overview-heading">Details</h2></header>
		<div class="ppo-overview__facts">
			<div v-for="field in visibleFields" :key="field.fieldname" :class="{ 'ppo-overview__wide': /comments/i.test(field.fieldname) }">
				<span>{{ field.label }}</span><strong><DocumentLink :doctype="linkFieldTarget(field)?.doctype" :name="linkFieldTarget(field)?.name" :label="display(field)" /></strong>
			</div>
		</div>
	</section>
</template>

<script setup>
import DocumentLink from "../../components/common/DocumentLink.vue"
import { computed } from "vue"
import { linkFieldTarget } from "../../utils/linkTarget.js"
import { plainTextFromHtml } from "../../utils/documentValues.js"

const props = defineProps({ fields: { type: Array, default: () => [] } })
const hidden = new Set(["status", "item"])
const visibleFields = computed(() => props.fields.filter((field) => !hidden.has(field.fieldname)))

function display(field) {
	const value = field.value
	if (value === null || value === undefined || value === "") return "—"
	if ((field.fieldtype === "Date" || /date$/i.test(field.fieldname)) && /^\d{4}-\d{2}-\d{2}/.test(String(value))) {
		const [year, month, day] = String(value).slice(0, 10).split("-")
		return `${day}-${month}-${year}`
	}
	if (field.fieldname === "skip_box_sticker_print") return Number(value) ? "Yes" : "No"
	return plainTextFromHtml(value)
}
</script>

<style scoped>
.ppo-overview {
	min-width: 0;
	overflow: hidden;
}

.ppo-overview > header {
	padding: 10px 16px;
	background: var(--erp-surface-soft);
	border-bottom: 1px solid var(--erp-border);
}

.ppo-overview h2 {
	margin: 0;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: .02em;
}

.ppo-overview__facts {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 4px 28px;
	padding: 16px 18px 18px;
}

.ppo-overview__facts > div {
	display: flex;
	min-width: 0;
	flex-direction: column;
	gap: 2px;
	padding: 9px 0;
	border-bottom: 1px solid var(--erp-border);
}

.ppo-overview__wide {
	grid-column: 1 / -1;
}

.ppo-overview span {
	order: 2;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: .03em;
	text-transform: uppercase;
}

.ppo-overview strong {
	order: 1;
	min-width: 0;
	overflow: hidden;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
	font-weight: var(--erp-font-weight-semibold);
	line-height: 1.35;
	overflow-wrap: anywhere;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.ppo-overview__wide strong {
	white-space: normal;
}

@media (max-width: 760px) {
	.ppo-overview__facts {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}

@media (max-width: 480px) {
	.ppo-overview__facts {
		grid-template-columns: 1fr;
	}
}
</style>
