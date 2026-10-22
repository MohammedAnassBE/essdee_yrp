frappe.ui.form.on("Purchase Invoice", {
	async onload(frm) {
		const { vendor_bill_tracking, bill_no, is_return } = frm.doc;
		if (!frm.is_new() || !vendor_bill_tracking || bill_no || is_return) return;

		const defaults = await frappe.xcall(
			"essdee_yrp.erp_purchase_invoice.get_bill_tracking_invoice_defaults",
			{ name: vendor_bill_tracking }
		);
		await frm.set_value(defaults);
	},
});
