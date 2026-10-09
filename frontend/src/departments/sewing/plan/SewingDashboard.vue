<template>
	<section data-sewing-plan-tab="dashboard" class="sewing-dashboard" :aria-busy="loading" aria-label="Sewing dashboard">
		<header class="sewing-dashboard__header">
			<div><h2>Open Work Order inputs</h2><p>Recorded quantities by input type for {{ supplier }}.</p></div>
			<Button label="Refresh" aria-label="Refresh dashboard" icon="pi pi-refresh" severity="secondary" :disabled="loading" @click="load" />
		</header>
		<p v-if="loading && loaded" role="status">Refreshing dashboard…</p>
		<p v-if="stale" role="status">Dashboard could not be refreshed. Displayed results may be out of date. <Button label="Retry" text :disabled="loading" @click="load" /></p>
		<div v-if="loading && !loaded" role="status"><p>Loading dashboard</p><Skeleton height="120px" /></div>
		<p v-else-if="!rows.length && !stale" class="erp-empty-state">No input quantities for open Work Orders.</p>
		<div v-else class="sewing-dashboard__grid" :aria-label="`${rows.length} input types with recorded quantities`">
			<article v-for="row in rows" :key="row.input_type" class="sewing-dashboard__card erp-card" :data-sewing-dashboard-card="row.input_type">
				<span class="sewing-dashboard__icon"><i class="pi pi-box" aria-hidden="true" /></span>
				<div><strong>{{ Number(row.qty).toLocaleString(undefined, { maximumFractionDigits: 3 }) }}</strong><span>{{ row.input_type }}</span></div>
			</article>
		</div>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { onUnmounted, ref, watch } from "vue"
import { getSewingDashboard } from "../../../api/sewing.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { useSewingContext } from "../useSewingContext.js"
const { supplier, beginRequest, isCurrent } = useSewingContext()
const loading = ref(false), loaded = ref(false), stale = ref(false), error = ref(""), rows = ref([])
let mounted = true
async function load() {
	if (!supplier.value || loading.value) return
	const generation = beginRequest()
	loading.value = true; error.value = ""
	try {
		const data = await getSewingDashboard(supplier.value)
		if (mounted && isCurrent(generation)) { rows.value = Array.isArray(data) ? data : []; loaded.value = true; stale.value = false }
	} catch (reason) {
		if (mounted && isCurrent(generation)) { error.value = reason.message || "Unable to load dashboard."; stale.value = true }
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
watch(supplier, load, { immediate: true })
onUnmounted(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-dashboard { min-width: 0; padding-bottom: var(--erp-space-3); }
.sewing-dashboard__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
h2 { margin: 0; font-size: 16px; color: var(--erp-text); }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-dashboard__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: var(--erp-space-3); }
.sewing-dashboard__card { display: flex; align-items: center; gap: var(--erp-space-3); min-height: 96px; padding: var(--erp-space-4); box-shadow: var(--erp-shadow-xs); }
.sewing-dashboard__icon { display: grid; width: 40px; height: 40px; flex: 0 0 40px; color: var(--erp-accent-dark); background: var(--erp-accent-soft); border: 1px solid var(--erp-accent-border); border-radius: 12px; place-items: center; }
.sewing-dashboard__card div { display: grid; gap: 3px; min-width: 0; }
.sewing-dashboard__card strong { color: var(--erp-text); font-size: clamp(1.35rem, 2vw, 1.75rem); font-variant-numeric: tabular-nums; line-height: 1; letter-spacing: -0.025em; }
.sewing-dashboard__card span:last-child { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: var(--erp-font-weight-semibold); overflow-wrap: anywhere; }
@media (max-width: 700px) { .sewing-dashboard__header { align-items: flex-start; } .sewing-dashboard__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 430px) { .sewing-dashboard__grid { grid-template-columns: 1fr; } }
</style>
