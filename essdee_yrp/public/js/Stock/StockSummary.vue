<template>
	<div ref="root" class="stock-summary">
		<div class="row align-items-end mb-3">
			<div class="lot-control col-md-2"></div>
			<div class="item-control col-md-2"></div>
			<div class="variant-control col-md-2"></div>
			<div class="warehouse-control col-md-2"></div>
			<div class="received-type-control col-md-2"></div>
			<div class="col-md-2 d-flex gap-2 pb-2">
				<button class="btn btn-primary btn-sm" @click="generate">Generate</button>
				<button class="btn btn-default btn-sm" @click="toggle_all">
					{{ all_selected ? "Clear" : "Select All" }}
				</button>
			</div>
		</div>

		<div v-if="loading" class="text-muted py-4">{{ __("Loading stock…") }}</div>
		<div v-else-if="rows.length" class="table-responsive">
			<div class="mb-3 d-flex flex-wrap gap-2">
				<button class="btn btn-primary btn-sm" @click="bulk_entry">Create Stock Entry</button>
				<button class="btn btn-default btn-sm" @click="reconcile">Reconcile to Zero</button>
				<button class="btn btn-default btn-sm" @click="transfer_lot">Transfer Lot</button>
				<button class="btn btn-default btn-sm" @click="reduce">Create Stock Reduction</button>
			</div>
			<table class="table table-sm table-bordered">
				<thead>
					<tr>
						<th></th><th>#</th><th>Lot</th><th>Item</th><th>Variant</th>
						<th>Warehouse</th><th>Received Type</th><th class="text-right">Balance</th>
						<th class="text-right">Rate</th><th></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in rows" :key="row_key(row, index)">
						<td><input v-model="selected" type="checkbox" :value="row" /></td>
						<td>{{ index + 1 }}</td>
						<td>{{ row.lot }}</td><td>{{ row.item_name }}</td><td>{{ row.item }}</td>
						<td>{{ row.warehouse }}</td><td>{{ row.received_type }}</td>
						<td class="text-right">{{ format_number(row.bal_qty) }} {{ row.stock_uom }}</td>
						<td class="text-right">{{ format_currency(row.val_rate) }}</td>
						<td><button class="btn btn-default btn-xs" @click="single_entry(row)">Create</button></td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else-if="generated" class="text-muted py-4">{{ __("No matching stock balance.") }}</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

const METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_stock_summary.sd_yrp_stock_summary.";
const root = ref(null);
const rows = ref([]);
const selected = ref([]);
const loading = ref(false);
const generated = ref(false);
const controls = {};
const control_doc = {};

const all_selected = computed(() => rows.value.length && selected.value.length === rows.value.length);

onMounted(() => {
	make_control("lot", ".lot-control", {
		fieldtype: "Table MultiSelect", label: "Lot", options: "SD YRP Lot MultiSelect",
	});
	make_control("item", ".item-control", { fieldtype: "Link", label: "Item", options: "YRP Item" });
	make_control("item_variant", ".variant-control", {
		fieldtype: "Link", label: "Item Variant", options: "YRP Item Variant",
	});
	make_control("warehouse", ".warehouse-control", {
		fieldtype: "Link", label: "Warehouse", options: "YRP Warehouse",
	});
	make_control("received_type", ".received-type-control", {
		fieldtype: "Link", label: "Received Type", options: "YRP Received Type",
	});
});

function make_control(name, selector, df) {
	const parent = $(root.value).find(selector).empty();
	controls[name] = frappe.ui.form.make_control({
		parent,
		df: { fieldname: name, ...df },
		doc: control_doc,
		render_input: true,
	});
}

function call(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: METHOD + method,
			args,
			callback: (response) => resolve(response.message),
			error: reject,
		});
	});
}

async function generate() {
	loading.value = true;
	selected.value = [];
	try {
		rows.value = (await call("get_stock_summary", {
			lot: controls.lot.get_value(),
			item: controls.item.get_value(),
			item_variant: controls.item_variant.get_value(),
			warehouse: controls.warehouse.get_value(),
			received_type: controls.received_type.get_value(),
		})) || [];
		generated.value = true;
	} finally {
		loading.value = false;
	}
}

