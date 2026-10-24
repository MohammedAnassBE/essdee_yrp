const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const scriptPath = __dirname + "/purchase_order.js";
const WAREHOUSES = { "S-ONE": ["WH-ONE"], "S-TWO": ["WH-TWO"], "S-MANY": ["WH-A", "WH-B"] };

function load(delay = () => Promise.resolve()) {
	let handlers;
	const calls = [];
	const context = {
		console,
		__: (value) => value,
		essdee_yrp: {},
		frappe: {
			ui: { form: { on(_doctype, registered) { handlers = registered; } }, Dialog: class {} },
			async call({ method, args }) {
				calls.push([method, args]);
				await delay();
				const warehouses = WAREHOUSES[args.supplier] || [];
				return { message: { supplier: args.supplier, warehouse: warehouses.length === 1 ? warehouses[0] : null } };
			},
		},
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });
	return { handlers, calls };
}

function makeForm(doc) {
	const frm = {
		doc: { doctype: "Purchase Order", is_yrp_managed: 1, default_delivery_location: "", set_warehouse: "", ...doc },
		async set_value(fieldname, value) { frm.doc[fieldname] = value; },
	};
	return frm;
}

(async () => {
	{
		const { handlers, calls } = load();
		const frm = makeForm({ default_delivery_location: "S-ONE" });
		await handlers.default_delivery_location(frm);
		assert.equal(frm.doc.set_warehouse, "WH-ONE", "a location's only Warehouse fills Set Target Warehouse");
		assert.deepEqual(JSON.parse(JSON.stringify(calls)), [
			["essdee_yrp.api.supplier_warehouse.get_single_location_options", { supplier: "S-ONE" }],
		]);

		frm.doc.default_delivery_location = "S-MANY";
		await handlers.default_delivery_location(frm);
		assert.equal(frm.doc.set_warehouse, "", "several Warehouses clear the previous location's Warehouse");

		frm.doc.default_delivery_location = "";
		frm.doc.set_warehouse = "WH-A";
		await handlers.default_delivery_location(frm);
		assert.equal(frm.doc.set_warehouse, "", "clearing the location clears its Warehouse");
	}

	{
		let release;
		const { handlers } = load(() => new Promise((resolve) => { release = resolve; }));
		const frm = makeForm({ default_delivery_location: "S-ONE" });
		const pending = handlers.default_delivery_location(frm);
		while (!release) await Promise.resolve();
		frm.doc.default_delivery_location = "S-TWO";
		release();
		await pending;
		assert.equal(frm.doc.set_warehouse, "", "a late answer for an old location is ignored");
	}

	{
		const { handlers, calls } = load();
		const frm = makeForm({ is_yrp_managed: 0, default_delivery_location: "S-ONE", set_warehouse: "WH-X" });
		await handlers.default_delivery_location(frm);
		assert.equal(frm.doc.set_warehouse, "WH-X", "plain ERPNext Purchase Orders are untouched");
		assert.equal(calls.length, 0);
	}

	console.log("Essdee Purchase Order delivery warehouse tests passed");
})().catch((error) => {
	console.error(error);
	process.exit(1);
});
