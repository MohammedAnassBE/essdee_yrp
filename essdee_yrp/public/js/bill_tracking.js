// Essdee adds its YRP Purchase Invoice path. Base YRP owns the ERPNext
// Purchase Invoice field and actions.

const CANCEL_PENDING_STATUS = "Pending Approval";
const CANCEL_APPROVED_STATUS = "Cancel Request Approved";
const CANCEL_REQUESTABLE_STATUSES = ["Open", "Assigned", "Reopen", "Amended"];

frappe.ui.form.on("YRP Bill Tracking", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1) return;

		frm.remove_custom_button(__("Cancel"));
		if (is_cancellation_status(frm.doc.form_status)) {
			remove_conflicting_actions(frm);
		} else {
			configure_purchase_invoice_actions(frm);
		}
		configure_cancellation_action(frm);
	},
});

function is_cancellation_status(status) {
	return [CANCEL_PENDING_STATUS, CANCEL_APPROVED_STATUS].includes(status);
}

function remove_conflicting_actions(frm) {
	for (const label of [
		"Assign",
		"Create ERP Purchase Invoice",
		"Create YRP Purchase Invoice",
		"Bill Received",
	]) {
		frm.remove_custom_button(__(label));
	}
}

function configure_purchase_invoice_actions(frm) {
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

function configure_cancellation_action(frm) {
	if (frm.doc.purchase_invoice || frm.doc.erp_purchase_invoice) return;

	if (CANCEL_REQUESTABLE_STATUSES.includes(frm.doc.form_status) && frappe.user.has_role("HR User")) {
		frm.add_custom_button(__("Request for Cancel"), () => {
			call_cancel_transition(
				frm,
				"request_bill_cancellation",
				__("Request cancellation approval for this YRP Bill Tracking?")
			);
		});
		return;
	}

	if (frm.doc.form_status === CANCEL_PENDING_STATUS && frappe.user.has_role("HR Manager")) {
		frm.add_custom_button(__("Approve Cancel Request"), () => {
			call_cancel_transition(
				frm,
				"approve_bill_cancellation",
				__("Approve the cancellation request for this YRP Bill Tracking?")
			);
		});
		return;
	}

	if (frm.doc.form_status === CANCEL_APPROVED_STATUS && frappe.user.has_role("HR User")) {
		frm.add_custom_button(__("Cancel"), () => show_cancel_dialog(frm));
	}
}

function call_cancel_transition(frm, method, confirmation) {
	frappe.confirm(confirmation, () => {
		frappe.call({
			method: `essdee_yrp.overrides.bill_tracking.${method}`,
			args: { name: frm.doc.name },
			freeze: true,
			callback: () => frm.reload_doc(),
		});
	});
}

function show_cancel_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Cancel Bill"),
		fields: [
			{ label: "Cancel Reason", fieldname: "cancel_reason", fieldtype: "Small Text", reqd: 1 },
		],
		primary_action_label: __("Confirm"),
		primary_action: (values) => {
			frappe.call({
				method: "essdee_yrp.overrides.bill_tracking.cancel_vendor_bill",
				args: { name: frm.doc.name, cancel_reason: values.cancel_reason },
				freeze: true,
				freeze_msg: __("Cancelling Document"),
				callback: () => {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}
