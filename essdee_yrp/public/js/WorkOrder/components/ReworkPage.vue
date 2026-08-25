<template>
	<div ref="root" class="rework-page">
		<div class="rework-heading">
			<div>
				<h3>{{ __("Rework Details") }}</h3>
				<p>{{ __("Clear non-standard Received Types into Accepted or Rejected stock.") }}</p>
			</div>
			<div v-if="hasRows" class="summary-pill">
				{{ rowCount }} {{ __("source rows") }} · {{ pendingTotal }} {{ __("pending") }}
			</div>
		</div>

		<div class="filter-card">
			<div class="filter-control lot-input"></div>
			<div class="filter-control item-input"></div>
			<div class="filter-control colour-input"></div>
			<div class="filter-control received-type-input"></div>
			<div class="filter-control show-reworked-input"></div>
			<div class="filter-actions">
				<button class="btn btn-primary" :disabled="loading" @click="getReworkItems">
					{{ loading ? __("Loading...") : __("Get Rework Items") }}
				</button>
				<button class="btn btn-default" :disabled="!hasRows" @click="download">
					{{ __("Download XL") }}
				</button>
				<button class="btn btn-default" :disabled="!hasRows || copying" @click="copyReport">
					{{ copying ? __("Copying...") : __("Copy") }}
				</button>
			</div>
		</div>

		<div v-if="!loading && loaded && !hasRows" class="empty-state">
			<div class="empty-icon">✓</div>
			<div>
				<strong>{{ __("No rework items found") }}</strong>
				<p>{{ __("Change the filters or enable Show Reworked to view completed rows.") }}</p>
			</div>
		</div>

		<div v-if="hasRows" class="table-card">
			<div class="table-responsive">
				<table class="table rework-table">
					<thead>
						<tr>
							<th></th>
							<th>{{ __("Series No") }}</th>
							<th>{{ __("Date") }}</th>
							<th>{{ __("GRN Number") }}</th>
							<th>{{ __("Lot") }}</th>
							<th>{{ __("Item") }}</th>
							<th>{{ __("Colour / Part") }}</th>
							<th v-for="type in items.types" :key="type">{{ type }}</th>
							<th>{{ __("Total") }}</th>
						</tr>
					</thead>
					<tbody>
						<template v-for="(value, key) in items.report_detail" :key="key">
							<tr class="summary-row" @click="toggleRow(key)">
								<td><span class="chevron" :class="{ open: expandedRowKey === key }">›</span></td>
								<td><strong>{{ key }}</strong></td>
								<td>{{ formatDate(value.date) }}</td>
								<td><a href="#" @click.stop.prevent="openGRN(value.grn_number)">{{ value.grn_number }}</a></td>
								<td>{{ value.lot }}</td>
								<td>{{ value.item }}</td>
								<td>{{ colourLabel(value.rework_detail) }}</td>
								<td v-for="type in items.types" :key="type">
									{{ displayQty(value, type) }}
								</td>
								<td><strong>{{ value.total - value.total_rejection }}</strong></td>
							</tr>
							<tr v-if="expandedRowKey === key" class="detail-row">
								<td :colspan="8 + items.types.length">
									<div v-for="(group, groupKey) in value.rework_detail" :key="groupKey" class="detail-panel">
										<div class="detail-panel-title">
											<div>
												<strong>{{ groupKey }}</strong>
												<span>{{ value.warehouse }}</span>
											</div>
											<span class="badge badge-orange">{{ mistakeLabel(groupKey) }}</span>
										</div>
										<div class="table-responsive">
											<table class="table size-table">
												<tbody>
													<tr>
														<th>{{ __("Size") }}</th>
														<th v-for="row in group.items" :key="row.row_name">{{ row[value.size] }}</th>
													</tr>
													<tr>
														<td>{{ __("Pending") }} {{ mistakeLabel(groupKey) }}</td>
														<td v-for="row in group.items" :key="row.row_name"><strong>{{ row.rework_qty }}</strong></td>
													</tr>
													<tr v-if="!showReworkedValue && canWrite">
														<td>{{ __("Rejection") }}</td>
														<td v-for="row in group.items" :key="row.row_name">
															<input v-model.number="row.rejected" type="number" min="0" :max="row.rework_qty" step="1" class="form-control" @input="group.changed = 1" />
														</td>
													</tr>
													<tr v-if="!showReworkedValue && canWrite">
														<td>{{ __("Reworked") }}</td>
														<td v-for="row in group.items" :key="row.row_name">
															<input v-model.number="row.rework" type="number" min="0" :max="row.rework_qty" step="1" class="form-control" />
														</td>
													</tr>
												</tbody>
											</table>
										</div>
										<div v-if="!showReworkedValue && canWrite" class="row-actions">
											<button class="btn btn-default btn-sm" :disabled="busy" @click="saveRejection(group)">{{ __("Update Rejection Qty") }}</button>
											<button class="btn btn-primary btn-sm" :disabled="busy" @click="convertReworked(group)">{{ __("Update Reworked Piece") }}</button>
											<button class="btn btn-danger btn-sm" :disabled="busy" @click="completeRework(group)">{{ __("Complete Rework") }}</button>
										</div>
										<div v-else-if="!showReworkedValue && !canWrite" class="permission-note">
											{{ __("You have read-only access. GRN Rework Item write permission is required to clear stock.") }}
										</div>
									</div>
								</td>
							</tr>
						</template>
						<tr class="total-row">
							<th colspan="7">{{ __("Total") }}</th>
							<th v-for="type in items.types" :key="type">
								{{ (items.total_detail[type] || 0) - (items.total_rejection_detail[type] || 0) }}
							</th>
							<th>{{ items.total_sum - items.total_rejection }}</th>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { copyElementAsImage } from "../../copyElementAsImage";

