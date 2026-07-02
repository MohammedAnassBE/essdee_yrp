frappe.ui.form.on("Production Order", {
	refresh(frm) {
		render_lot_ordered_details(frm);
	},
});

function render_lot_ordered_details(frm) {
	const field = frm.fields_dict["lot_ordered_html"];
	if (!field) return;

	field.$wrapper.html("");
	frm.lot_ordered_view = null;

	if (frm.is_new()) return;

	const view = new frappe.production.ui.LotOrderedDetail(field.wrapper);
	const requested_name = frm.doc.name;
	frm.lot_ordered_view = view;
	frappe.call({
		method: "essdee_yrp.production_order.get_lot_ordered_details",
		args: { production_order: requested_name },
		callback(response) {
			// Ignore stale responses after switching to another record.
			if (frm.lot_ordered_view !== view || frm.doc.name !== requested_name) return;
			view.load_data(response.message || {});
		},
	});
}
