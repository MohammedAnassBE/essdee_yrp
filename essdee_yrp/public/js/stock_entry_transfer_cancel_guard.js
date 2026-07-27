// essdee_yrp — hide the desk "Cancel" action on Stock Entries created by the
// cross-bench mrp GRN transfer (their `source_grn` custom field is set).
//
// Such SEs must be cancelled ONLY by the mrp GRN-cancel flow (which reaches yrp
// through essdee_yrp.api.stock_transfer.cancel_grn_transfer and sets
// doc.flags.from_grn_transfer). The server-side before_cancel guard
// (guard_transfer_se_cancel) is the real protection; this just removes the
// tempting UI affordance so a user is never offered a cancel that will only throw.
//
// MECHANISM: for a SUBMITTED document Frappe renders "Cancel" as the page
// *secondary action* button, not a ⋯-menu item — see
// frappe/public/js/frappe/form/toolbar.js: get_action_status() -> "Cancel" ->
// set_page_actions() -> page.set_secondary_action(__("Cancel"), ...). The form's
// refresh_header() (which calls toolbar.refresh() and thus sets that button) runs
// BEFORE the client "refresh" trigger inside frappe.run_serially() in
// form.js#refresh(), so by the time this handler runs the Cancel button already
// exists and page.clear_secondary_action() reliably removes it (it adds the `hide`
// class AND unbinds the click). Scoped to source_grn SEs, so normal Stock Entries
// keep their Cancel untouched.
frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.source_grn) {
			frm.page.clear_secondary_action();
		}
	},
});