const METHOD = "essdee_yrp.essdee_yrp.doctype.grn_rework_item.grn_rework_item";
const root = ref(null);
const items = ref({ report_detail: {}, types: [], total_detail: {}, total_rejection_detail: {} });
const expandedRowKey = ref(null);
const loading = ref(false);
const loaded = ref(false);
const copying = ref(false);
const busy = ref(false);
const showReworkedValue = ref(false);
let lotControl;
let itemControl;
let colourControl;
let receivedTypeControl;
let showReworkedControl;

const hasRows = computed(() => Object.keys(items.value.report_detail || {}).length > 0);
const rowCount = computed(() => Object.keys(items.value.report_detail || {}).length);
const pendingTotal = computed(() => (items.value.total_sum || 0) - (items.value.total_rejection || 0));
const canWrite = computed(() => Boolean(items.value.permissions?.can_write));

onMounted(() => {
	lotControl = makeControl(".lot-input", { fieldname: "lot", fieldtype: "Link", options: "Lot", label: __("Lot") });
	itemControl = makeControl(".item-input", { fieldname: "item", fieldtype: "Link", options: "Item", label: __("Item") });
	colourControl = makeControl(".colour-input", { fieldname: "colour", fieldtype: "Data", label: __("Colour") });
	receivedTypeControl = makeControl(".received-type-input", { fieldname: "received_type", fieldtype: "Link", options: "Received Type", label: __("Received Type") });
	showReworkedControl = makeControl(".show-reworked-input", {
		fieldname: "show_reworked",
		fieldtype: "Check",
		label: __("Show Reworked"),
		change: () => { showReworkedValue.value = Boolean(showReworkedControl.get_value()); },
	});
	const route = frappe.get_route();
	const routeLot = (route?.[0] === "rework-details" ? route?.[1] : route?.[2]) || frappe.route_options?.lot;
	if (routeLot) lotControl.set_value(routeLot);
});

function makeControl(selector, df) {
	const parent = $(root.value).find(selector).empty();
	return frappe.ui.form.make_control({ parent, df, render_input: true });
}

function call(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({ method: `${METHOD}.${method}`, args, callback: (r) => resolve(r.message), error: reject });
	});
}

async function getReworkItems() {
	loading.value = true;
	try {
		items.value = await call("get_rework_items", {
			lot: lotControl.get_value(),
			item: itemControl.get_value(),
			colour: colourControl.get_value(),
			received_type: receivedTypeControl.get_value(),
			show_reworked: showReworkedControl.get_value() ? 1 : 0,
		}) || {};
		loaded.value = true;
		expandedRowKey.value = null;
	} finally {
		loading.value = false;
	}
}

function toggleRow(key) { expandedRowKey.value = expandedRowKey.value === key ? null : key; }
function colourLabel(details) { return Object.keys(details || {})[0]?.split("-").slice(1).join("-") || ""; }
function mistakeLabel(key) { return String(key || "").split("-")[0]; }
function displayQty(value, type) { return (value.types?.[type] || 0) - (value.rejection_detail?.[type] || 0); }
function formatDate(value) { return value ? frappe.datetime.str_to_user(String(value).slice(0, 10)) : ""; }
function openGRN(name) { window.open(`/app/goods-received-note/${encodeURIComponent(name)}`, "_blank"); }

function validGroup(group) {
	for (const row of group.items) {
		if ((Number(row.rejected) || 0) < 0 || (Number(row.rejected) || 0) > Number(row.rework_qty)) {
			frappe.msgprint(__("Rejected quantity must be between 0 and the pending quantity."));
			return false;
		}
		if ((Number(row.rework) || 0) < 0 || (Number(row.rework) || 0) > Number(row.rework_qty)) {
			frappe.msgprint(__("Reworked quantity must be between 0 and the pending quantity."));
			return false;
		}
	}
	return true;
}

