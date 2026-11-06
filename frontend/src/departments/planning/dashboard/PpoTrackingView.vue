<template>
	<div class="pd-view">
		<section class="pd-panel pd-head" aria-labelledby="pd-tracking-title">
			<div class="pd-head__row">
				<div>
					<h1 id="pd-tracking-title">PPO Tracking</h1>
					<p>Lot-wise progress by process. PPO sizes are boxes; production is pieces.</p>
				</div>
				<div class="pd-head__end">
					<span v-if="data" class="pd-sync"><i aria-hidden="true" />Live · {{ formatDisplayDate(data.as_of) }}</span>
					<Button v-if="hasScope" icon="pi pi-refresh" label="Refresh" size="small" severity="secondary" outlined :loading="loading" @click="load" />
				</div>
			</div>
			<div class="pd-filters" role="search" aria-label="PPO Tracking filters">
				<FilterMultiSelect :model-value="filters.ppo" label="PPO" placeholder="Search PPO or item" help="Paste several, separated by , or ;" :options="options.ppo" @update:model-value="setFilter('ppo', $event)" />
				<FilterMultiSelect :model-value="filters.lot" label="Lot" placeholder="All lots in the PPOs" :options="options.lot" @update:model-value="setFilter('lot', $event)" />
				<FilterMultiSelect :model-value="filters.process" label="Process" placeholder="All processes" :options="options.process" @update:model-value="setFilter('process', $event)" />
				<Button label="Clear" text size="small" class="pd-filters__clear" :disabled="!hasScope && !filters.process.length" @click="emit('update', { filters: emptyTrackingFilters(), showDispatched: false })" />
			</div>
		</section>
		<WorkspaceLoadError v-if="optionsError" :message="optionsError" @retry="loadOptions" />
		<section v-if="!hasScope" class="pd-panel pd-start" data-start-empty>
			<strong>Select a PPO or Lot to begin</strong>
			<p>Search the PPO filter by PPO number or item (for example BOXER), paste a list of PPOs, or pick lots. A Process selection alone is not enough.</p>
		</section>
		<div v-else-if="loading && !data" class="pd-loading"><Skeleton height="96px" /><Skeleton height="420px" /></div>
		<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
		<template v-else-if="data">
			<SummaryTiles :tiles="tiles" label="Selection summary" />
			<TrackingLotsTable
				:key="scopeKey"
				:lots="visibleLots"
				:hidden-count="showDispatched ? 0 : hiddenDispatchedCount(matchingLots)"
				:ppos="data.ppos"
				:as-of="data.as_of"
				:show-dispatched="showDispatched"
				:reports="reports"
				@update:show-dispatched="emit('update', { filters, showDispatched: $event })"
			/>
		</template>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, ref, watch } from "vue"

import { getPpoTracking, getPpoTrackingOptions } from "../../../api/planning.js"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import FilterMultiSelect from "./FilterMultiSelect.vue"
import SummaryTiles from "./SummaryTiles.vue"
import TrackingLotsTable from "./TrackingLotsTable.vue"
import { formatQuantity } from "./dashboardFormat.js"
import {
	emptyTrackingFilters, hasTrackingScope, hiddenDispatchedCount, matchingTrackingLots,
	pruneTrackingFilters, trackingFilterOptions, trackingSummary, visibleTrackingLots,
} from "./trackingRows.js"

/** Lots of the selected PPOs or Lots, grouped by PPO, with process progress; filters live in the route. */
const props = defineProps({
	filters: { type: Object, required: true },
	showDispatched: Boolean,
	reports: { type: Array, default: () => [] },
})
const emit = defineEmits(["update"])
const filterOptions = ref({ ppos: [], lots: [] })
const optionsError = ref("")
const data = ref(null)
const loading = ref(false)
const error = ref("")
let sequence = 0

const hasScope = computed(() => hasTrackingScope(props.filters))
const scopeKey = computed(() => JSON.stringify([props.filters.ppo, props.filters.lot]))
const loadedLots = computed(() => (hasScope.value ? data.value?.lots || [] : []))
const options = computed(() => trackingFilterOptions(filterOptions.value, loadedLots.value, props.filters))
const matchingLots = computed(() => matchingTrackingLots(loadedLots.value, props.filters))
const visibleLots = computed(() => visibleTrackingLots(matchingLots.value, props.showDispatched))
const tiles = computed(() => {
	const summary = trackingSummary(data.value || {}, props.filters)
	const lotFoot = [`${summary.openLots} open`, summary.dispatchedLots ? `${summary.dispatchedLots} dispatched` : "", summary.notStartedLots ? `${summary.notStartedLots} not started` : ""].filter(Boolean).join(" · ")
	return [
		{ key: "ppos", label: "PPOs", value: formatQuantity(summary.ppoCount), foot: summary.isLotsOnly ? "of the selected lots" : "selected" },
		{ key: "lots", label: "Lots", value: formatQuantity(summary.lotCount), foot: lotFoot },
		{ key: "ppoQty", label: "PPO Quantity", value: formatQuantity(summary.ppoBoxes, true), unit: "boxes", foot: `${formatQuantity(summary.ppoPieces)} pieces` },
		{ key: "dispatched", label: "Dispatched", value: formatQuantity(summary.dispatched), foot: "pieces, incl. dispatched lots" },
		{ key: "wip", label: "Work in Progress", value: formatQuantity(summary.workInProgress), foot: "pieces · balance of open lots" },
		{ key: "notStarted", label: "Not Started", value: formatQuantity(summary.notStarted), foot: summary.isLotsOnly ? "not counted when picking lots" : "pieces · lots with no Work Order" },
	]
})

function setFilter(kind, values) {
	emit("update", { filters: { ...props.filters, [kind]: values }, showDispatched: props.showDispatched })
}

async function loadOptions() {
	optionsError.value = ""
	try {
		filterOptions.value = await getPpoTrackingOptions()
	} catch (reason) {
		optionsError.value = reason?.message || "Unable to load the PPO and Lot options."
	}
}

async function load() {
	const request = ++sequence
	if (!hasScope.value) {
		loading.value = false
		return
	}
	loading.value = true
	error.value = ""
	try {
		const result = await getPpoTracking(props.filters.ppo, props.filters.lot)
		if (request === sequence) data.value = result
	} catch (reason) {
		if (request === sequence) error.value = reason?.message || "Unable to load PPO Tracking."
	} finally {
		if (request === sequence) loading.value = false
	}
}

/** Drop Lot picks outside the PPOs and Process picks no loaded lot has. */
function prune() {
	if (loading.value || !filterOptions.value.lots.length || (hasScope.value && !data.value)) return
	const pruned = pruneTrackingFilters(props.filters, options.value)
	if (!hasScope.value) pruned.process = props.filters.process
	if (JSON.stringify(pruned) !== JSON.stringify(props.filters)) emit("update", { filters: pruned, showDispatched: props.showDispatched, replace: true })
}

watch(scopeKey, () => {
	data.value = null
	load()
})
watch([options, loading], prune)
onMounted(() => {
	loadOptions()
	load()
})
</script>
