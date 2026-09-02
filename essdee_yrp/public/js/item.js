frappe.ui.form.on("YRP Item", {
	setup(frm) {
		frm.set_query("yarn_item", "yarn_ratio_details", () => ({
			filters: {
				disabled: 0,
				is_cloth_item: 0,
			},
		}));
	},

	refresh(frm) {
		update_yarn_ratio_total(frm);
	},

	validate(frm) {
		if (!frm.doc.is_cloth_item) {
			return;
		}
		const rows = frm.doc.yarn_ratio_details || [];
		const total = rows.reduce((sum, row) => sum + Number(row.ratio || 0), 0);
		if (!rows.length) {
			frappe.throw(__("Add at least one Yarn Ratio row for a Cloth Item."));
		}
		if (Math.abs(total - 100) > 0.001) {
			frappe.throw(
				__("Yarn Ratio total must be exactly 100%. Current total is {0}%.", [
					format_yarn_ratio(total),
				])
			);
		}
	},
});

frappe.ui.form.on("SD YRP Item Yarn Ratio", {
	yarn_ratio_details_add(frm) {
		update_yarn_ratio_total(frm);
	},
	yarn_ratio_details_remove(frm) {
		update_yarn_ratio_total(frm);
	},
	ratio(frm) {
		update_yarn_ratio_total(frm);
	},
});

function format_yarn_ratio(value) {
	return Number(value || 0).toLocaleString(
		undefined,
		{ minimumFractionDigits: 0, maximumFractionDigits: 3 }
	);
}

function update_yarn_ratio_total(frm) {
	if (!frm.fields_dict.yarn_ratio_details) {
		return;
	}
	const rows = frm.doc.yarn_ratio_details || [];
	const total = rows.reduce((sum, row) => sum + Number(row.ratio || 0), 0);
	frm.set_df_property(
		"yarn_ratio_details",
		"description",
		__("Yarn composition for this cloth item. Current total: {0}% — required total: 100%.", [
			format_yarn_ratio(total),
		])
	);
}
