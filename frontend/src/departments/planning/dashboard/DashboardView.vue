<template>
	<div class="pd-view">
		<section class="pd-panel pd-head" aria-labelledby="pd-dashboard-title">
			<div class="pd-head__row">
				<div>
					<h1 id="pd-dashboard-title">Dashboard</h1>
					<p>All {{ formatQuantity(ppoTotal) }} open PPOs and their lots. Filters narrow every section; click a figure, PPO or Lot to open it in PPO Tracking.</p>
				</div>
				<div class="pd-head__end">
					<span v-if="data" class="pd-sync"><i aria-hidden="true" />Live · {{ formatDisplayDate(data.as_of) }}</span>
					<Button icon="pi pi-refresh" label="Refresh" size="small" severity="secondary" outlined :loading="loading" @click="load" />
				</div>
			</div>
			<div class="pd-filters pd-filters--four" role="search" aria-label="Dashboard filters">
				<FilterMultiSelect v-for="filter in FILTERS" :key="filter.kind" v-model="filters[filter.kind]" :label="filter.label" :placeholder="filter.placeholder" :options="options[filter.kind]" />
				<Button label="Clear" text size="small" class="pd-filters__clear" :disabled="!hasDashboardFilter(filters)" @click="clear" />
			</div>
		</section>
		<div v-if="loading && !data" class="pd-loading"><Skeleton height="96px" /><Skeleton height="160px" /><Skeleton height="420px" /></div>
		<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
		<template v-else-if="data">
			<SummaryTiles :tiles="tiles" label="Dashboard summary" clickable @select="emit('drill', tileDrill($event, totals))" />
			<DashboardStatusCards :totals="totals" :active="filters.status" @toggle="toggleStatus" />
			<DashboardTable :rows="totals.rows" :ppos="data.ppos" :sewing-processes="data.sewing_processes" @drill="emit('drill', $event)" />
		</template>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, reactive, ref } from "vue"

import { getPlanningDashboard } from "../../../api/planning.js"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import DashboardStatusCards from "./DashboardStatusCards.vue"
import DashboardTable from "./DashboardTable.vue"
import FilterMultiSelect from "./FilterMultiSelect.vue"
import SummaryTiles from "./SummaryTiles.vue"
import { formatQuantity } from "./dashboardFormat.js"
import { dashboardOptions, dashboardTotals, emptyDashboardFilters, hasDashboardFilter, tileDrill } from "./dashboardRows.js"

/** Factory-wide view of every open PPO and its lots; tiles, PPO and Lot links drill into PPO Tracking. */
const emit = defineEmits(["drill"])
const FILTERS = [
	{ kind: "ppo", label: "PPO", placeholder: "All PPOs" },
	{ kind: "lot", label: "Lot", placeholder: "All lots" },
	{ kind: "item", label: "Item", placeholder: "All items" },
	{ kind: "status", label: "Status", placeholder: "All statuses" },
]
const data = ref(null)
const loading = ref(false)
const error = ref("")
const filters = reactive(emptyDashboardFilters())

const ppoTotal = computed(() => Object.keys(data.value?.ppos || {}).length)
const totals = computed(() => dashboardTotals(data.value || { lots: [], ppos: {} }, filters))
const options = computed(() => Object.fromEntries(FILTERS.map(({ kind }) => [kind, dashboardOptions(data.value?.lots || [], filters, kind, data.value?.ppos)])))
const tiles = computed(() => {
	const value = totals.value
	return [
		{ key: "ppos", label: "Open PPOs", value: formatQuantity(value.ppoCount), foot: `${formatQuantity(value.ppoWithWorkOrders)} with Work Orders` },
		{ key: "lots", label: "Open lots", value: formatQuantity(value.open.length), foot: `${formatQuantity(value.lots.length - value.open.length)} dispatched · ${formatQuantity(value.notStarted.length)} no WO yet` },
		{ key: "ppoQty", label: "PPO qty", value: formatQuantity(value.ppoPieces), foot: `pcs · ${formatQuantity(value.boxesOnly)} PPOs boxes only`, title: `${formatQuantity(value.ppoBoxes, true)} boxes. Pieces = boxes × pieces per box; ${value.boxesOnly} PPOs have no single pieces per box and count in boxes only.` },
		{ key: "cut", label: "Cut", value: formatQuantity(value.cut), foot: "pcs received from Cutting WOs" },
		{ key: "dispatched", label: "Dispatched", value: formatQuantity(value.dispatched), foot: "pcs, incl. dispatched lots" },
		{ key: "balance", label: "Balance", value: formatQuantity(value.balance), foot: "pcs · open lots, Cut − Dispatched" },
		{ key: "late", label: "Late lots", value: formatQuantity(value.late.length), foot: "open lots past delivery", alert: value.late.length > 0 },
	]
})

async function load() {
	loading.value = true
	error.value = ""
	try {
		data.value = await getPlanningDashboard()
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Planning Dashboard."
	} finally {
		loading.value = false
	}
}

function clear() {
	Object.assign(filters, emptyDashboardFilters())
}

function toggleStatus(status) {
	filters.status = filters.status.length === 1 && filters.status[0] === status ? [] : [status]
}

onMounted(load)
</script>
