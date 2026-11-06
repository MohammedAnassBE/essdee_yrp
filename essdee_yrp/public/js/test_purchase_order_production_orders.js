const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const scriptPath = __dirname + "/purchase_order.js";
const METHOD = "essdee_yrp.purchase_order_against";

function loadScript() {
	const calls = [];
	const dialogs = [];
	class Dialog {
		constructor(options) {
			this.options = options;
			this.hidden = 0;
			this.gridRefreshes = 0;
			this.fields_dict = { production_orders: { grid: { refresh: () => { this.gridRefreshes += 1; } } } };
			dialogs.push(this);
		}
		show() {}
		hide() { this.hidden += 1; }
	}
	const context = {
		console,
		__: (value) => value,
		essdee_yrp: { add_send_sms_button() {}, add_send_whatsapp_button() {} },
		frappe: {
			ui: { form: { on() {} }, Dialog },
			user: { has_role: () => false },
			perm: { has_perm: () => false },
			call(options) {
				calls.push(options);
				if (!options.callback) return;
				const message = options.method.endsWith("get_purchase_order_production_order") ? { item_name: "VEST" } : [];
				options.callback({ message });
			},
		},
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });
	return { context, calls, dialogs };
}

function makeForm({ docstatus = 0, canManage = true, canRemove = docstatus === 0, rows = ["PPO-1"], isNew = false } = {}) {
	const buttons = new Map();
	let reloads = 0;
	return {
		doc: {
			doctype: "Purchase Order",
			name: "YRP-PO-0012",
			docstatus,
			is_yrp_managed: 1,
			production_orders: rows.map((production_order) => ({ production_order, item_name: `ITEM-${production_order}` })),
			__onload: { can_manage_production_orders: canManage, can_remove_production_orders: canRemove },
		},
		is_new: () => isNew,
		add_custom_button(label, action) { buttons.set(label, action); },
		reload_doc() { reloads += 1; },
		buttons,
		get reloads() { return reloads; },
	};
}

function render(formOptions) {
	const runtime = loadScript();
	const frm = makeForm(formOptions);
	runtime.context.setup_purchase_order_production_order_actions(frm);
	return { ...runtime, frm };
}

// Draft, or submitted Development PO without PPOs (server flag): the button shows.
for (const options of [{}, { docstatus: 1, rows: [] }]) {
	const { frm } = render(options);
	assert.deepEqual([...frm.buttons.keys()], ["Add PPO"]);
}

// Server flag off (no submit permission, submitted with PPOs or without Development), cancelled, new: no button.
for (const options of [{ docstatus: 1, canManage: false }, { canManage: false }, { docstatus: 2 }, { isNew: true }]) {
	const { frm } = render(options);
	assert.deepEqual([...frm.buttons.keys()], []);
}

{
	const { frm, dialogs, calls } = render({ rows: ["PPO-1", "PPO-2"] });
	frm.buttons.get("Add PPO")();
	const table = dialogs[0].options.fields[0];
	assert.equal(table.fieldtype, "Table");
	assert.equal(table.cannot_delete_rows, false);
	assert.deepEqual(JSON.parse(JSON.stringify(table.data)), [
		{ production_order: "PPO-1", item_name: "ITEM-PPO-1" },
		{ production_order: "PPO-2", item_name: "ITEM-PPO-2" },
	]);
	const [ppo, itemName] = table.fields;
	assert.deepEqual([ppo.label, itemName.label, itemName.read_only], ["PPO", "Item Name", 1]);
	assert.deepEqual(JSON.parse(JSON.stringify(ppo.get_query())), { query: `${METHOD}.production_order_query` });

	const row = { production_order: "PPO-3" };
	ppo.onchange.call({ doc: row });
	assert.equal(calls[0].method, `${METHOD}.get_purchase_order_production_order`);
	assert.equal(row.item_name, "VEST");
	assert.equal(dialogs[0].gridRefreshes, 1);

	dialogs[0].options.primary_action({ production_orders: [{ production_order: "PPO-1" }, { production_order: "PPO-3" }, {}] });
	assert.equal(calls[1].method, `${METHOD}.update_purchase_order_production_orders`);
	assert.deepEqual(JSON.parse(JSON.stringify(calls[1].args)), { name: "YRP-PO-0012", production_orders: ["PPO-1", "PPO-3"] });
	assert.equal(dialogs[0].hidden, 1);
	assert.equal(frm.reloads, 1);
}

// Submitted Development PO, or Draft with a live Telegram request: rows cannot be deleted.
for (const options of [{ docstatus: 1, rows: [] }, { canRemove: false }]) {
	const { frm, dialogs } = render(options);
	frm.buttons.get("Add PPO")();
	assert.equal(dialogs[0].options.fields[0].cannot_delete_rows, true);
}

console.log("purchase order production order desk tests passed");
