<template>
	<section v-if="result" class="planner-lay-plan">
		<header class="planner-lay-plan__header"><div><span>Selected strategy</span><h2>{{ label(result.strategy) }}</h2><p>{{ result.strategy_description }}</p></div><Tag :value="`${result.summary.total_lays} lays`" severity="success" rounded /></header>
		<div class="planner-summary-grid"><article v-for="metric in metrics" :key="metric.label"><span>{{ metric.label }}</span><strong :class="metric.class">{{ metric.value }}</strong></article></div>
		<section class="planner-lay-table">
			<header><div><span>Cut structure</span><h3>Detailed Lay Plan</h3></div></header>
			<div class="planner-lay-table-wrap" tabindex="0" role="region" aria-label="Detailed lay plan quantities"><table><thead><tr><th>Lay</th><th class="numeric">Plies</th><th class="numeric">Pieces</th><th v-for="size in sizes" :key="size" class="numeric">{{ size }}</th><th>Ratio / Ply</th></tr></thead><tbody><tr v-for="lay in result.lays" :key="lay.lay_no"><td><strong>{{ lay.lay_no }}</strong></td><td class="numeric">{{ lay.plies }}</td><td class="numeric"><strong>{{ lay.total_pieces }}</strong></td><td v-for="size in sizes" :key="size" class="numeric" :class="{ 'is-zero': !lay.cut_per_size[size] }">{{ lay.cut_per_size[size] }}</td><td><span class="ratio-chip">{{ ratio(lay.ratio) }}</span><small>{{ lay.pieces_per_ply }} pcs/ply</small></td></tr></tbody><tfoot><tr class="total-cut"><td colspan="2">TOTAL CUT</td><td class="numeric">{{ result.summary.total_cut }}</td><td v-for="size in sizes" :key="size" class="numeric">{{ result.per_size[size].cut }}</td><td></td></tr><tr><td colspan="2">ORDER QTY</td><td class="numeric">{{ result.summary.total_order }}</td><td v-for="size in sizes" :key="size" class="numeric">{{ result.per_size[size].order }}</td><td></td></tr><tr><td colspan="2">DIFFERENCE</td><td class="numeric">{{ signed(result.summary.total_cut - result.summary.total_order) }}</td><td v-for="size in sizes" :key="size" class="numeric">{{ signed(result.per_size[size].diff) }}</td><td></td></tr></tfoot></table></div>
		</section>
		<PlannerDeviationTable :per-size="result.per_size" :tolerance="tolerance" />
	</section>
	<section v-else class="planner-plan-empty"><i class="pi pi-list-check"></i><strong>No selected lay plan</strong><span>Complete optimization and select a successful strategy.</span></section>
</template>

<script setup>
import Tag from "primevue/tag"
import { computed } from "vue"

import PlannerDeviationTable from "./PlannerDeviationTable.vue"

const props = defineProps({ result: { type: Object, default: null }, tolerance: { type: Number, default: 3 } })
const sizes = computed(() => Object.keys(props.result?.per_size || {}))
const metrics = computed(() => {
	const summary = props.result?.summary || {}
	return [
		{ label: "Total Lays", value: summary.total_lays || 0 }, { label: "Unique Markers", value: summary.unique_markers || 0 },
		{ label: "Avg Pieces / Ply", value: number(summary.avg_pieces_per_ply) }, { label: "Total Order", value: Number(summary.total_order || 0).toLocaleString() },
		{ label: "Total Cut", value: Number(summary.total_cut || 0).toLocaleString() }, { label: "Overcut", value: `${summary.overcut || 0} · ${number(summary.overcut_pct)}%`, class: Number(summary.overcut) ? "metric-warn" : "" },
		{ label: "Undercut", value: `${summary.undercut || 0} · ${number(summary.undercut_pct)}%`, class: Number(summary.undercut) ? "metric-danger" : "" },
	]
})
function label(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase()) }
function number(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 }) }
function ratio(values) { return sizes.value.map((size) => values?.[size] ?? 0).join(":") }
function signed(value) { const number = Number(value || 0); return number > 0 ? `+${number}` : String(number) }
</script>

<style scoped>
.planner-lay-plan { display: grid; padding: var(--erp-space-4); gap: var(--erp-space-3); }.planner-lay-plan__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.planner-lay-plan__header span, .planner-lay-table > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.planner-lay-plan__header h2 { margin: 3px 0; color: var(--erp-text); font-size: var(--erp-font-size-title); }.planner-lay-plan__header p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.planner-summary-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); overflow: hidden; }.planner-summary-grid article { display: grid; padding: 10px; gap: 3px; text-align: center; background: var(--erp-surface-soft); border-right: 1px solid var(--erp-border); }.planner-summary-grid article:last-child { border-right: 0; }.planner-summary-grid span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; text-transform: uppercase; }.planner-summary-grid strong { color: var(--erp-text); font-size: var(--erp-font-size-section); font-variant-numeric: tabular-nums; }.planner-summary-grid .metric-warn { color: var(--erp-warning); }.planner-summary-grid .metric-danger { color: var(--erp-danger); }
.planner-lay-table { border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); overflow: hidden; }.planner-lay-table > header { padding: 10px 12px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }.planner-lay-table h3 { margin: 2px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }.planner-lay-table-wrap { overflow-x: auto; }.planner-lay-table-wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }.planner-lay-table table { width: 100%; min-width: 820px; border-collapse: collapse; }.planner-lay-table th, .planner-lay-table td { padding: 8px 10px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }.planner-lay-table th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface-muted); }.planner-lay-table td { color: var(--erp-text); font-size: var(--erp-font-size-caption); }.planner-lay-table th:last-child, .planner-lay-table td:last-child { border-right: 0; }.planner-lay-table tbody tr:hover td { background: var(--erp-surface-soft); }.planner-lay-table tfoot td { color: var(--erp-text); font-weight: 680; background: var(--erp-surface-muted); }.planner-lay-table tfoot .total-cut td { color: var(--erp-accent-dark); background: var(--erp-accent-soft); }.numeric { text-align: right !important; font-variant-numeric: tabular-nums; }.is-zero { color: var(--erp-text-subtle) !important; }.ratio-chip { display: inline-flex; padding: 3px 7px; color: var(--erp-accent-dark); font-weight: 720; font-variant-numeric: tabular-nums; background: var(--erp-accent-soft); border-radius: 999px; }.planner-lay-table td small { margin-left: 6px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.planner-plan-empty { display: grid; min-height: 220px; place-content: center; justify-items: center; gap: 7px; color: var(--erp-text-muted); text-align: center; }.planner-plan-empty i { color: var(--erp-accent); font-size: 1.8rem; }.planner-plan-empty strong { color: var(--erp-text); }
@media (max-width: 1150px) { .planner-summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }.planner-summary-grid article { border-bottom: 1px solid var(--erp-border); } }
@media (max-width: 650px) { .planner-lay-plan { padding: var(--erp-space-3); }.planner-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
