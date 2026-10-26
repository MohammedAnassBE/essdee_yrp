// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP GRN Rework Item", {
	refresh(frm) {
		const has_entries =
			(frm.doc.grn_reworked_item_details || []).length ||
			(frm.doc.grn_rejected_item_details || []).length;
		if (frm.is_new() || !has_entries || !frm.perm[0]?.write) return;
		frm.add_custom_button(__("Revert"), () => {
			frappe.confirm(__("Revert all rework entries of {0}?", [frm.doc.name]), () => {
				frappe.call({
					method: "essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item.revert_reworked_item",
					args: { docname: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				});
			});
		});
	},
});
