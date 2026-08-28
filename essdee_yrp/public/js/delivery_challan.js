frappe.ui.form.on("Delivery Challan", {
	refresh(frm) {
		exclude_cut_panel_movement_from_cancel_all(frm);
		setTimeout(() => {
			essdee_yrp.contain_item_editor_matrix(frm, ["item_html", "correction_item_html"]);
		}, 0);
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
	},
});

function exclude_cut_panel_movement_from_cancel_all(frm) {
	if (frm.doc.docstatus !== 1 || !frm.doc.cut_panel_movement) return;
	const ignored = new Set(frm.ignore_doctypes_on_cancel_all || []);
	ignored.add("Cut Panel Movement");
	frm.ignore_doctypes_on_cancel_all = [...ignored];
}
