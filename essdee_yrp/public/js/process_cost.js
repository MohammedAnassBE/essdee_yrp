// Essdee Process Cost values are scoped by the Lot's IPD and process.
frappe.ui.form.on("Process Cost", {
	setup(frm) {
		frm.set_query("attribute", () => {
			if (!frm.doc.lot) {
				frappe.throw(__("Select Lot before Attribute."));
			}
			if (!frm.doc.process_name) {
				frappe.throw(__("Select Process before Attribute."));
			}
			return {
				query: "essdee_yrp.process_cost.get_item_attributes",
				filters: {
					item: frm.doc.item,
					lot: frm.doc.lot,
					process: frm.doc.process_name,
				},
			};
		});
	},

	attribute(frm) {
		if (!frm.doc.attribute) {
			frm.clear_table("process_cost_values");
			frm.refresh_field("process_cost_values");
			return;
		}
		frappe.call({
			method: "essdee_yrp.process_cost.get_pc_attribute_values",
			args: {
				lot: frm.doc.lot,
				attribute: frm.doc.attribute,
				process_name: frm.doc.process_name,
			},
			callback(r) {
				frm.clear_table("process_cost_values");
				for (const value of r.message || []) {
					const row = frm.add_child("process_cost_values");
					Object.assign(row, value);
				}
				frm.refresh_field("process_cost_values");
			},
		});
	},
});
