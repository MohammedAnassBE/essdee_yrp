frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		essdee_yrp.add_send_sms_button(frm, {
			hidden_statuses: ["Closed", "Cancelled", "Partially Cancelled"],
		});
		essdee_yrp.add_send_whatsapp_button(frm, {
			hidden_statuses: ["Closed", "Cancelled", "Partially Cancelled"],
		});
	},
});
