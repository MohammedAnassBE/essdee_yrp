<template>
	<div class="lot-tab-stack">
		<section class="lot-group">
			<header class="lot-group__header">
				<strong>Actual Dia Conversions</strong>
				<span>{{ view.changed }} changed · {{ view.routes }} routes</span>
				<label class="lot-conversion-toggle">
					<Checkbox v-model="includeUnchanged" binary input-id="lot-conversions-unchanged" />
					Include unchanged routes
				</label>
			</header>
			<div class="lot-conversion-controls">
				<InputText v-model="search" placeholder="Search conversions" aria-label="Search Actual Dia conversions" />
				<Select v-model="process" :options="processOptions" option-label="label" option-value="value" placeholder="All processes" aria-label="Conversion process" />
				<span>{{ view.rows.length }} shown</span>
			</div>
			<div v-if="view.rows.length" class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" aria-label="Actual Dia conversions">
				<table class="erp-data-table lot-table">
					<thead>
						<tr>
							<th>Process</th>
							<th>Planned Item → Actual Item</th>
							<th class="erp-number">Quantity</th>
							<th>Source</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, rowIndex) in view.rows" :key="rowIndex">
							<td><DocumentLink doctype="YRP Process" :name="row.process_name" /></td>
							<td><DocumentLink doctype="Item" :name="row.planned_item" /> → <DocumentLink doctype="Item" :name="row.actual_item" /></td>
							<td class="erp-number">{{ formatQuantity(row.actual_quantity) }} {{ row.stock_uom }}</td>
							<td>{{ countLabel(row.source_grn_count || 0, "GRN") }}<br /><DocumentLink v-if="row.production_detail" doctype="YRP Item Production Detail" :name="row.production_detail" /></td>
						</tr>
					</tbody>
				</table>
			</div>
			<LotEmptyState
				v-else
				:title="rows.length ? 'No matching routes' : 'No Actual Dia conversions'"
				:reason="rows.length ? 'Adjust the search, process or Include unchanged routes filter.' : 'Conversions appear after submitting Default Knitting GRNs.'"
			/>
		</section>
	</div>
</template>

<script setup>
import Checkbox from "primevue/checkbox"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import { computed, ref } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import LotEmptyState from "./LotEmptyState.vue"
import { conversionProcesses, conversionView, countLabel, formatQuantity, lotConversionRows } from "./lotViews.js"

/** Actual Dia conversions of every cloth route on the Lot, with search and process filters. */
const props = defineProps({
	fabrics: { type: Array, default: () => [] },
	otherConversions: { type: Array, default: () => [] },
})
const search = ref("")
const process = ref("")
const includeUnchanged = ref(false)
const rows = computed(() => lotConversionRows({ fabrics: props.fabrics, other_conversions: props.otherConversions }))
const processOptions = computed(() => [{ label: "All", value: "" }, ...conversionProcesses(rows.value).map((name) => ({ label: name, value: name }))])
const view = computed(() => conversionView(rows.value, { search: search.value, process: process.value, includeUnchanged: includeUnchanged.value }))
</script>

<style scoped>
.lot-conversion-controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 12px; }
</style>
