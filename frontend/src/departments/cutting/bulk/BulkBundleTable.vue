<template>
	<section class="bulk-bundles data-panel">
		<header><div><span>Output</span><h3>Generated Bundles</h3></div><div class="bundle-metrics"><Tag :value="`${rows.length} bundles`" severity="secondary" rounded /><strong>{{ totalPieces }} pieces</strong></div></header>
		<div v-if="rows.length" class="bulk-bundles__scroll"><table><thead><tr><th>#</th><th>Bundle No</th><th>Size</th><th>Colour</th><th>Shade</th><th>Panel</th><th class="numeric">Quantity</th><th>Moved</th></tr></thead><tbody><tr v-for="(row, index) in rows" :key="row.name || `${row.bundle_no}-${index}`"><td>{{ index + 1 }}</td><td><strong>{{ row.bundle_no }}</strong></td><td>{{ value(row.size) }}</td><td>{{ value(row.colour) }}</td><td>{{ row.shade || "—" }}</td><td>{{ value(row.part) }}</td><td class="numeric"><strong>{{ row.quantity || 0 }}</strong></td><td><Tag :value="Number(row.is_moved) ? 'Moved' : 'Pending'" :severity="Number(row.is_moved) ? 'success' : 'secondary'" rounded /></td></tr></tbody></table></div>
		<div v-else class="data-empty"><i class="pi pi-box"></i><strong>No bundles generated</strong><span>Complete the active LaySheet details, then run Generate.</span></div>
	</section>
</template>

<script setup>
import Tag from "primevue/tag"
import { computed } from "vue"

const props = defineProps({ rows: { type: Array, default: () => [] } })
const totalPieces = computed(() => props.rows.reduce((total, row) => total + Number(row.quantity || 0), 0))
function value(input) { return (input?.value ?? input) || "—" }
</script>

<style scoped>
.data-panel { min-width: 0; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); overflow: hidden; }
.data-panel > header { display: flex; padding: 11px 13px; align-items: center; justify-content: space-between; gap: 12px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }.data-panel > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.data-panel > header h3 { margin: 2px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }.bundle-metrics { display: flex; align-items: center; gap: 9px; }.bundle-metrics strong { color: var(--erp-accent-dark); font-size: var(--erp-font-size-caption); }
.bulk-bundles__scroll { max-height: 310px; overflow: auto; }.bulk-bundles table { width: 100%; min-width: 760px; border-collapse: collapse; }.bulk-bundles th, .bulk-bundles td { padding: 8px 10px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }.bulk-bundles th { position: sticky; z-index: 1; top: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface-muted); }.bulk-bundles td { color: var(--erp-text); font-size: var(--erp-font-size-caption); }.bulk-bundles th:last-child, .bulk-bundles td:last-child { border-right: 0; }.bulk-bundles tbody tr:last-child td { border-bottom: 0; }.numeric { text-align: right !important; font-variant-numeric: tabular-nums; }
.data-empty { display: grid; min-height: 150px; place-content: center; justify-items: center; gap: 6px; color: var(--erp-text-muted); text-align: center; }.data-empty i { color: var(--erp-accent); font-size: 1.45rem; }.data-empty strong { color: var(--erp-text); }
</style>
