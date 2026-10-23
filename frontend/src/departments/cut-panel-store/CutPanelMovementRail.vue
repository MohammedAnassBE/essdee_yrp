<template>
	<aside class="cut-panel-movement-rail" aria-label="Linked Cut Panel Movement documents">
		<header class="cut-panel-movement-rail__header">
			<div><span>LINKED</span><h3>Movement documents</h3></div>
			<Button icon="pi pi-refresh" severity="secondary" text rounded aria-label="Refresh linked documents" :loading="loading" :disabled="busy || loading" @click="emit('refresh')" />
		</header>

		<div v-if="availableActions.length" class="cut-panel-movement-rail__actions">
			<Button
				v-for="action in availableActions"
				:key="action.operation"
				:label="action.label"
				:icon="action.icon"
				size="small"
				:severity="action.operation === 'stock_entry' ? 'primary' : 'secondary'"
				:outlined="action.operation !== 'stock_entry'"
				:disabled="busy || (!action.eligible && !action.reason)"
				:aria-disabled="!action.eligible"
				:aria-label="action.eligible ? action.label : `${action.label}. Unavailable: ${action.reason}`"
				:aria-describedby="!action.eligible && action.reason ? 'cut-panel-action-disabled-reason' : undefined"
				:class="{ 'cut-panel-movement-rail__action--reason-disabled': !action.eligible && action.reason }"
				:title="action.eligible ? action.label : action.reason"
				@focus="showDisabledReason(action)"
				@click="runAction(action)"
			/>
			<small v-if="disabledReason" id="cut-panel-action-disabled-reason" class="cut-panel-movement-rail__reason" role="status">{{ disabledReason }}</small>
		</div>

		<div v-if="loading && !hasRows" class="cut-panel-movement-rail__loading">
			<Skeleton v-for="index in 5" :key="index" height="4.25rem" />
		</div>
		<div v-else class="cut-panel-movement-rail__sections">
			<section
				v-for="section in visibleSections"
				:key="section.key"
				class="cut-panel-movement-rail__section"
				:class="{ 'cut-panel-movement-rail__section--expanded': expandedSections[section.key] }"
			>
				<header><span>{{ section.label }}</span><strong>{{ section.rows.length }}</strong></header>
				<button
					v-for="(row, rowIndex) in section.rows"
					:key="`${row.doctype}-${row.name}`"
					type="button"
					class="cut-panel-movement-rail__row"
					:class="{ 'cut-panel-movement-rail__row--mobile-overflow': rowIndex >= mobilePreviewLimit }"
					:disabled="busy"
					@click="emit('open-document', row)"
				>
					<span><strong>{{ row.name }}</strong><DocumentStatusBadge :docstatus="row.docstatus" :label="row.status" /></span>
					<small>{{ dateTime(row) }}</small>
					<i class="pi pi-angle-right" aria-hidden="true" />
				</button>
				<div v-if="!section.rows.length" class="cut-panel-movement-rail__empty">No {{ section.label.toLowerCase() }} yet</div>
				<Button
					v-if="section.rows.length > mobilePreviewLimit"
					class="cut-panel-movement-rail__toggle"
					severity="secondary"
					text
					:icon="expandedSections[section.key] ? 'pi pi-chevron-up' : 'pi pi-chevron-down'"
					:label="expandedSections[section.key] ? 'Show fewer' : `Show all ${section.rows.length}`"
					:aria-expanded="expandedSections[section.key]"
					@click="expandedSections[section.key] = !expandedSections[section.key]"
				/>
			</section>
		</div>
	</aside>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref } from "vue"

import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { formatDisplayDate } from "../../utils/dateFormat.js"
import { normaliseFrappeTime } from "../../utils/documentValues.js"

const props = defineProps({ linked: { type: Object, default: () => ({}) }, loading: Boolean, busy: Boolean })
const emit = defineEmits(["refresh", "create", "open-document"])
const definitions = [
	{ key: "stock_entries", operation: "stock_entry", label: "Stock Entries", icon: "pi pi-box" },
	{ key: "delivery_challans", operation: "delivery_challan", label: "Delivery Challans", icon: "pi pi-truck" },
	{ key: "goods_received_notes", operation: "goods_received_note", label: "Goods Received Notes", icon: "pi pi-inbox" },
]
const visibleSections = computed(() => definitions
	.filter((definition) => Object.hasOwn(props.linked.sections || {}, definition.key))
	.map((definition) => ({ ...definition, rows: props.linked.sections?.[definition.key] || [] })))
const availableActions = computed(() => definitions
	.filter((definition) => props.linked.actions?.[definition.operation]?.can_create)
	.map((definition) => ({ ...definition, ...props.linked.actions[definition.operation], operation: definition.operation })))
const hasRows = computed(() => visibleSections.value.some((section) => section.rows.length))
const disabledReason = ref("")
const expandedSections = reactive({ stock_entries: false, delivery_challans: false, goods_received_notes: false })
const mobilePreviewLimit = 2

