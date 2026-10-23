<template>
	<div class="work-order-details">
		<section v-if="!matricesOnly && visibleDetails.length" class="work-order-fields erp-card" aria-label="Work Order details">
			<div v-for="field in visibleDetails" :key="field.fieldname" class="work-order-field" :class="{ 'work-order-field--wide': isWide(field) }" :data-field="field.fieldname">
				<span>{{ field.label }}</span>
				<strong :title="String(formatValue(field))">{{ formatValue(field) }}</strong>
			</div>
		</section>

		<section v-if="!fieldsOnly && deliverables.length" class="work-order-section erp-card">
			<header><div><span>Inputs</span><h2>Deliverables</h2></div><span class="erp-count">{{ itemCount(deliverables) }} rows</span></header>
			<WorkOrderItemMatrix :groups="deliverables" :process-cost-view-route-name="processCostViewRouteName" />
		</section>
		<section v-if="!fieldsOnly && receivables.length" class="work-order-section erp-card">
			<header><div><span>Outputs</span><h2>Receivables</h2></div><span class="erp-count">{{ itemCount(receivables) }} rows</span></header>
			<WorkOrderItemMatrix :groups="receivables" :process-cost-view-route-name="processCostViewRouteName" />
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { formatDisplayByFieldtype } from "../../utils/dateFormat.js"
import { plainTextFromHtml } from "../../utils/documentValues.js"
import WorkOrderItemMatrix from "./WorkOrderItemMatrix.vue"

const props = defineProps({
	details: { type: Array, default: () => [] },
	deliverables: { type: Array, default: () => [] },
	receivables: { type: Array, default: () => [] },
	fieldsOnly: { type: Boolean, default: false },
	matricesOnly: { type: Boolean, default: false },
	processCostViewRouteName: { type: String, default: "" },
})

const visibleDetails = computed(() => props.details.filter((field) => !["supplier_name", "process_name", "item", "lot"].includes(field.fieldname)))
const multilineFieldtypes = new Set(["Small Text", "Text", "Long Text", "Text Editor", "Code"])

function itemCount(groups) { return (groups || []).reduce((count, group) => count + (group.items?.length || 0), 0) }
function isWide(field) { return multilineFieldtypes.has(field.fieldtype) && /address|comments?|notes?|remarks?|terms?/i.test(field.fieldname) }
function formatValue(field) {
	if (["Date", "Datetime"].includes(field.fieldtype)) return formatDisplayByFieldtype(field.value, field.fieldtype, { seconds: true })
	if (field.fieldtype === "Check") return Number(field.value) ? "Yes" : "No"
	if (["Currency", "Float", "Int", "Percent"].includes(field.fieldtype)) return Number(field.value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
	return field.value === null || field.value === undefined || field.value === "" ? "—" : plainTextFromHtml(field.value)
}
</script>

<style scoped>
.work-order-details { display: grid; gap: var(--erp-space-3); }
.work-order-fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; border-color: color-mix(in srgb, var(--erp-border) 84%, var(--erp-surface)); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.work-order-field { display: grid; min-width: 0; min-height: 52px; align-content: center; gap: 3px; padding: 9px 12px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.work-order-field:nth-child(4n) { border-right: 0; }
.work-order-field--wide { grid-column: span 2; }
.work-order-field span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.work-order-field strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.work-order-field--wide strong { min-width: 0; overflow: visible; line-height: 1.35; overflow-wrap: anywhere; text-overflow: clip; white-space: pre-line; }
.work-order-section { overflow: hidden; border-color: color-mix(in srgb, var(--erp-border) 84%, var(--erp-surface)); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.work-order-section > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); border-left: 3px solid color-mix(in srgb, var(--erp-accent) 68%, var(--erp-surface)); background: color-mix(in srgb, var(--erp-surface-soft) 78%, var(--erp-surface)); }
.work-order-section > header div { display: grid; gap: 2px; }
.work-order-section > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; text-transform: uppercase; }
.work-order-section > header h2 { margin: 0; font-size: 14px; }
.work-order-section > :deep(.work-order-matrix-stack) { padding: var(--erp-space-3); }
.erp-count { padding: 3px 8px; color: var(--erp-accent) !important; background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); white-space: nowrap; }
@media (max-width: 900px) { .work-order-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } .work-order-field:nth-child(4n) { border-right: 1px solid var(--erp-border); } .work-order-field:nth-child(2n) { border-right: 0; } }
@media (max-width: 620px) { .work-order-field { min-height: 48px; padding: 8px 10px; } }
</style>
