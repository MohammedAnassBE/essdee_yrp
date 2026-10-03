<template>
	<div class="adc-shell">
		<header class="adc-head">
			<div>
				<div class="adc-title-row">
					<h5>{{ __("Actual Dia Conversions") }}</h5>
					<span class="adc-count">{{ changedCount }} {{ __("changed") }}</span>
					<span class="adc-count adc-count--muted">{{ rows.length }} {{ __("receipts") }}</span>
				</div>
				<p>{{ __("Built automatically from submitted Default Knitting Process GRNs.") }}</p>
			</div>
		</header>

		<div v-if="rows.length" class="adc-toolbar">
			<div class="adc-search-wrap">
				<span class="adc-search-icon">⌕</span>
				<input
					v-model.trim="search"
					type="search"
					class="adc-control adc-search"
					:placeholder="__('Search process or item')"
				/>
			</div>
			<select v-model="process" class="adc-control adc-process">
				<option value="">{{ __("All Processes") }}</option>
				<option v-for="value in processes" :key="value" :value="value">{{ value }}</option>
			</select>
			<label class="adc-toggle">
				<input v-model="includeUnchanged" type="checkbox" />
				<span>{{ __("Include unchanged routes") }}</span>
			</label>
		</div>

		<div v-if="!rows.length" class="adc-empty">
			<strong>{{ __("No knitting receipts yet") }}</strong>
			<span>{{ __("Submit a GRN for the Default Knitting Process to build this table.") }}</span>
		</div>
		<div v-else-if="!filteredRows.length" class="adc-empty">
			<strong v-if="!includeUnchanged && !search && !process">{{ __("No actual Dia changes") }}</strong>
			<strong v-else>{{ __("No matching conversions") }}</strong>
			<span v-if="!includeUnchanged && !search && !process">
				{{ __("All {0} receipts keep their planned Dia.", [rows.length]) }}
			</span>
			<span v-else>{{ __("Change the search or filter to see more rows.") }}</span>
			<button
				v-if="!includeUnchanged && !search && !process"
				type="button"
				class="adc-link-button"
				@click="includeUnchanged = true"
			>
				{{ __("Show unchanged routes") }}
			</button>
		</div>

		<section v-for="group in groups" :key="group.productionDetail" class="adc-card">
			<header class="adc-card-head">
				<button type="button" class="adc-ipd" @click="openDoc('Item Production Detail', group.productionDetail)">
					{{ group.productionDetail || __("Unspecified cloth route") }}
				</button>
				<span>{{ group.rows.length }} {{ group.rows.length === 1 ? __("row") : __("rows") }}</span>
			</header>
			<div class="adc-table-wrap">
				<table class="adc-table">
					<thead>
						<tr>
							<th class="adc-process-col">{{ __("Process") }}</th>
							<th>{{ __("Planned Item") }}</th>
							<th class="adc-arrow-col" aria-label="To"></th>
							<th>{{ __("Actual Item") }}</th>
							<th class="adc-qty-col">{{ __("Quantity") }}</th>
							<th class="adc-source-col">{{ __("Source") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in group.rows" :key="row.name || rowKey(row)" :class="{ 'adc-row--unchanged': !isChanged(row) }">
							<td><span class="adc-process-badge">{{ row.process_name || "—" }}</span></td>
							<td>
								<button type="button" class="adc-item" @click="openDoc('Item Variant', row.from_item)">{{ row.from_item || "—" }}</button>
							</td>
							<td class="adc-arrow">→</td>
							<td>
								<button type="button" class="adc-item adc-item--actual" @click="openDoc('Item Variant', row.to_item)">{{ row.to_item || "—" }}</button>
							</td>
							<td class="adc-qty">{{ formatQty(row.to_qty) }} <small>{{ row.stock_uom || "" }}</small></td>
							<td class="adc-source">{{ sourceLabel(row.source_grn_count) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import { computed, ref } from "vue";

const rows = ref([]);
const search = ref("");
const process = ref("");
const includeUnchanged = ref(false);

function load_data(data) {
	rows.value = (data || [])
		.filter((row) => flt(row.to_qty) > 0 && (!row.received_type || row.received_type === "Accepted"))
		.map((row) => ({ ...row }));
	search.value = "";
	process.value = "";
	includeUnchanged.value = false;
}

function isChanged(row) {
	return Boolean(row.from_item && row.to_item && row.from_item !== row.to_item);
}

const changedCount = computed(() => rows.value.filter(isChanged).length);
const processes = computed(() =>
	[...new Set(rows.value.map((row) => row.process_name).filter(Boolean))]
		.sort((a, b) => String(a).localeCompare(String(b))),
);
const filteredRows = computed(() => {
	const term = search.value.toLowerCase();
	return rows.value.filter((row) => {
		if (!includeUnchanged.value && !isChanged(row)) return false;
		if (process.value && row.process_name !== process.value) return false;
		if (!term) return true;
		return [row.process_name, row.from_item, row.to_item, row.production_detail]
			.some((value) => String(value || "").toLowerCase().includes(term));
	});
});
const groups = computed(() => {
	const result = [];
	const byIpd = new Map();
	for (const row of filteredRows.value) {
		const key = row.production_detail || "";
		if (!byIpd.has(key)) {
			const group = { productionDetail: key, rows: [] };
			byIpd.set(key, group);
			result.push(group);
		}
		byIpd.get(key).rows.push(row);
	}
	return result;
});

function formatQty(value) {
	const number = Number(value || 0);
	return number.toLocaleString(undefined, { maximumFractionDigits: 3 });
}
function sourceLabel(value) {
	const count = Number(value || 0);
	return count === 1 ? __("1 GRN") : __("{0} GRNs", [count]);
}
function rowKey(row) {
	return [row.production_detail, row.process_name, row.from_item, row.to_item, row.to_qty].join("|");
}
function openDoc(doctype, name) {
	if (name) frappe.set_route("Form", doctype, name);
}

defineExpose({ load_data });
</script>

<style scoped>
.adc-shell { padding: 4px 0 18px; }
.adc-head, .adc-title-row, .adc-toolbar, .adc-card-head { display: flex; align-items: center; }
.adc-head { justify-content: space-between; margin-bottom: 12px; }
.adc-title-row { flex-wrap: wrap; gap: 7px; }
.adc-title-row h5 { margin: 0 4px 0 0; font-size: 15px; }
.adc-head p { margin: 4px 0 0; color: var(--text-muted); font-size: 12px; }
.adc-count { padding: 2px 7px; border-radius: 999px; background: var(--green-100, #d1fadf); color: var(--green-700, #027a48); font-size: 11px; font-weight: 600; }
.adc-count--muted { background: var(--subtle-fg); color: var(--text-muted); }
.adc-toolbar { flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.adc-control { height: 34px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--control-bg, var(--fg-color)); color: var(--text-color); font-size: 12px; outline: none; }
.adc-control:focus { border-color: var(--primary); box-shadow: 0 0 0 2px var(--gray-100); }
.adc-search-wrap { position: relative; flex: 1 1 260px; }
.adc-search-icon { position: absolute; top: 7px; left: 10px; color: var(--text-muted); font-size: 16px; pointer-events: none; }
.adc-search { width: 100%; padding: 0 10px 0 31px; }
.adc-process { min-width: 150px; padding: 0 28px 0 10px; }
.adc-toggle { display: inline-flex; align-items: center; gap: 7px; min-height: 34px; margin: 0; padding: 0 10px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 12px; cursor: pointer; }
.adc-toggle input { margin: 0; }
.adc-empty { display: flex; align-items: center; flex-direction: column; gap: 5px; padding: 34px 20px; border: 1px dashed var(--border-color); border-radius: 8px; background: var(--subtle-fg); color: var(--text-muted); text-align: center; }
.adc-empty strong { color: var(--text-color); }
.adc-link-button, .adc-ipd, .adc-item { border: 0; background: transparent; color: var(--primary); font: inherit; text-align: left; cursor: pointer; }
.adc-link-button { margin-top: 4px; font-weight: 600; }
.adc-card { margin-top: 12px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg, var(--fg-color)); overflow: hidden; }
.adc-card-head { justify-content: space-between; gap: 12px; padding: 8px 11px; border-bottom: 1px solid var(--border-color); background: var(--subtle-fg); }
.adc-card-head span { color: var(--text-muted); font-size: 11px; }
.adc-ipd { padding: 0; font-weight: 600; }
.adc-table-wrap { max-height: 520px; overflow: auto; }
.adc-table { width: 100%; min-width: 880px; border-collapse: separate; border-spacing: 0; font-size: 12px; }
.adc-table th, .adc-table td { padding: 8px 10px; border-right: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.adc-table th:last-child, .adc-table td:last-child { border-right: 0; }
.adc-table tbody tr:last-child td { border-bottom: 0; }
.adc-table th { position: sticky; top: 0; z-index: 1; background: var(--subtle-fg); color: var(--text-muted); font-weight: 500; text-align: left; }
.adc-process-col { width: 105px; }
.adc-arrow-col { width: 34px; }
.adc-qty-col { width: 110px; text-align: right !important; }
.adc-source-col { width: 78px; }
.adc-process-badge { display: inline-block; padding: 2px 7px; border-radius: 999px; background: var(--blue-100, #d1e9ff); color: var(--blue-700, #175cd3); font-size: 11px; font-weight: 600; }
.adc-item { display: block; width: 100%; padding: 0; color: var(--text-color); font-weight: 500; overflow-wrap: anywhere; }
.adc-item:hover, .adc-ipd:hover { color: var(--primary); text-decoration: underline; }
.adc-item--actual { color: var(--green-700, #027a48); }
.adc-arrow { color: var(--text-muted); text-align: center; }
.adc-qty { font-variant-numeric: tabular-nums; font-weight: 600; text-align: right; white-space: nowrap; }
.adc-qty small, .adc-source { color: var(--text-muted); font-weight: 400; }
.adc-row--unchanged { opacity: 0.65; }
@media (max-width: 700px) {
	.adc-toolbar { align-items: stretch; flex-direction: column; }
	.adc-search-wrap { flex-basis: auto; }
	.adc-process { width: 100%; }
}
</style>
