// Copyright (c) 2026, Essdee and contributors

frappe.provide("essdee_yrp.mrp_stock");

frappe.ui.form.on("Item Conversion", {
	setup(frm) {
		for (const fieldname of ["from_item", "to_item"]) {
			frm.set_query(fieldname, () => ({ filters: { is_stock_item: 1 } }));
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1) frm.page.btn_secondary.hide();
	},
	warehouse(frm) { frm.item_conversion?.refresh_from_rates(); },
	from_item(frm) { frm.item_conversion?.refresh_from_rates(); },
});

essdee_yrp.mrp_stock.ItemConversion = class extends frappe.ui.form.Controller {
	refresh() {
		$(this.frm.fields_dict.item_conversion_html.wrapper).empty();
		this.frm.item_conversion = new frappe.production.ui.ItemConversion(
			this.frm.fields_dict.item_conversion_html.wrapper
		);
		this.frm.item_conversion.load_data({
			from_items: this.frm.doc.__onload?.from_item_details || [],
			to_items: this.frm.doc.__onload?.to_item_details || [],
		});
		this.frm.item_conversion.update_status();
	}
	validate() {
		if (!this.frm.item_conversion) frappe.throw(__("Refresh the form and try again."));
		const values = this.frm.item_conversion.get_items();
		if (!values.from_items.length) frappe.throw(__("Add From Items to continue"));
		if (!values.to_items.length) frappe.throw(__("Add To Items to continue"));
		this.frm.doc.from_item_details = JSON.stringify(values.from_items);
		this.frm.doc.to_item_details = JSON.stringify(values.to_items);
		this.frm.doc.from_total_amount = values.from_total_amount;
		this.frm.doc.to_total_amount = values.to_total_amount;
		this.frm.doc.difference_amount = values.difference_amount;
	}
	before_submit() {
		if (this.frm.item_conversion.get_items().has_difference) {
			frappe.throw(__("From Item value and To Item value must match before submit."));
		}
	}
};

extend_cscript(cur_frm.cscript, new essdee_yrp.mrp_stock.ItemConversion({ frm: cur_frm }));
