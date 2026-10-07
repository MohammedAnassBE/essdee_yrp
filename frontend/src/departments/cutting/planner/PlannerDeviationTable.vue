<template>
	<section class="planner-deviation">
		<header><div><span>Order accuracy</span><h3>Size Deviation</h3></div><Tag :value="`${sizes.length} sizes`" severity="secondary" rounded /></header>
		<div class="planner-deviation__scroll" role="region" tabindex="0" aria-label="Size deviation results"><table><thead><tr><th>Size</th><th class="numeric">Order</th><th class="numeric">Cut</th><th class="numeric">Difference</th><th class="numeric">Deviation</th><th>Result</th></tr></thead><tbody><tr v-for="size in sizes" :key="size"><td><strong>{{ size }}</strong></td><td class="numeric">{{ perSize[size].order }}</td><td class="numeric">{{ perSize[size].cut }}</td><td class="numeric" :class="diffClass(perSize[size].diff)">{{ signed(perSize[size].diff) }}</td><td class="numeric">{{ number(perSize[size].pct) }}%</td><td><Tag :value="status(perSize[size])" :severity="severity(perSize[size])" rounded /></td></tr></tbody></table></div>
	</section>
</template>

<script setup>
import Tag from "primevue/tag"
import { computed } from "vue"

const props = defineProps({ perSize: { type: Object, default: () => ({}) }, tolerance: { type: Number, default: 3 } })
const sizes = computed(() => Object.keys(props.perSize || {}))
function number(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 }) }
function signed(value) { const number = Number(value || 0); return number > 0 ? `+${number}` : String(number) }
function diffClass(value) { return Number(value) > 0 ? "is-over" : Number(value) < 0 ? "is-under" : "is-exact" }
function status(row) { if (Number(row.pct || 0) > props.tolerance) return "Outside tolerance"; if (Number(row.diff) > 0) return "Overcut"; if (Number(row.diff) < 0) return "Undercut"; return "Exact" }
function severity(row) { if (Number(row.pct || 0) > props.tolerance) return "danger"; if (Number(row.diff) !== 0) return "warn"; return "success" }
</script>

<style scoped>
.planner-deviation { border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); overflow: hidden; }.planner-deviation > header { display: flex; padding: 10px 12px; align-items: center; justify-content: space-between; gap: 10px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }.planner-deviation > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.planner-deviation h3 { margin: 2px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }.planner-deviation__scroll { overflow-x: auto; }.planner-deviation table { width: 100%; min-width: 680px; border-collapse: collapse; }.planner-deviation th, .planner-deviation td { padding: 8px 10px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }.planner-deviation th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface-muted); }.planner-deviation td { color: var(--erp-text); font-size: var(--erp-font-size-caption); }.planner-deviation th:last-child, .planner-deviation td:last-child { border-right: 0; }.planner-deviation tbody tr:last-child td { border-bottom: 0; }.numeric { text-align: right !important; font-variant-numeric: tabular-nums; }.is-over { color: var(--erp-warning) !important; font-weight: 760; }.is-under { color: var(--erp-danger) !important; font-weight: 760; }.is-exact { color: var(--erp-accent-dark) !important; font-weight: 760; }
</style>
