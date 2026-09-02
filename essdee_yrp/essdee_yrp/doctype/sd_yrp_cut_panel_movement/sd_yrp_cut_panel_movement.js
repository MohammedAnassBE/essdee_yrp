// Copyright (c) 2025, Essdee and contributors
// For license information, please see license.txt

const CPM_METHOD =
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_panel_movement.sd_yrp_cut_panel_movement";

frappe.ui.form.on("SD YRP Cut Panel Movement", {
	setup(frm) {
		frm.set_query("cutting_plan", () => {
			if (!frm.doc.lot || !frm.doc.item) {
				frappe.throw(__("Set Lot and Item before selecting a Cutting Plan."));
			}
			return { filters: { lot: frm.doc.lot, item: frm.doc.item } };
		});
	},

	refresh(frm) {
		mount_movement_editor(frm);
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Fetch Panels"), () => fetch_panels(frm));
			if (!frm.doc.cut_panel_movement_json) {
				fetch_panels(frm);
			}
		}
		if (frm.doc.docstatus === 1) {
			const active = frm.doc.__onload?.active_root_transactions || [];
			const unexpected = active.filter(
				(row) => row.doctype !== frm.doc.against || row.name !== frm.doc.against_id,
			);
			if (unexpected.length || (!frm.doc.against_id && active.length)) {
				show_active_transaction_warning(frm, active);
			} else if (!frm.doc.against_id) {
				add_create_buttons(frm);
			}
		}
	},

	validate(frm) {
		if (!frm.is_new() && frm.cutting_movement) {
			frm.doc.movement_data = JSON.stringify(frm.cutting_movement.get_items());
		}
	},
});

function show_active_transaction_warning(frm, active) {
	const references = active
		.map((row) => `${row.doctype} ${row.name} (${row.docstatus ? __("Submitted") : __("Draft")})`)
		.join(", ");
	frm.dashboard.set_headline(
		__("This Cut Panel Movement already has active transaction(s): {0}. Resolve them before creating another transaction.", [references]),
	);
	for (const row of active) {
		frm.add_custom_button(
			__("Open {0}", [row.name]),
			() => frappe.set_route("Form", row.doctype, row.name),
			__("Active Transactions"),
		);
	}
}

function mount_movement_editor(frm) {
	if (!frm.fields_dict.cut_panel_movement_html || !frappe.production.ui.CutPanelMovementBundle) {
		return;
	}
	if (frm.cutting_movement && frm.cutting_movement.app) {
		frm.cutting_movement.app.unmount();
	}
	$(frm.fields_dict.cut_panel_movement_html.wrapper).empty();
	frm.cutting_movement = new frappe.production.ui.CutPanelMovementBundle(
		frm.fields_dict.cut_panel_movement_html.wrapper,
	);
	let data = frm.doc.__onload && frm.doc.__onload.movement_details;
	if (!data && frm.doc.cut_panel_movement_json) {
		try {
			data =
				typeof frm.doc.cut_panel_movement_json === "string"
					? JSON.parse(frm.doc.cut_panel_movement_json)
					: frm.doc.cut_panel_movement_json;
		} catch (_error) {
			data = {};
		}
	}
	frm.doc.movement_data = JSON.stringify(data || {});
	frm.cutting_movement.load_data(data || {});
}

function fetch_panels(frm) {
	if (!frm.doc.from_warehouse || !frm.doc.lot) {
		frappe.throw(__("Set From Warehouse and Lot before fetching panels."));
	}
	frm.cutting_movement.load_data({});
	frappe.call({
		method: `${CPM_METHOD}.get_cut_bundle_unmoved_data`,
		args: {
			from_location: frm.doc.from_warehouse,
			lot: frm.doc.lot,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
			movement_from_cutting: frm.doc.movement_from_cutting,
			cutting_plan: frm.doc.cutting_plan,
			// Frappe form calls serialise booleans as text; cint("true") is 0.
			// Send the numeric flag so collapsed ledger rows reach the rendered UI.
			get_collapsed: 1,
		},
		freeze: true,
		freeze_message: __("Fetching available bundles..."),
		callback(r) {
			frm.cutting_movement.load_data(r.message || {});
			frm.doc.movement_data = JSON.stringify(r.message || {});
			frm.dirty();
		},
	});
}

