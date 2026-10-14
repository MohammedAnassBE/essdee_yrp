frappe.provide("essdee_yrp");

essdee_yrp.dispatch_supplier_states = new WeakMap();

/** Supplier and Warehouse dialog fields for both ends of a finishing dispatch. */
essdee_yrp.dispatch_location_fields = function (get_dialog, defaults = {}) {
	return [
		["from", __("From")],
		["to", __("To")],
	].flatMap(([side, label]) => [
		{
			fieldname: `${side}_supplier`,
			fieldtype: "Link",
			label: __("{0} Supplier", [label]),
			options: "Supplier",
			reqd: 1,
			default: defaults[`${side}_supplier`],
			onchange: () => essdee_yrp.set_dispatch_supplier(get_dialog(), side),
		},
		{
			fieldname: `${side}_warehouse`,
			fieldtype: "Link",
			label: __("{0} Warehouse", [label]),
			options: "Warehouse",
			reqd: 1,
			get_query: () => ({
				filters: {
					disabled: 0,
					supplier: get_dialog().get_value(`${side}_supplier`) || "__unselected__",
				},
			}),
		},
	]);
};

/** Clear a side's Warehouse, then prefill the only one linked to its Supplier. */
essdee_yrp.set_dispatch_supplier = async function (dialog, side) {
	let dialog_state = essdee_yrp.dispatch_supplier_states.get(dialog);
	if (!dialog_state) {
		dialog_state = {};
		essdee_yrp.dispatch_supplier_states.set(dialog, dialog_state);
	}
	const state = (dialog_state[side] ||= { sequence: 0, warehouse_write: Promise.resolve() });
	const sequence = ++state.sequence;
	const set_warehouse = (value) => {
		state.warehouse_write = state.warehouse_write
			.catch(() => {})
			.then(() => dialog.set_value(`${side}_warehouse`, value));
		return state.warehouse_write;
	};
	const supplier = dialog.get_value(`${side}_supplier`);
	await set_warehouse("");
	if (!supplier || state.sequence !== sequence) return;
	const { message: warehouses = [] } = await frappe.call({
		method: "essdee_yrp.finishing.dispatch_locations.get_supplier_warehouses",
		args: { supplier },
	});
	if (state.sequence !== sequence || dialog.get_value(`${side}_supplier`) !== supplier) return;
	if (warehouses.length === 1) await set_warehouse(warehouses[0]);
	if (!warehouses.length) {
		frappe.msgprint(__("Supplier {0} has no Warehouse. Create one from the Supplier.", [supplier]));
	}
};
