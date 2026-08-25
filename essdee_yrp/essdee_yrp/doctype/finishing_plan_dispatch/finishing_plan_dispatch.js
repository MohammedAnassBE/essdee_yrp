// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

const DISPATCH_METHOD =
	"essdee_yrp.essdee_yrp.doctype.finishing_plan_dispatch.finishing_plan_dispatch";

frappe.ui.form.on("Finishing Plan Dispatch", {
	refresh(frm) {
		mount_dispatch_editor(frm);
		const can_write = (frm.perm || []).some((permission) => permission.write);

		if (frm.doc.docstatus === 0 && can_write) {
			frm.add_custom_button(__("Fetch Items"), () => fetch_finishing_items(frm));
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Print Dispatch"), () => print_dispatch(frm));
			if (!frm.doc.stock_entry && can_write) {
				frm.add_custom_button(__("Dispatch Stock"), () => show_dispatch_dialog(frm));
			}
		}
	},

	validate(frm) {
		if (frm.finishing_dispatch) {
			frm.doc.finishing_items = JSON.stringify(frm.finishing_dispatch.get_data() || []);
		}
	},
});

function mount_dispatch_editor(frm) {
	const field = frm.fields_dict.finishing_plan_dispatch_html;
	if (!field || !frappe.production?.ui?.FinishingPlanDispatch) return;

	if (frm.finishing_dispatch?.app) {
		frm.finishing_dispatch.app.unmount();
	}
	$(field.wrapper).empty();
	frm.finishing_dispatch = new frappe.production.ui.FinishingPlanDispatch(field.wrapper);

	const items = frm.doc.__onload?.items;
	if (Array.isArray(items)) {
		frm.doc.finishing_items = JSON.stringify(items);
		frm.finishing_dispatch.load_data(items);
		return;
	}
	if (frm.doc.docstatus === 0 && frm.is_new()) {
		fetch_finishing_items(frm);
	}
}

async function fetch_finishing_items(frm) {
	if (!frm.finishing_dispatch) return;
	const response = await frappe.call({
		method: `${DISPATCH_METHOD}.fetch_fp_items`,
		freeze: true,
		freeze_message: __("Fetching Finishing Plans..."),
	});
	const items = response.message || [];
	frm.finishing_dispatch.load_data(items);
	frm.doc.finishing_items = JSON.stringify(items);
	frm.dirty();
	frappe.show_alert({
		message: __("{0} Finishing Plan(s) fetched", [items.length]),
		indicator: items.length ? "green" : "orange",
	});
}

function print_dispatch(frm) {
	const url = frappe.urllib.get_full_url(
		`/printview?doctype=${encodeURIComponent(frm.doc.doctype)}` +
			`&name=${encodeURIComponent(frm.doc.name)}` +
			`&trigger_print=1&format=${encodeURIComponent("Essdee Finishing Plan Dispatch")}` +
			"&no_letterhead=1",
	);
	if (!window.open(url)) {
		frappe.msgprint(__("Please enable pop-ups"));
	}
}

function show_dispatch_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Dispatch Stock"),
		fields: [
			{
				fieldname: "from_location",
				fieldtype: "Link",
				label: __("From Warehouse"),
				options: "Warehouse",
				reqd: 1,
			},
			{
				fieldname: "to_location",
				fieldtype: "Link",
				label: __("To Supplier"),
				options: "Supplier",
				reqd: 1,
			},
			{
				fieldname: "goods_value",
				fieldtype: "Currency",
				label: __("Goods Value"),
				reqd: 1,
			},
			{
				fieldname: "vehicle_no",
				fieldtype: "Data",
				label: __("Vehicle No"),
				reqd: 1,
			},
		],
		primary_action_label: __("Dispatch"),
		async primary_action(values) {
			dialog.disable_primary_action();
			try {
				const response = await frappe.call({
					method: `${DISPATCH_METHOD}.create_stock_dispatch`,
					args: { doc_name: frm.doc.name, ...values },
					freeze: true,
					freeze_message: __("Dispatching Items..."),
				});
				dialog.hide();
				await frm.reload_doc();
				frappe.show_alert({
					message: __("Stock Entry {0} created", [response.message]),
					indicator: "green",
				});
			} finally {
				dialog.enable_primary_action();
			}
		},
	});
	dialog.show();
}