async function saveRejection(group) {
	if (!group.changed) return frappe.msgprint(__("There is nothing changed in this row."));
	if (!validGroup(group)) return;
	await mutate("update_rejected_quantity", { rejection_data: group.items, completed: 0, lot: lotControl.get_value() }, __("Rejection quantity updated"));
}

async function convertReworked(group) {
	if (!validGroup(group) || !group.items.some((row) => Number(row.rework) > 0)) {
		return frappe.msgprint(__("Enter at least one Reworked quantity."));
	}
	frappe.confirm(__("Convert the entered pieces to Accepted stock?"), async () => {
		await mutate("update_partial_quantity", { data: group.items, lot: lotControl.get_value() }, __("Reworked pieces converted to Accepted"));
	});
}

function completeRework(group) {
	if (!validGroup(group)) return;
	frappe.confirm(
		__("Complete this rework? Remaining pieces will become Accepted and entered Rejection pieces will become Rejected."),
		async () => {
			await mutate("update_rejected_quantity", { rejection_data: group.items, completed: 1, lot: lotControl.get_value() }, __("Rework completed"));
		},
	);
}

async function mutate(method, args, message) {
	busy.value = true;
	try {
		await call(method, args);
		frappe.show_alert({ message, indicator: "green" });
		await getReworkItems();
	} finally {
		busy.value = false;
	}
}

async function copyReport() {
	copying.value = true;
	try {
		await copyElementAsImage(root.value);
		frappe.show_alert({ message: __("Copied to clipboard"), indicator: "green" });
	} finally {
		copying.value = false;
	}
}

function download() {
	const xhr = new XMLHttpRequest();
	xhr.open("POST", `/api/method/${METHOD}.download_xl`, true);
	xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
	xhr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
	xhr.responseType = "blob";
	xhr.onload = () => {
		if (xhr.status !== 200) return;
		const link = document.createElement("a");
		link.href = URL.createObjectURL(xhr.response);
		link.download = "rework_details.xlsx";
		link.click();
		URL.revokeObjectURL(link.href);
	};
	xhr.send($.param({ data: JSON.stringify(items.value) }));
}
</script>

<style scoped>
.rework-page { background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 10px; padding: 20px; color: var(--text-color); }
.rework-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }
.rework-heading h3 { margin: 0 0 4px; font-size: 20px; font-weight: 700; }
.rework-heading p, .empty-state p { margin: 0; color: var(--text-muted); }
.summary-pill { background: var(--control-bg); border-radius: 20px; padding: 7px 12px; white-space: nowrap; font-weight: 600; }
.filter-card { display: grid; grid-template-columns: repeat(5, minmax(145px, 1fr)); gap: 12px; padding: 14px; background: var(--subtle-fg); border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 18px; }
.filter-actions { grid-column: 1 / -1; display: flex; justify-content: flex-end; gap: 8px; }
.table-card { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; }
.rework-table { margin: 0; min-width: 1050px; }
.rework-table th { background: var(--subtle-fg); color: var(--text-muted); font-size: 12px; white-space: nowrap; }
.rework-table td, .rework-table th { padding: 10px; vertical-align: middle; border-color: var(--border-color); }
.summary-row { cursor: pointer; }
.summary-row:hover { background: var(--highlight-color); }
.chevron { display: inline-block; font-size: 22px; transition: transform .15s; }
.chevron.open { transform: rotate(90deg); }
.detail-row > td { padding: 14px 18px; background: var(--subtle-fg); }
.detail-panel { background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 8px; padding: 14px; margin-bottom: 10px; }
.detail-panel-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.detail-panel-title span:not(.badge) { color: var(--text-muted); font-size: 12px; margin-left: 10px; }
.badge-orange { background: var(--orange-100); color: var(--orange-700); padding: 5px 9px; border-radius: 12px; }
.size-table { margin: 0; min-width: 520px; }
.size-table td, .size-table th { text-align: center; min-width: 90px; }
.size-table td:first-child, .size-table th:first-child { text-align: left; min-width: 150px; }
.size-table input { min-width: 75px; text-align: right; }
.row-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.permission-note { color: var(--text-muted); margin-top: 10px; }
.total-row th { background: var(--control-bg); }
.empty-state { display: flex; align-items: center; justify-content: center; gap: 14px; padding: 50px 20px; border: 1px dashed var(--border-color); border-radius: 8px; }
.empty-icon { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; background: var(--green-100); color: var(--green-700); font-weight: 700; }
@media (max-width: 1100px) { .filter-card { grid-template-columns: repeat(3, minmax(150px, 1fr)); } }
@media (max-width: 700px) { .filter-card { grid-template-columns: 1fr; } .rework-heading { flex-direction: column; } .filter-actions { justify-content: flex-start; } }
</style>
