frappe.ui.form.on("Supplier", {
	refresh(frm) {
		const supplier = frm.doc.name;
		const request_token = Symbol();
		frm.supplier_warehouse_request_token = request_token;
		clear_warehouse_buttons(frm);
		if (frm.is_new()) return;
		frappe
			.call("essdee_yrp.api.supplier_warehouse.get_supplier_warehouse_context", {
				supplier,
			})
			.then(({ message }) => {
				if (
					frm.doc.name !== supplier ||
					frm.supplier_warehouse_request_token !== request_token
				) {
					return;
				}
				clear_warehouse_buttons(frm);
				if (message.warehouse) {
					frm.add_custom_button(__("View Warehouse"), () =>
						frappe.set_route("Form", "Warehouse", message.warehouse)
					);
					return;
				}
				if (!message.warehouse_exists && frappe.model.can_create("Warehouse")) {
					frm.add_custom_button(__("Create Warehouse"), () =>
						open_new_warehouse(message.defaults)
					);
				}
			});
	},
});

function clear_warehouse_buttons(frm) {
	frm.remove_custom_button(__("Create Warehouse"));
	frm.remove_custom_button(__("View Warehouse"));
}

function open_new_warehouse(defaults) {
	return frappe.model.with_doctype("Warehouse").then(() => {
		const company_field = frappe.meta.get_docfield("Warehouse", "company");
		const company =
			defaults.company ||
			frappe.model.get_default_value(company_field, { doctype: "Warehouse" });
		if (company) {
			frappe.new_doc("Warehouse", defaults);
			return;
		}
		frappe.prompt(
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				reqd: 1,
			},
			({ company }) => frappe.new_doc("Warehouse", { ...defaults, company }),
			__("Select Company"),
			__("Create Warehouse")
		);
	});
}
