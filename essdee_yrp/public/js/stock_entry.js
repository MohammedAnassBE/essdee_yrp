frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;
		const supplier_key = frm.doc.to_supplier
			? "to_supplier"
			: frm.doc.from_supplier
				? "from_supplier"
				: null;
		if (!supplier_key) return;
		essdee_yrp.add_send_sms_button(frm, { supplier_key: supplier_key });
		essdee_yrp.add_send_whatsapp_button(frm, { supplier_key: supplier_key });
	},
});
