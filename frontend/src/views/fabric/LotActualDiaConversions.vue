<template>
	<section class="adc-shell">
		<header class="adc-head">
			<div>
				<div class="adc-title-row">
					<h4>Actual Dia Conversion</h4>
					<span class="adc-count">{{ view.changedCount }} changed</span>
					<span class="adc-count adc-count--muted">{{ view.rowCount }} receipts</span>
				</div>
				<p>Built automatically from submitted Default Knitting Process GRNs.</p>
			</div>
		</header>

		<div v-if="rows.length" class="adc-toolbar">
			<span class="p-input-icon-left adc-search-wrap">
				<i class="pi pi-search" />
				<input
					v-model.trim="search"
					type="search"
					class="adc-control adc-search"
					placeholder="Search process or item"
				/>
			</span>
			<select v-model="process" class="adc-control adc-process" aria-label="Process">
				<option value="">All Processes</option>
				<option v-for="value in view.processes" :key="value" :value="value">{{ value }}</option>
			</select>
			<label class="adc-toggle">
				<input v-model="includeUnchanged" type="checkbox" />
				<span>Include unchanged routes</span>
			</label>
		</div>

		<div v-if="!rows.length" class="esd-empty adc-empty">
			<i class="pi pi-inbox" />
			<p class="esd-empty__text">Submit a Default Knitting Process GRN to build the conversion table.</p>
		</div>
		<div v-else-if="!view.filteredRows.length" class="esd-empty adc-empty">
			<i class="pi pi-filter-slash" />
			<p class="esd-empty__text">No matching actual Dia conversions.</p>
			<button
				v-if="!includeUnchanged && !search && !process"
				type="button"
				class="adc-link-button"
				@click="includeUnchanged = true"
			>
				Show unchanged routes
			</button>
		</div>

		<article v-for="group in view.groups" :key="group.productionDetail" class="adc-card">
			<header class="adc-card-head">
				<strong>{{ group.productionDetail || "Unspecified cloth route" }}</strong>
				<span>{{ group.rows.length }} {{ group.rows.length === 1 ? "row" : "rows" }}</span>
			</header>
			<div class="adc-table-wrap">
				<table class="adc-table">
					<thead>
						<tr>
							<th class="adc-process-col">Process</th>
							<th>From Item</th>
							<th>To Item</th>
							<th class="adc-qty-col">To Qty</th>
							<th class="adc-source-col">Source</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in group.rows" :key="row.name || rowKey(row)">
							<td><span class="adc-process-badge">{{ row.process_name || "—" }}</span></td>
							<td class="adc-item">{{ row.from_item || "—" }}</td>
							<td class="adc-item adc-item--actual">{{ row.to_item || "—" }}</td>
							<td class="adc-qty">{{ formatQty(row.to_qty) }} <small>{{ row.stock_uom || "" }}</small></td>
							<td class="adc-source">{{ sourceLabel(row.source_grn_count) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</article>
	</section>
</template>

<script setup>
import { computed, ref } from "vue"
import { buildActualDiaConversionView } from "./fabricShapes"

const props = defineProps({
	rows: { type: Array, default: () => [] },
})

const search = ref("")
const process = ref("")
const includeUnchanged = ref(false)

const view = computed(() => buildActualDiaConversionView(props.rows, {
	search: search.value,
	process: process.value,
	includeUnchanged: includeUnchanged.value,
}))

function formatQty(value) {
	return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 })
}

function sourceLabel(value) {
	const count = Number(value || 0)
	return count === 1 ? "1 GRN" : `${count} GRNs`
}

function rowKey(row) {
	return [row.production_detail, row.process_name, row.from_item, row.to_item, row.to_qty].join("|")
}
</script>

<style scoped>
.adc-shell { padding: 4px 0 18px; }
.adc-head, .adc-title-row, .adc-toolbar, .adc-card-head { display: flex; align-items: center; }
.adc-head { justify-content: space-between; margin-bottom: 12px; }
.adc-title-row { flex-wrap: wrap; gap: 7px; }
.adc-title-row h4 { margin: 0 4px 0 0; }
.adc-head p { margin: 4px 0 0; color: var(--esd-muted); font-size: 0.78rem; }
.adc-count { padding: 2px 8px; border-radius: 999px; background: #dcfce7; color: #166534; font-size: 0.7rem; font-weight: 700; }
.adc-count--muted { background: var(--esd-bg-subtle); color: var(--esd-muted); }
.adc-toolbar { flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.adc-control { height: 36px; border: 1px solid var(--esd-border); border-radius: 7px; background: var(--esd-surface); color: var(--esd-text); font: inherit; font-size: 0.78rem; }
.adc-control:focus { border-color: var(--esd-accent); outline: 2px solid color-mix(in srgb, var(--esd-accent) 18%, transparent); }
.adc-search-wrap { flex: 1 1 280px; }
.adc-search-wrap > i { left: 11px; color: var(--esd-muted); }
.adc-search { width: 100%; padding: 0 10px 0 34px; }
.adc-process { min-width: 155px; padding: 0 10px; }
.adc-toggle { display: inline-flex; align-items: center; gap: 7px; min-height: 36px; padding: 0 10px; border: 1px solid var(--esd-border); border-radius: 7px; font-size: 0.78rem; cursor: pointer; }
.adc-toggle input { margin: 0; }
.adc-empty { gap: 7px; padding: 34px 20px; }
.adc-link-button { border: 0; background: transparent; color: var(--esd-accent); font: inherit; font-weight: 700; cursor: pointer; }
.adc-card { margin-top: 12px; border: 1px solid var(--esd-border); border-radius: 9px; background: var(--esd-surface); overflow: hidden; }
.adc-card-head { justify-content: space-between; gap: 12px; padding: 9px 12px; border-bottom: 1px solid var(--esd-border); background: var(--esd-bg-subtle); }
.adc-card-head span { color: var(--esd-muted); font-size: 0.72rem; }
.adc-table-wrap { max-height: 520px; overflow: auto; }
.adc-table { width: 100%; min-width: 760px; border-collapse: separate; border-spacing: 0; font-size: 0.78rem; }
.adc-table th, .adc-table td { padding: 9px 11px; border-right: 1px solid var(--esd-border); border-bottom: 1px solid var(--esd-border); vertical-align: middle; }
.adc-table th:last-child, .adc-table td:last-child { border-right: 0; }
.adc-table tbody tr:last-child td { border-bottom: 0; }
.adc-table th { position: sticky; top: 0; z-index: 1; background: var(--esd-bg-subtle); color: var(--esd-muted); font-weight: 700; text-align: left; }
.adc-process-col { width: 125px; }
.adc-qty-col { width: 125px; text-align: right !important; }
.adc-source-col { width: 90px; }
.adc-process-badge { display: inline-block; padding: 3px 8px; border-radius: 999px; background: #dbeafe; color: #1d4ed8; font-size: 0.7rem; font-weight: 700; }
.adc-item { overflow-wrap: anywhere; font-weight: 600; }
.adc-item--actual { color: #166534; }
.adc-qty { font-variant-numeric: tabular-nums; font-weight: 700; text-align: right; white-space: nowrap; }
.adc-qty small { color: var(--esd-muted); font-weight: 500; }
.adc-source { color: var(--esd-muted); white-space: nowrap; }
@media (max-width: 700px) {
	.adc-toolbar { align-items: stretch; flex-direction: column; }
	.adc-search-wrap { flex-basis: auto; }
	.adc-process { width: 100%; }
}
</style>
