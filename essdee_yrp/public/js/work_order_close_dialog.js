frappe.provide("frappe.yrp.work_order");

// Essdee garment workflow vocabulary. Base YRP deliberately leaves this
// unset, which makes Close Reason a free-text Data field.
frappe.yrp.work_order.close_dialog_options = {
	reason_options: "\nCutting Shortage\nPrinting Shortage\nSewing Shortage\nSewing Missing\nOthers",
	other_reason_value: "Others",
};
