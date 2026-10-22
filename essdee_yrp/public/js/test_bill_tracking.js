const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const scriptPath = __dirname + "/bill_tracking.js";

const PERMISSIONS_METHOD = "yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.get_role_permissions";

function loadFormScript(permissions = {}, defaults = {}, canCreateErpInvoice = true) {
	let handlers;
	const calls = [];
	const xcalls = [];
	const confirmations = [];
	const dialogs = [];
	const invoices = [];
	const routes = [];
	const prefillCalls = [];
	const context = {
		console,
		__: (value) => value,
		frappe: {
			ui: {
				form: { on(_doctype, registeredHandlers) { handlers = registeredHandlers; } },
				Dialog: class {
					constructor(options) {
						this.options = options;
						dialogs.push(this);
					}
					show() {}
					hide() {}
				},
			},
			user: { has_role: () => true },
			async xcall(method, args) {
				xcalls.push(method);
				if (method === PERMISSIONS_METHOD) return permissions;
				prefillCalls.push({ method, args });
				if (defaults instanceof Error) throw defaults;
				return defaults;
			},
			confirm(message, action) {
				confirmations.push(message);
				action();
			},
			call(options) {
				calls.push(options);
				if (options.callback) options.callback({ message: true });
			},
			model: {
				get_new_doc: () => ({}),
				can_create: (doctype) => doctype !== "Purchase Invoice" || canCreateErpInvoice,
			},
			async new_doc(doctype, options, initialize) {
				await Promise.resolve();
				const doc = { doctype, name: "new-invoice", company: "Configured Company" };
				initialize(doc);
				invoices.push(doc);
				routes.push(["Form", doctype, doc.name]);
			},
			set_route(...route) { routes.push(route); },
		},
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });
	return { handlers, calls, xcalls, confirmations, dialogs, invoices, routes, prefillCalls };
}

function makeForm(formStatus) {
	const buttons = new Map([
		["Assign", () => {}],
		["Cancel", () => {}],
		["Create ERP Purchase Invoice", () => {}],
		["Bill Received", () => {}],
	]);
	let reloads = 0;
	return {
		doc: {
			name: "YRP-BT-TEST",
			docstatus: 1,
			form_status: formStatus,
			purchase_invoice: null,
			erp_purchase_invoice: null,
		},
		is_new: () => false,
		add_custom_button(label, action) { if (!buttons.has(label)) buttons.set(label, action); },
		remove_custom_button(label) { buttons.delete(label); },
		reload_doc() { reloads += 1; },
		buttons,
		get reloads() { return reloads; },
	};
}

async function render(status, permissions, defaults, canCreateErpInvoice) {
	const runtime = loadFormScript(permissions, defaults, canCreateErpInvoice);
	const frm = makeForm(status);
	await runtime.handlers.refresh(frm);
	return { ...runtime, frm };
}

(async () => {
	{
		const { frm, calls, confirmations } = await render("Open", { can_request_cancel: true });
		assert.deepEqual(new Set(frm.buttons.keys()), new Set([
			"Assign",
			"Bill Received",
			"Request for Cancel",
		]));
		frm.buttons.get("Request for Cancel")();
		assert.equal(confirmations.length, 1);
		assert.equal(calls.at(-1).method, "essdee_yrp.overrides.bill_tracking.request_bill_cancellation");
		assert.equal(calls.at(-1).args.name, "YRP-BT-TEST");
		assert.equal(frm.reloads, 1);
	}

	{
		const { frm, calls } = await render("Pending Approval", { can_approve_cancel: true });
		assert.deepEqual([...frm.buttons.keys()], ["Approve Cancel Request"]);
		frm.buttons.get("Approve Cancel Request")();
		assert.equal(calls.at(-1).method, "essdee_yrp.overrides.bill_tracking.approve_bill_cancellation");
		assert.equal(frm.reloads, 1);
	}

	{
		const { frm, dialogs, calls } = await render("Cancel Request Approved", { can_request_cancel: true });
		assert.deepEqual([...frm.buttons.keys()], ["Cancel"]);
		frm.buttons.get("Cancel")();
		assert.equal(dialogs.length, 1);
		assert.equal(dialogs[0].options.fields[0].fieldname, "cancel_reason");
		dialogs[0].options.primary_action({ cancel_reason: "duplicate bill" });
		assert.equal(calls.at(-1).method, "essdee_yrp.overrides.bill_tracking.cancel_vendor_bill");
		assert.equal(calls.at(-1).args.name, "YRP-BT-TEST");
		assert.equal(calls.at(-1).args.cancel_reason, "duplicate bill");
		assert.equal(frm.reloads, 1);
	}

	{
		const { frm } = await render("Cancel Request Approved", { can_approve_cancel: true });
		assert.deepEqual([...frm.buttons.keys()], []);
	}

	{
		const { frm, xcalls } = await render("Open", { can_create_invoice: true });
		assert.deepEqual(xcalls, [PERMISSIONS_METHOD]);
		assert.deepEqual(new Set(frm.buttons.keys()), new Set([
			"Assign",
			"Create ERP Purchase Invoice",
			"Bill Received",
			"Create YRP Purchase Invoice",
		]));
	}

	{
		const { frm } = await render("Open", { can_create_invoice: true }, {}, false);
		assert.deepEqual(new Set(frm.buttons.keys()), new Set([
			"Assign",
			"Bill Received",
			"Create YRP Purchase Invoice",
		]));
	}

	{
		const { frm } = await render("Open", {});
		assert.deepEqual(new Set(frm.buttons.keys()), new Set([
			"Assign",
			"Bill Received",
		]));
	}

	{
		const defaults = {
			supplier: "SUP-LOCAL-VBT", bill_no: "LOCAL-VBT-42", bill_date: "2026-10-20",
			vendor_bill_tracking: "YRP-BT-TEST", remarks: "Bill Tracking Invoice Value: 1250.75",
		};
		const { frm, invoices, routes, prefillCalls } = await render("Open", { can_create_invoice: true }, defaults);
		frm.doc.supplier = "XXXXXXXXXX";
		await frm.buttons.get("Create ERP Purchase Invoice")();
		assert.equal(invoices.length, 1);
		assert.deepEqual(invoices[0], {
			doctype: "Purchase Invoice", name: "new-invoice", company: "Configured Company", ...defaults,
		});
		assert.equal(prefillCalls[0].method, "essdee_yrp.erp_purchase_invoice.get_bill_tracking_invoice_defaults");
		assert.equal(prefillCalls[0].args.name, frm.doc.name);
		assert.deepEqual(routes, [["Form", "Purchase Invoice", "new-invoice"]]);
	}

	{
		const failure = new Error("No permission to read this bill");
		const { frm, invoices, routes } = await render("Open", { can_create_invoice: true }, failure);
		await assert.rejects(frm.buttons.get("Create ERP Purchase Invoice"), failure);
		assert.equal(invoices.length, 0);
		assert.equal(routes.length, 0);
	}

	console.log("Essdee YRP Bill Tracking UI behavior tests passed");
})().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});