function toggle_all() {
	selected.value = all_selected.value ? [] : [...rows.value];
}

function require_selection() {
	if (!selected.value.length) frappe.throw(__("Select at least one stock row."));
	const warehouses = [...new Set(selected.value.map((row) => row.warehouse))];
	if (warehouses.length !== 1) frappe.throw(__("Select stock from one Warehouse at a time."));
	return warehouses[0];
}

function purpose_dialog(action) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Purpose"),
		fields: [{
			fieldname: "purpose", fieldtype: "Select", label: "Purpose", reqd: 1,
			options: ["Send to Warehouse", "Material Receipt", "Material Issue", "Material Consumed"],
		}],
		primary_action_label: __("Continue"),
		primary_action(values) { dialog.hide(); action(values.purpose); },
	});
	dialog.show();
}

function location_dialog(purpose, warehouse, action) {
	const fields = [];
	if (purpose !== "Material Receipt") {
		fields.push({ fieldname: "from_warehouse", fieldtype: "Link", options: "YRP Warehouse", label: "From Warehouse", reqd: 1, default: warehouse });
	}
	if (["Material Receipt", "Send to Warehouse"].includes(purpose)) {
		fields.push({ fieldname: "to_warehouse", fieldtype: "Link", options: "YRP Warehouse", label: "To Warehouse", reqd: 1, default: purpose === "Material Receipt" ? warehouse : null });
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Stock Entry Locations"), fields,
		primary_action_label: __("Create Draft"),
		primary_action(values) { dialog.hide(); action(values); },
	});
	dialog.show();
}

function open_doc(doctype, name) {
	if (name) frappe.set_route("Form", doctype, name);
}

function bulk_entry() {
	const warehouse = require_selection();
	purpose_dialog((purpose) => location_dialog(purpose, warehouse, async (locations) => {
		open_doc("YRP Stock Entry", await call("create_bulk_stock_entry", {
			locations, selected_items: selected.value, purpose,
		}));
	}));
}

function single_entry(row) {
	purpose_dialog((purpose) => location_dialog(purpose, row.warehouse, async (locations) => {
		const values = {
			...row, ...locations, purpose,
			item_variant: row.item,
			qty: row.bal_qty,
			uom: row.stock_uom,
			posting_date: frappe.datetime.get_today(),
			posting_time: frappe.datetime.now_time(),
		};
		open_doc("YRP Stock Entry", await call("create_stock_entry", { stock_values: values }));
	}));
}

function reconcile() {
	const warehouse = require_selection();
	frappe.confirm(__("Create a Stock Reconciliation that sets the selected balances to zero?"), async () => {
		open_doc("YRP Stock Reconciliation", await call("stock_reconcile", { selected_items: selected.value, warehouse }));
	});
}

function reduce() {
	const warehouse = require_selection();
	frappe.confirm(__("Create a Stock Update draft for the selected balances?"), async () => {
		open_doc("YRP Stock Update", await call("reduce_stock", { selected_items: selected.value, warehouse }));
	});
}

function transfer_lot() {
	require_selection();
	const dialog = new frappe.ui.Dialog({
		title: __("Transfer to Lot"),
		fields: [{ fieldname: "lot", fieldtype: "Link", options: "SD YRP Lot", label: "Target Lot", reqd: 1 }],
		primary_action_label: __("Create Draft"),
		async primary_action(values) {
			dialog.hide();
			open_doc("SD YRP Lot Transfer", await call("lot_transfer_items", {
				selected_items: selected.value, transfer_lot: values.lot,
			}));
		},
	});
	dialog.show();
}

function row_key(row, index) {
	return [row.item, row.warehouse, row.lot, row.received_type, index].join("::");
}
function format_number(value) { return frappe.format(value || 0, { fieldtype: "Float" }); }
function format_currency(value) { return frappe.format(value || 0, { fieldtype: "Currency" }); }
</script>

<style scoped>
.stock-summary .gap-2 { gap: 0.5rem; }
.stock-summary th { white-space: nowrap; }
</style>
