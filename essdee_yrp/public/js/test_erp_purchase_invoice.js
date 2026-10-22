const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const scriptPath = __dirname + "/erp_purchase_invoice.js";
const DEFAULTS_METHOD = "essdee_yrp.erp_purchase_invoice.get_bill_tracking_invoice_defaults";

function loadFormScript(defaults) {
	const registered = {};
	const xcalls = [];
	const context = {
		frappe: {
			ui: { form: { on(doctype, handlers) { registered[doctype] = handlers; } } },
			async xcall(method, args) {
				xcalls.push({ method, args });
				return defaults;
			},
		},
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });
	return { handlers: registered["Purchase Invoice"], xcalls };
}

function makeForm(doc, isNew = true) {
	const values = [];
	return {
		doc,
		values,
		is_new: () => isNew,
		async set_value(value) { values.push(value); },
	};
}

(async () => {
	const defaults = {
		supplier: "SUP-1", bill_no: "B-1", bill_date: "2026-10-20",
		vendor_bill_tracking: "BT-1", remarks: "Bill Tracking Invoice Value: 10",
	};

	{
		const { handlers, xcalls } = loadFormScript(defaults);
		const frm = makeForm({ vendor_bill_tracking: "BT-1" });
		await handlers.onload(frm);
		assert.deepEqual(JSON.parse(JSON.stringify(xcalls)), [{ method: DEFAULTS_METHOD, args: { name: "BT-1" } }]);
		assert.deepEqual(frm.values, [defaults]);
	}

	for (const [doc, isNew] of [
		[{ vendor_bill_tracking: "BT-1" }, false],
		[{ vendor_bill_tracking: "BT-1", bill_no: "B-1" }, true],
		[{}, true],
		[{ vendor_bill_tracking: "BT-1", is_return: 1 }, true],
	]) {
		const { handlers, xcalls } = loadFormScript(defaults);
		const frm = makeForm(doc, isNew);
		await handlers.onload(frm);
		assert.deepEqual(xcalls, [], JSON.stringify({ doc, isNew }));
		assert.deepEqual(frm.values, []);
	}

	console.log("ERP Purchase Invoice Bill Tracking prefill tests passed");
})().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});