function add_create_buttons(frm) {
	frm.add_custom_button(
		__("Stock Entry"),
		() => create_stock_entry(frm),
		__("Create"),
	);
	frm.add_custom_button(
		__("Delivery Challan"),
		() => select_work_order(frm, "YRP Delivery Challan"),
		__("Create"),
	);
	frm.add_custom_button(
		__("Goods Received Note"),
		() => select_work_order(frm, "YRP Goods Received Note"),
		__("Create"),
	);
}

function create_stock_entry(frm) {
	frappe.call({
		method: `${CPM_METHOD}.create_stock_entry`,
		args: { doc_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Preparing Stock Entry..."),
		callback(r) {
			if (!r.message) return;
			open_new_transaction("YRP Stock Entry", r.message);
		},
	});
}

function select_work_order(frm, target_doctype) {
	const fields = [
		{
			fieldname: "work_order",
			fieldtype: "Link",
			options: "YRP Work Order",
			label: __("Work Order"),
			reqd: true,
			get_query: () => ({
				filters: {
					lot: frm.doc.lot,
					docstatus: 1,
					open_status: ["!=", "Close"],
				},
			}),
		},
	];
	if (target_doctype === "YRP Goods Received Note") {
		fields.push({
			fieldname: "delivery_challan",
			fieldtype: "Link",
			options: "YRP Delivery Challan",
			label: __("Delivery Challan"),
			reqd: true,
			get_query: () => ({
				filters: {
					work_order: dialog.get_value("work_order") || "",
					docstatus: 1,
				},
			}),
		});
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Select Work Order"),
		fields,
		primary_action(values) {
			dialog.hide();
			const method =
				target_doctype === "YRP Delivery Challan"
					? "create_delivery_challan"
					: "create_goods_received_note";
			frappe.call({
				method: `${CPM_METHOD}.${method}`,
				args: {
					doc_name: frm.doc.name,
					work_order: values.work_order,
					delivery_challan: values.delivery_challan || "",
				},
				freeze: true,
				freeze_message: __(`Preparing ${target_doctype}...`),
				callback(r) {
					if (!r.message) return;
					open_new_transaction(target_doctype, r.message);
				},
			});
		},
	});
	dialog.show();
}

function open_new_transaction(doctype, values) {
	frappe.model.with_doctype(doctype, () => {
		const doc = frappe.model.get_new_doc(doctype);
		const prepared_item_details = values?.item_details || [];
		const ignored = new Set(["items", "correction_items", "correction_item_details"]);
		for (const [fieldname, value] of Object.entries(values || {})) {
			if (ignored.has(fieldname)) continue;
			if (fieldname === "item_details") {
				doc.item_details = JSON.stringify(value || []);
				continue;
			}
			if (frappe.meta.has_field(doctype, fieldname)) {
				doc[fieldname] = value;
			}
		}
		if (!doc.posting_date) doc.posting_date = frappe.datetime.nowdate();
		if (!doc.posting_time) {
			doc.posting_time = frappe.datetime.now_datetime().split(" ")[1];
		}
		frappe.set_route("Form", doctype, doc.name).then(() => {
			// The base DC and GRN forms fetch Work Order defaults when their
			// prepared link fields are mounted. Wait for that request, then restore
			// the exact CPM selection so it cannot be replaced by every pending
			// Work Order row.
			if (!["YRP Delivery Challan", "YRP Goods Received Note"].includes(doctype)) return;
			frappe.after_ajax(() => {
				if (cur_frm?.doctype !== doctype || cur_frm.doc.name !== doc.name) return;
				cur_frm.clear_table("items");
				cur_frm.refresh_field("items");
				cur_frm.doc.item_details = JSON.stringify(prepared_item_details);
				if (cur_frm.itemEditor) {
					cur_frm.itemEditor.load_data(prepared_item_details);
				}
				cur_frm.dirty();
			});
		});
	});
}
