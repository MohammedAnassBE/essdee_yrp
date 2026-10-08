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
		<table v-else class="sewing-dashboard__table">
			<caption>{{ rows.length }} input types with recorded quantities</caption>
			<thead><tr><th scope="col">Input Type</th><th scope="col">Recorded Quantity</th></tr></thead>
			<tbody><tr v-for="row in rows" :key="row.input_type"><th scope="row">{{ row.input_type }}</th><td>{{ Number(row.qty).toLocaleString(undefined, { maximumFractionDigits: 3 }) }}</td></tr></tbody>
		</table>
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
.sewing-dashboard { min-width: 0; }
.sewing-dashboard__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
h2 { margin: 0; font-size: 16px; color: var(--erp-text); }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-dashboard__table { width: 100%; border-collapse: collapse; background: var(--erp-surface); font-size: var(--erp-font-size-caption); }
caption { text-align: left; padding-bottom: 10px; color: var(--erp-text-muted); }
th, td { padding: 12px; border-bottom: 1px solid var(--erp-border); text-align: left; overflow-wrap: anywhere; }
thead th { background: var(--erp-surface-soft); color: var(--erp-text-secondary); }
th:last-child, td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
@media (max-width: 700px) { .sewing-dashboard__header { align-items: flex-start; } }
</style>
