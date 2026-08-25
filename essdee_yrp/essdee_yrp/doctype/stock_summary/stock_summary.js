// Copyright (c) 2026, Essdee and contributors

frappe.ui.form.on("Stock Summary", {
	refresh(frm) {
		frm.disable_save();
		const wrapper = frm.fields_dict.stock_summary_html.wrapper;
		$(wrapper).empty();
		frm.stock_summary = new frappe.production.ui.StockSummary(wrapper);
	},
});
