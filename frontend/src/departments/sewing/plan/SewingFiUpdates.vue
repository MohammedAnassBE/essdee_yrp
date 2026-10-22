<template>
	<section data-sewing-plan-tab="fi-updates" class="sewing-fi-updates" :aria-busy="loading || saving" aria-label="FI date updates">
		<div class="sewing-fi-updates__toolbar">
			<p>Set the FI date for each pending Lot and Colour. Updated rows leave this list and show in the DPR.</p>
			<Button label="Refresh" aria-label="Refresh FI updates" icon="pi pi-refresh" severity="secondary" :disabled="loading || saving" @click="load" />
		</div>
		<div v-if="loading && !loaded" role="status"><p>Loading pending FI dates</p><Skeleton height="140px" /></div>
		<WorkspaceLoadError v-else-if="loadError && !loaded" message="Retry to load pending FI dates." @retry="load" />
		<template v-else>
			<Message v-if="success" severity="success" :closable="false" role="status">{{ success }}</Message>
			<p v-if="!groups.length" class="erp-empty-state">No pending FI dates to update.</p>
			<article v-for="group in groups" :key="group.lot" class="sewing-fi-updates__lot erp-card" :data-fi-lot="group.lot">
				<header><strong>{{ group.lot }}</strong><span>{{ group.item }}</span><small>{{ group.rows.length }} pending</small></header>
				<table class="sewing-fi-updates__table">
					<thead><tr><th>#</th><th>Colour</th><th v-if="group.isSetItem">{{ group.setAttribute }}</th><th>FI Date</th></tr></thead>
					<tbody>
						<tr v-for="(row, index) in group.rows" :key="fiUpdateKey(row)" :data-fi-row="`${row.colour}|${row.part || ''}`">
							<td>{{ index + 1 }}</td>
							<td>{{ row.colour }}</td>
							<td v-if="group.isSetItem">{{ row.part }}</td>
							<td><DateField v-model="dates[fiUpdateKey(row)]" :aria-label="`FI Date for ${row.colour}${row.part ? ` ${row.part}` : ''}`" show-clear :disabled="saving" /></td>
						</tr>
					</tbody>
				</table>
			</article>
			<div v-if="groups.length" class="sewing-fi-updates__actions">
				<Button label="Update FI dates" icon="pi pi-check" :loading="saving" :disabled="loading || saving || !payload.length" @click="save" />
				<small>{{ payload.length }} of {{ rows.length }} rows dated</small>
			</div>
		</template>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onUnmounted, reactive, ref, watch } from "vue"
import { getSewingFiUpdates, updateSewingFiDates } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { useSewingContext } from "../useSewingContext.js"
import { fiUpdateKey, fiUpdatePayload, groupFiUpdatesByLot } from "./fiUpdates.js"

const { supplier, beginRequest, isCurrent } = useSewingContext()
const rows = ref([]), dates = reactive({})
const loading = ref(false), loaded = ref(false), saving = ref(false)
const loadError = ref(""), error = ref(""), success = ref("")
const groups = computed(() => groupFiUpdatesByLot(rows.value))
const payload = computed(() => fiUpdatePayload(rows.value, dates))
let mounted = true

async function load() {
	if (!supplier.value) return
	const generation = beginRequest()
	loading.value = true; loadError.value = ""
	try {
		const data = await getSewingFiUpdates(supplier.value)
		if (!isCurrent(generation)) return
		rows.value = data?.data || []
		Object.keys(dates).forEach(key => delete dates[key])
		loaded.value = true
	} catch (reason) {
		if (isCurrent(generation)) { loadError.value = reason?.message || "Unable to load pending FI dates."; error.value = loadError.value }
	} finally { if (isCurrent(generation)) loading.value = false }
}

async function save() {
	if (!payload.value.length || saving.value) return
	const count = payload.value.length
	saving.value = true; error.value = ""; success.value = ""
	try {
		await updateSewingFiDates(payload.value)
		if (!mounted) return
		await load()
		success.value = `FI date updated for ${count} ${count === 1 ? "row" : "rows"}.`
	} catch (reason) {
		if (mounted) error.value = reason?.message || "Unable to update FI dates."
	} finally { if (mounted) saving.value = false }
}

watch(supplier, () => { rows.value = []; loaded.value = false; success.value = ""; load() }, { immediate: true })
onUnmounted(() => { mounted = false })
</script>

<style scoped>
.sewing-fi-updates { display: grid; gap: var(--erp-space-3); min-width: 0; max-width: 100%; }
p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.sewing-fi-updates__toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.sewing-fi-updates__lot { min-width: 0; padding: var(--erp-space-3); overflow-x: auto; }
.sewing-fi-updates__lot header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; margin-bottom: var(--erp-space-2); }
.sewing-fi-updates__lot header span, .sewing-fi-updates__lot small, .sewing-fi-updates__actions small { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.sewing-fi-updates__table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 0.86rem; }
.sewing-fi-updates__table th:first-child { width: 48px; }
.sewing-fi-updates__table th { color: var(--erp-text-muted); font-weight: 650; text-align: left; }
.sewing-fi-updates__table th, .sewing-fi-updates__table td { padding: 6px 8px; border-bottom: 1px solid var(--erp-border); vertical-align: middle; }
.sewing-fi-updates__table th:last-child { width: 220px; }
.sewing-fi-updates__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding-bottom: var(--erp-space-3); }
@media (max-width: 600px) { .sewing-fi-updates__toolbar { align-items: stretch; flex-direction: column; } .sewing-fi-updates__table th:last-child { width: 160px; } }
</style>
