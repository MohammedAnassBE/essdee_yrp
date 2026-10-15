const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const WAREHOUSES = { "S-ONE": ["WH-ONE"], "S-MANY": ["WH-A", "WH-B"], "S-NONE": [] };

function load() {
	const messages = [];
	const context = {
		__: (value, args = []) => value.replace(/\{(\d)\}/g, (_match, index) => args[index]),
		frappe: {
			provide() {},
			msgprint: (message) => messages.push(message),
			call: async ({ method, args }) => {
				assert.equal(method, "essdee_yrp.finishing.dispatch_locations.get_supplier_warehouses");
				return { message: WAREHOUSES[args.supplier] };
			},
		},
	};
	context.essdee_yrp = {};
	vm.runInNewContext(fs.readFileSync(__dirname + "/supplier_warehouse.js", "utf8"), context);
	return { api: context.essdee_yrp, messages };
}

const plain = (value) => JSON.parse(JSON.stringify(value));

function dialogFor(fields) {
	const values = {};
	for (const field of fields) values[field.fieldname] = field.default || "";
	return {
		values,
		get_value: (fieldname) => values[fieldname],
		set_value: async (fieldname, value) => {
			values[fieldname] = value;
		},
	};
}

(async () => {
	const { api, messages } = load();
	let dialog;
	const fields = api.dispatch_location_fields(() => dialog, { from_supplier: "S-ONE" });
	dialog = dialogFor(fields);

	assert.deepEqual(
		plain(fields.map((field) => [field.fieldname, field.options, field.reqd])),
		[
			["from_supplier", "Supplier", 1],
			["from_warehouse", "Warehouse", 1],
			["to_supplier", "Supplier", 1],
			["to_warehouse", "Warehouse", 1],
		],
	);
	assert.deepEqual(plain(fields[1].get_query().filters), { disabled: 0, supplier: "S-ONE" });
	assert.deepEqual(plain(fields[3].get_query().filters), { disabled: 0, supplier: "__unselected__" });

	await api.set_dispatch_supplier(dialog, "from");
	assert.equal(dialog.values.from_warehouse, "WH-ONE", "a sole linked Warehouse is prefilled");

	dialog.values.to_supplier = "S-MANY";
	dialog.values.to_warehouse = "WH-OLD";
	await api.set_dispatch_supplier(dialog, "to");
	assert.equal(dialog.values.to_warehouse, "", "changing the Supplier clears its Warehouse");

	dialog.values.to_supplier = "S-NONE";
	await api.set_dispatch_supplier(dialog, "to");
	assert.deepEqual(messages, ["Supplier S-NONE has no Warehouse. Create one from the Supplier."]);

	let finish_validation;
	const delayed_dialog = dialogFor(fields);
	delayed_dialog.values.from_supplier = "S-ONE";
	delayed_dialog.set_value = async (fieldname, value) => {
		if (fieldname === "from_warehouse" && value === "WH-ONE") {
			await new Promise((resolve) => {
				finish_validation = resolve;
			});
		}
		delayed_dialog.values[fieldname] = value;
	};
	const old_supplier = api.set_dispatch_supplier(delayed_dialog, "from");
	while (!finish_validation) await Promise.resolve();
	delayed_dialog.values.from_supplier = "S-MANY";
	const new_supplier = api.set_dispatch_supplier(delayed_dialog, "from");
	finish_validation();
	await Promise.all([old_supplier, new_supplier]);
	assert.equal(
		delayed_dialog.values.from_warehouse,
		"",
		"a delayed Link validation cannot restore the previous Supplier's Warehouse",
	);

	console.log("supplier_warehouse.js: OK");
})().catch((error) => {
	console.error(error);
	process.exit(1);
});