function showDisabledReason(action) { disabledReason.value = !action?.eligible && action?.reason ? action.reason : "" }
function runAction(action) {
	if (props.busy || !action?.eligible) { showDisabledReason(action); return }
	disabledReason.value = ""
	emit("create", action.operation)
}

function dateTime(row) {
	const time = normaliseFrappeTime(row.posting_time).slice(0, 5)
	return [formatDisplayDate(row.posting_date, ""), time].filter(Boolean).join(" ") || "No posting time"
}
</script>

<style scoped>
.cut-panel-movement-rail{display:flex;min-width:0;min-height:0;flex-direction:column;overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}
.cut-panel-movement-rail__header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:11px 12px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}
.cut-panel-movement-rail__header>div{display:grid;gap:2px}.cut-panel-movement-rail__header span{color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:800;letter-spacing:.08em}.cut-panel-movement-rail__header h3{margin:0;color:var(--erp-text);font-size:.9rem}
.cut-panel-movement-rail__actions{display:grid;gap:7px;padding:10px;border-bottom:1px solid var(--erp-border)}.cut-panel-movement-rail__actions :deep(.p-button){justify-content:flex-start;width:100%;font-size:12px}
.cut-panel-movement-rail__reason{grid-column:1/-1;padding:2px 3px;color:var(--erp-text-secondary);font-size:var(--erp-font-size-min);font-weight:650;line-height:1.35}
.cut-panel-movement-rail__loading,.cut-panel-movement-rail__sections{display:grid;min-height:0;gap:0;padding:0}.cut-panel-movement-rail__loading{gap:8px;padding:10px}.cut-panel-movement-rail__section{display:grid;align-content:start;overflow:hidden;border-bottom:1px solid var(--erp-border)}.cut-panel-movement-rail__section:last-child{border-bottom:0}.cut-panel-movement-rail__section>header{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:var(--erp-surface-soft);color:var(--erp-text-secondary);font-size:var(--erp-font-size-min);font-weight:750}.cut-panel-movement-rail__section>header strong{display:grid;min-width:20px;height:20px;place-items:center;border-radius:999px;background:var(--erp-surface);color:var(--erp-accent-hover)}
.cut-panel-movement-rail__row{position:relative;display:grid;min-height:52px;gap:4px;width:100%;padding:9px 30px 9px 10px;border:0;border-top:1px solid var(--erp-border);background:var(--erp-surface);color:var(--erp-text);text-align:left;cursor:pointer}.cut-panel-movement-rail__row:hover{background:var(--erp-accent-soft)}.cut-panel-movement-rail__row>span{display:flex;align-items:center;justify-content:space-between;gap:6px}.cut-panel-movement-rail__row strong{overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.cut-panel-movement-rail__row em{padding:2px 6px;border-radius:999px;background:var(--erp-surface-muted);color:var(--erp-text-muted);font-size:var(--erp-font-size-min);font-style:normal;font-weight:700;text-transform:uppercase}.cut-panel-movement-rail__row em.is-submitted{background:var(--erp-success-soft);color:var(--erp-success-text)}.cut-panel-movement-rail__row em.is-cancelled{background:var(--erp-danger-soft);color:var(--erp-danger)}.cut-panel-movement-rail__row small{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.cut-panel-movement-rail__row>i{position:absolute;right:10px;top:50%;color:var(--erp-text-muted);transform:translateY(-50%)}.cut-panel-movement-rail__empty{padding:13px 9px;border-top:1px solid var(--erp-border);color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-align:center}
.cut-panel-movement-rail__row:disabled{opacity:.58;cursor:wait}.cut-panel-movement-rail__row:disabled:hover{background:var(--erp-surface)}
.cut-panel-movement-rail__toggle{display:none}
@media(max-width:1050px){.cut-panel-movement-rail__sections{grid-template-columns:repeat(3,minmax(0,1fr))}.cut-panel-movement-rail__section{border-right:1px solid var(--erp-border);border-bottom:0}.cut-panel-movement-rail__section:last-child{border-right:0}.cut-panel-movement-rail__actions{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:720px){.cut-panel-movement-rail__sections,.cut-panel-movement-rail__actions{grid-template-columns:1fr}.cut-panel-movement-rail__section{border-right:0;border-bottom:1px solid var(--erp-border)}.cut-panel-movement-rail__section:last-child{border-bottom:0}.cut-panel-movement-rail__row--mobile-overflow{display:none}.cut-panel-movement-rail__section--expanded .cut-panel-movement-rail__row--mobile-overflow{display:grid}.cut-panel-movement-rail__toggle{display:flex;width:100%;min-height:44px;justify-content:center;border-top:1px solid var(--erp-border);border-radius:0}}
@media(max-width:1024px),(pointer:coarse){.cut-panel-movement-rail__header :deep(.p-button),.cut-panel-movement-rail__actions :deep(.p-button){min-width:44px;min-height:44px}}
</style>
