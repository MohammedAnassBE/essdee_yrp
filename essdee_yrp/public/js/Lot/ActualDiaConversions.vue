<template>
	<div class="actual-dia-conversions">
		<div class="conversion-heading">
			<div>
				<h5>{{ __("Actual Dia Conversions") }}</h5>
				<p>{{ __("Built automatically from submitted versioned Knitting GRNs.") }}</p>
			</div>
			<div class="conversion-counts">
				<span class="changed-count">{{ changedCount }} {{ __("changed") }}</span>
				<span>{{ rows.length }} {{ __("routes") }}</span>
			</div>
		</div>

		<div v-if="rows.length" class="conversion-toolbar">
			<input v-model.trim="search" type="search" class="form-control"
				:placeholder="__('Search process or Item')" />
			<select v-model="process" class="form-control">
				<option value="">{{ __("All Processes") }}</option>
				<option v-for="value in processes" :key="value" :value="value">{{ value }}</option>
			</select>
			<label>
				<input v-model="includeUnchanged" type="checkbox" />
				{{ __("Include unchanged routes") }}
			</label>
		</div>

		<div v-if="!rows.length" class="conversion-empty">
			<strong>{{ __("No knitting receipts yet") }}</strong>
			<span>{{ __("Submit a versioned Knitting GRN to build this table.") }}</span>
		</div>
		<div v-else-if="!filteredRows.length" class="conversion-empty">
			<strong>{{ !includeUnchanged && !search && !process
				? __("No actual Dia changes") : __("No matching conversions") }}</strong>
			<button v-if="!includeUnchanged && !search && !process" type="button"
				class="btn btn-xs btn-default" @click="includeUnchanged = true">
				{{ __("Show unchanged routes") }}
			</button>
		</div>

		<section v-for="group in groups" :key="group.productionDetail" class="conversion-card">
			<header>
				<button type="button" @click="openDoc('YRP Item Production Detail', group.productionDetail)">
					{{ group.productionDetail || __("Unspecified cloth route") }}
				</button>
				<span>{{ group.rows.length }} {{ group.rows.length === 1 ? __("row") : __("rows") }}</span>
			</header>
			<div class="table-wrap">
				<table class="table table-bordered table-sm">
					<thead>
						<tr>
							<th>{{ __("Process") }}</th>
							<th>{{ __("Planned Item") }}</th>
							<th class="arrow"></th>
							<th>{{ __("Actual Item") }}</th>
							<th class="quantity">{{ __("Quantity") }}</th>
							<th>{{ __("Source") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in group.rows" :key="row.name || rowKey(row)"
							:class="{ unchanged: !isChanged(row) }">
							<td><span class="process-badge">{{ row.process_name || "—" }}</span></td>
							<td><button type="button" @click="openDoc('Item', row.planned_item)">{{ row.planned_item || "—" }}</button></td>
							<td class="arrow">→</td>
							<td><button type="button" class="actual-item" @click="openDoc('Item', row.actual_item)">{{ row.actual_item || "—" }}</button></td>
							<td class="quantity">{{ formatQty(row.actual_quantity) }} <small>{{ row.stock_uom || "" }}</small></td>
							<td>{{ sourceLabel(row.source_grn_count) }}</td>
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
		.filter((row) => flt(row.actual_quantity) > 0)
		.map((row) => ({ ...row }));
	search.value = "";
	process.value = "";
	includeUnchanged.value = false;
}

function isChanged(row) {
	return Boolean(row.planned_item && row.actual_item && row.planned_item !== row.actual_item);
}

const changedCount = computed(() => rows.value.filter(isChanged).length);
const processes = computed(() => [...new Set(rows.value.map((row) => row.process_name).filter(Boolean))]
	.sort((a, b) => String(a).localeCompare(String(b))));
const filteredRows = computed(() => {
	const term = search.value.toLowerCase();
	return rows.value.filter((row) => {
		if (!includeUnchanged.value && !isChanged(row)) return false;
		if (process.value && row.process_name !== process.value) return false;
		if (!term) return true;
		return [row.process_name, row.planned_item, row.actual_item, row.production_detail]
			.some((value) => String(value || "").toLowerCase().includes(term));
	});
});
const groups = computed(() => {
	const result = [];
	const byProductionDetail = new Map();
	for (const row of filteredRows.value) {
		const key = row.production_detail || "";
		if (!byProductionDetail.has(key)) {
			const group = { productionDetail: key, rows: [] };
			byProductionDetail.set(key, group);
			result.push(group);
		}
		byProductionDetail.get(key).rows.push(row);
	}
	return result;
});

function formatQty(value) {
	return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function sourceLabel(value) {
	const count = Number(value || 0);
	return count === 1 ? __("1 GRN") : __("{0} GRNs", [count]);
}

function rowKey(row) {
	return [row.production_detail, row.process_name, row.planned_item, row.actual_item, row.actual_quantity].join("|");
}

function openDoc(doctype, name) {
	if (name) frappe.set_route("Form", doctype, name);
}

defineExpose({ load_data });
</script>

<style scoped>
.actual-dia-conversions { padding: 4px 0 18px; }
.conversion-heading, .conversion-heading > div, .conversion-toolbar, .conversion-card > header {
	display: flex;
	align-items: center;
}
.conversion-heading { justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.conversion-heading h5 { margin: 0; font-size: 15px; }
.conversion-heading p { margin: 4px 0 0; color: var(--text-muted); font-size: 12px; }
.conversion-counts { gap: 7px; font-size: 11px; color: var(--text-muted); }
.conversion-counts span { padding: 2px 7px; border-radius: 999px; background: var(--subtle-fg); }
.conversion-counts .changed-count { background: var(--green-100, #d1fadf); color: var(--green-700, #027a48); font-weight: 600; }
.conversion-toolbar { flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.conversion-toolbar input[type="search"] { flex: 1 1 260px; }
.conversion-toolbar select { width: 170px; }
.conversion-toolbar label { display: flex; align-items: center; gap: 6px; margin: 0; }
.conversion-empty { display: flex; align-items: center; flex-direction: column; gap: 6px; padding: 32px; border: 1px dashed var(--border-color); border-radius: 8px; color: var(--text-muted); }
.conversion-card { margin-top: 12px; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; }
.conversion-card > header { justify-content: space-between; padding: 8px 11px; background: var(--subtle-fg); }
.conversion-card button { border: 0; padding: 0; background: transparent; color: var(--primary); font: inherit; cursor: pointer; }
.conversion-card > header button { font-weight: 600; }
.conversion-card > header span { color: var(--text-muted); font-size: 11px; }
.table-wrap { max-height: 520px; overflow: auto; }
.table { min-width: 820px; margin: 0; font-size: 12px; }
.table th { position: sticky; top: 0; z-index: 1; background: var(--subtle-fg); }
.table td, .table th { vertical-align: middle; }
.process-badge { padding: 2px 7px; border-radius: 999px; background: var(--blue-100, #d1e9ff); color: var(--blue-700, #175cd3); font-size: 11px; font-weight: 600; }
.actual-item { color: var(--green-700, #027a48) !important; }
.arrow { width: 34px; color: var(--text-muted); text-align: center; }
.quantity { width: 120px; text-align: right; font-variant-numeric: tabular-nums; }
.quantity small { color: var(--text-muted); }
.unchanged { opacity: 0.65; }
@media (max-width: 700px) {
	.conversion-heading, .conversion-toolbar { align-items: stretch; flex-direction: column; }
	.conversion-toolbar select { width: 100%; }
}
</style>
