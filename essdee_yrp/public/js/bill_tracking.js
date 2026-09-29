// Essdee adds its YRP Purchase Invoice path. Base YRP owns the ERPNext
// Purchase Invoice field and actions.

frappe.ui.form.on("YRP Bill Tracking", {
	refresh(frm) {
		configure_purchase_invoice_actions(frm);
	},
});

function configure_purchase_invoice_actions(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 1) return;

	const has_yrp_invoice = Boolean(frm.doc.purchase_invoice);
	const has_erp_invoice = Boolean(frm.doc.erp_purchase_invoice);
	const can_create_invoice =
		frappe.user.has_role("Accounts Manager") || frappe.user.has_role("Accounts User");

	if (!has_yrp_invoice && !has_erp_invoice && can_create_invoice) {
		frm.add_custom_button(__("Create YRP Purchase Invoice"), () => {
			const invoice = frappe.model.get_new_doc("YRP Purchase Invoice");
			invoice.supplier = frm.doc.supplier;
			invoice.billing_supplier = frm.doc.supplier;
			invoice.bill_date = frm.doc.bill_date;
			invoice.bill_no = frm.doc.bill_no;
			invoice.bill_tracking = frm.doc.name;
			frappe.set_route("Form", invoice.doctype, invoice.name);
		});
	}

	if (has_yrp_invoice) {
		frm.add_custom_button(__("Show YRP Purchase Invoice"), () => {
			frappe.set_route("Form", "YRP Purchase Invoice", frm.doc.purchase_invoice);
		});
	}
}
