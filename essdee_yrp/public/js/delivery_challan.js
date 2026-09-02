frappe.ui.form.on("Delivery Challan", {
	work_order(frm) {
		if (frm.doc.docstatus !== 0) return;
		// Source location and warehouse are specific to this dispatch. Never
		// retain or inherit the Work Order's delivery location when the operator
		// selects or changes the Work Order.
		frm.set_value({
			from_location: "",
			from_warehouse: "",
		});
	},

	refresh(frm) {
		exclude_cut_panel_movement_from_cancel_all(frm);
		setTimeout(() => {
			essdee_yrp.contain_item_editor_matrix(frm, ["item_html", "correction_item_html"]);
			replace_return_button(frm);
		}, 0);
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
	},
});

function replace_return_button(frm) {
	if (
		frm.doc.docstatus !== 1 ||
		!frappe.model.can_create("Goods Received Note") ||
		!frappe.production?.ui?.ReturnItemsMatrix
	) {
		return;
	}
	frm.remove_custom_button(__("Return"));
	frm.add_custom_button(__("Return"), () => load_return_matrix(frm));
}

function load_return_matrix(frm) {
	frappe.call({
		method: "yrp.yrp.doctype.delivery_challan.delivery_challan.get_return_delivery_items",
		args: {doc_name: frm.doc.name},
		freeze: true,
		freeze_message: __("Loading returnable items..."),
		callback(r) {
			if (!r.message) return;
			show_return_matrix(frm, r.message);
		},
	});
}

function show_return_matrix(frm, data) {
	let matrix;
	const dialog = new frappe.ui.Dialog({
		title: __("Return Items from {0}", [frm.doc.name]),
		size: "extra-large",
		fields: [
			{
				fieldname: "return_whole_bundles",
				fieldtype: "Check",
				label: __("Return Whole Bundles"),
				description: __("Leave unchecked for normal or collapsed-bundle returns."),
			},
			{
				fieldname: "cut_panel_movement",
				fieldtype: "Link",
				options: "Cut Panel Movement",
				label: __("Return Cut Panel Movement"),
				mandatory_depends_on: "eval:doc.return_whole_bundles",
				depends_on: "eval:doc.return_whole_bundles",
				get_query: () => ({
					filters: {
						docstatus: 1,
						lot: frm.doc.lot,
						against_id: ["is", "not set"],
					},
				}),
			},
			{fieldname: "return_matrix_html", fieldtype: "HTML"},
		],
		primary_action_label: __("Create Return GRN"),
		primary_action(values) {
			const selected = matrix.get_data();
			if (values.return_whole_bundles && !values.cut_panel_movement) {
				frappe.throw(__("Select the Return Cut Panel Movement."));
			}
			frappe.call({
				method: "essdee_yrp.delivery_challan_hooks.create_return_grn",
				args: {
					doc_name: frm.doc.name,
					items: selected.items,
					received_type: selected.received_type,
					cut_panel_movement: values.return_whole_bundles
						? values.cut_panel_movement
						: "",
				},
				freeze: true,
				freeze_message: __("Creating Return GRN..."),
				callback(r) {
					if (!r.message) return;
					dialog.hide();
					frappe.set_route("Form", "Goods Received Note", r.message);
				},
			});
		},
	});
	const wrapper = dialog.fields_dict.return_matrix_html.$wrapper;
	wrapper.empty();
	matrix = new frappe.production.ui.ReturnItemsMatrix(wrapper);
	matrix.load_data(data);
	dialog.show();
}

function exclude_cut_panel_movement_from_cancel_all(frm) {
	if (frm.doc.docstatus !== 1 || !frm.doc.cut_panel_movement) return;
	const ignored = new Set(frm.ignore_doctypes_on_cancel_all || []);
	ignored.add("Cut Panel Movement");
	frm.ignore_doctypes_on_cancel_all = [...ignored];
}
