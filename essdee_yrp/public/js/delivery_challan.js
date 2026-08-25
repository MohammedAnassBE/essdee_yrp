frappe.ui.form.on("Delivery Challan", {
	refresh(frm) {
		setTimeout(() => {
			essdee_yrp.contain_item_editor_matrix(frm, ["item_html", "correction_item_html"]);
		}, 0);
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
	},
});
