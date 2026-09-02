// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP IPD Settings", {
	setup(frm) {
		frm.set_query("default_knitting_output_colour", () => ({
			filters: { attribute_name: "Colour" },
		}));
	},
});
