const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadWorkOrderForm() {
	const context = {
		console,
		__: (value) => value,
		flt: (value) => Number(value || 0),
		frappe: { ui: { form: { on() {} } } },
	};
	const sourcePath = path.join(__dirname, "work_order.js");
	vm.runInNewContext(fs.readFileSync(sourcePath, "utf8"), context, { filename: sourcePath });
	return context;
}

const form = loadWorkOrderForm();
const entry = {
	cloth_qty: 30,
	manual_inputs: [
		{ fieldname: "input_a", qty_per_output: 0.58 },
		{ fieldname: "input_b", qty_per_output: 0.42 },
	],
};

assert.deepEqual(
	[...form.knitting_input_updates(entry, 30)],
	[],
	"setting the prefilled cloth quantity keeps saved or edited yarn inputs",
);
assert.deepEqual(
	JSON.parse(JSON.stringify(form.knitting_input_updates(entry, 20))),
	[["input_a", 11.6], ["input_b", 8.4]],
	"a cloth quantity change splits yarn inputs by the yarn ratio",
);
assert.deepEqual([...form.knitting_input_updates(entry, 20)], [], "an unchanged quantity does not recalculate");
assert.deepEqual(
	JSON.parse(JSON.stringify(form.knitting_input_updates(entry, 10 / 3))),
	[["input_a", 1.933], ["input_b", 1.4]],
	"yarn inputs round to three decimals",
);
assert.deepEqual(
	JSON.parse(JSON.stringify(form.knitting_input_updates(entry, 0))),
	[["input_a", 0], ["input_b", 0]],
	"clearing the cloth quantity clears its yarn inputs",
);

function dateForm(doc, previous) {
	const values = [];
	const frm = { doc, _previous_planned_end_date: previous, set_value: (field, value) => { values.push([field, value]); doc[field] = value; } };
	return { frm, values };
}
const blank = dateForm({ planned_end_date: "2026-11-10", expected_delivery_date: "" }, "");
form.sync_expected_delivery_date(blank.frm);
assert.deepEqual(blank.values, [["expected_delivery_date", "2026-11-10"]], "an empty expected delivery date copies the end date");
const following = dateForm({ planned_end_date: "2026-11-12", expected_delivery_date: "2026-11-10" }, "2026-11-10");
form.sync_expected_delivery_date(following.frm);
assert.equal(following.frm.doc.expected_delivery_date, "2026-11-12", "a copied expected delivery date follows the end date");
const overridden = dateForm({ planned_end_date: "2026-11-12", expected_delivery_date: "2026-11-20" }, "2026-11-10");
form.sync_expected_delivery_date(overridden.frm);
assert.deepEqual(overridden.values, [], "a manual expected delivery date is kept");
assert.equal(overridden.frm._previous_planned_end_date, "2026-11-12");

console.log("work order dialog tests passed");
