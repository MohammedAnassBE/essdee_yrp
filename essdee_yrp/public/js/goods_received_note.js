frappe.ui.form.on("Goods Received Note", {
	refresh(frm) {
		exclude_grn_cut_panel_movement_from_cancel_all(frm);
		configure_bundle_return(frm);
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
	},
});

function exclude_grn_cut_panel_movement_from_cancel_all(frm) {
	if (frm.doc.docstatus !== 1 || !frm.doc.cut_panel_movement) return;
	const ignored = new Set(frm.ignore_doctypes_on_cancel_all || []);
	ignored.add("Cut Panel Movement");
	frm.ignore_doctypes_on_cancel_all = [...ignored];
}

function configure_bundle_return(frm) {
	if (!frm.fields_dict.cut_panel_movement) return;
	const editable_return = frm.doc.docstatus === 0 && Boolean(frm.doc.is_return);
	frm.set_df_property("cut_panel_movement", "hidden", editable_return ? 0 : 1);
	if (!editable_return) return;

	frm.set_df_property(
		"cut_panel_movement",
		"description",
		__(
			"Select the submitted Cut Panel Movement for an exact whole-bundle return. Leave this empty to return the entered quantity as collapsed-bundle stock.",
		),
	);
	frm.set_query("cut_panel_movement", () => {
		const filters = {
			docstatus: 1,
			against_id: ["is", "not set"],
		};
		if (frm.doc.supplier) filters.from_warehouse = frm.doc.supplier;
		if (frm.doc.lot) filters.lot = frm.doc.lot;
		return { filters };
	});
}
