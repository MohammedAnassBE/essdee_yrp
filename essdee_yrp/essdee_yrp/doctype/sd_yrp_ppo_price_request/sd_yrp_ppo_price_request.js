// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP PPO Price Request", {
	refresh(frm) {
		if (frm.doc.status !== "Pending" || !frappe.user_roles.includes("System Manager")) {
			return;
		}
		for (const [label, method, indicator, resultLabel] of [
			["Approve", "approve_ppo_price_request", "green", "approved"],
			["Reject", "reject_ppo_price_request", "red", "rejected"],
		]) {
			frm.add_custom_button(
				__(label),
				() => {
					frappe.call({
						method: `essdee_yrp.essdee_yrp.doctype.sd_yrp_ppo_price_request.sd_yrp_ppo_price_request.${method}`,
						args: { name: frm.doc.name },
						callback() {
							frm.reload_doc();
							frappe.show_alert({
								message: __(`Price change ${resultLabel}`),
								indicator,
							});
						},
					});
				},
				__("Action"),
			);
		}
	},
});
