// Copyright (c) 2026, Essdee and contributors

frappe.ui.form.on("FG Item Master", {
	setup(frm) {
		frm.set_query("attribute_value", "sizes", () => ({
			filters: { attribute_name: "Size" },
		}));
	},
	refresh(frm) {
		if (frm.is_new() || !frm.has_perm("write")) return;
		frm.page.add_menu_item(__("Create / Update YRP Item"), () => {
			frappe.call({
				method: "essdee_yrp.essdee_yrp.doctype.fg_item_master.fg_item_master.sync_fg_item",
				args: { name: frm.doc.name },
				freeze: true,
				callback(response) {
					if (response.message) frappe.set_route("Form", "Item", response.message);
				},
			});
		});
		if (frm.doc.item) {
			frm.page.add_menu_item(__("Rename YRP Item"), () => {
				frappe.call({
					method: "essdee_yrp.essdee_yrp.doctype.fg_item_master.fg_item_master.sync_fg_item",
					args: { name: frm.doc.name, rename: 1 },
					freeze: true,
					callback: () => frm.reload_doc(),
				});
			});
		}
	},
	size_range(frm) {
		if (!frm.doc.size_range) return frm.set_value("sizes", []);
		frappe.db.get_doc("FG Item Size Range", frm.doc.size_range).then((size_range) => {
			frm.set_value("sizes", (size_range.sizes || []).map((row) => ({
				attribute_value: row.attribute_value,
			})));
		});
	},
});
