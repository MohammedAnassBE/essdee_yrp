const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const scriptPath = __dirname + "/purchase_order_attribute_values.js";
const METHOD = "essdee_yrp.purchase_order_attribute_values";
const ROWS = [
	{
		name: "ROW-1", idx: 1, item_code: "Yarn-Red", qty: 12, uom: "Kg", rate: 10, amount: 120,
		attributes: [
			{ attribute: "Colour", value: "Red", options: ["Red", "Blue"], editable: true },
			{ attribute: "Stage", value: "Yarn", options: ["Yarn"], editable: false },
		],
	},
	{ name: "ROW-2", idx: 2, item_code: "Plain", qty: 3, uom: "Nos", rate: 1, amount: 3, attributes: [] },
];

function load({ roles = ["System Manager"], allowed = true } = {}) {
	let handlers;
	const calls = [];
	const dialogs = [];
	const context = {
		console,
		__: (value, args) => (args ? value.replace(/\{(\d)\}/g, (_match, index) => args[index]) : value),
		frappe: {
			user: { has_role: (role) => roles.includes(role) },
			scrub: (value) => value.toLowerCase().replace(/ /g, "_"),
			format: (value) => String(value),
			utils: { escape_html: (value) => value },
			msgprint() {},
			show_alert() {},
			ui: {
				form: { on(_doctype, registered) { handlers = registered; } },
				Dialog: class {
					constructor(options) { this.options = options; dialogs.push(this); }
					show() { this.shown = true; }
					hide() { this.hidden = true; }
				},
			},
			async xcall(method, args) {
				calls.push([method, args]);
				if (method.endsWith("can_update_purchase_order_attribute_values")) return allowed;
				if (method.endsWith("get_purchase_order_attribute_rows")) return { rows: ROWS };
				return { changes: [] };
			},
		},
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });
	return { handlers, calls, dialogs };
}

function makeForm(doc = {}) {
	const buttons = {};
	return {
		buttons,
		reloaded: 0,
		doc: { name: "PO-1", docstatus: 1, is_yrp_managed: 1, ...doc },
		is_new: () => false,
		add_custom_button(label, action) { buttons[label] = action; },
		reload_doc() { this.reloaded += 1; },
	};
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

(async () => {
	{
		const { handlers, calls, dialogs } = load();
		const frm = makeForm();
		handlers.refresh(frm);
		await flush();
		assert.ok(frm.buttons["Update Attribute Values"], "System Manager sees the button on an eligible order");
		assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), [`${METHOD}.can_update_purchase_order_attribute_values`, { name: "PO-1" }]);

		await frm.buttons["Update Attribute Values"]();
		const dialog = dialogs[0];
		const fieldnames = dialog.options.fields.map((field) => field.fieldname).filter(Boolean);
		assert.deepEqual([...fieldnames], ["ROW-1__summary", "ROW-1__colour", "ROW-1__stage"], "rows without attributes are left out");
		const stage = dialog.options.fields.find((field) => field.fieldname === "ROW-1__stage");
		assert.equal(stage.read_only, 1, "the dependent attribute stays read-only");

		await dialog.options.primary_action({ "ROW-1__colour": "Blue", "ROW-1__stage": "Yarn" });
		assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))), [
			`${METHOD}.update_purchase_order_attribute_values`,
			{ name: "PO-1", rows: [{ name: "ROW-1", item_code: "Yarn-Red", qty: 12, attributes: { Colour: "Blue" } }] },
		]);
		assert.equal(frm.reloaded, 1);
	}

	{
		const { handlers, calls, dialogs } = load();
		const frm = makeForm();
		handlers.refresh(frm);
		await flush();
		await frm.buttons["Update Attribute Values"]();
		await dialogs[0].options.primary_action({ "ROW-1__colour": "Red", "ROW-1__stage": "Yarn" });
		assert.equal(calls.length, 2, "an unchanged dialog sends no update");
		assert.ok(dialogs[0].hidden);
	}

	for (const [options, doc] of [
		[{ roles: ["Purchase Manager"] }, {}],
		[{}, { docstatus: 0 }],
		[{}, { is_yrp_managed: 0 }],
	]) {
		const { handlers, calls } = load(options);
		const frm = makeForm(doc);
		handlers.refresh(frm);
		await flush();
		assert.equal(calls.length, 0, "ineligible forms never ask the server");
		assert.equal(frm.buttons["Update Attribute Values"], undefined);
	}

	{
		const { handlers } = load({ allowed: false });
		const frm = makeForm();
		handlers.refresh(frm);
		await flush();
		assert.equal(frm.buttons["Update Attribute Values"], undefined, "a GRN-blocked order shows no button");
	}

	console.log("Essdee Purchase Order attribute value tests passed");
})().catch((error) => {
	console.error(error);
	process.exit(1);
});
