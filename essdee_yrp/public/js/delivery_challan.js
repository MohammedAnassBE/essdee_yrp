frappe.ui.form.on("Delivery Challan", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
	},
});
