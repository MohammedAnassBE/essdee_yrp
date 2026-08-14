// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("MRP Data Migration", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.dashboard.set_headline(__("Save this run to enable schema analysis."));
			return;
		}

		frm.add_custom_button(
			__("Analyse Schema"),
			() => {
				frm.call({
					doc: frm.doc,
					method: "analyse",
					freeze: true,
					freeze_message: __("Analysing repository schemas..."),
				}).then(() => frm.reload_doc());
			},
			__("Migration"),
		);

		const actions = [
			[__("Dry Run"), "dry_run", ["Ready", "Dry Run Complete", "Failed"]],
			[__("Migrate"), "migrate", ["Dry Run Complete", "Failed"]],
			[__("Verify"), "verify", ["Completed", "Verified"]],
		];
		for (const [label, method, statuses] of actions) {
			const button = frm.add_custom_button(
				label,
				() =>
					frm.call({ doc: frm.doc, method }).then(() => {
						frappe.show_alert({ message: __("Migration job queued."), indicator: "blue" });
						frm.reload_doc();
					}),
				__("Migration"),
			);
			if (!statuses.includes(frm.doc.status) || frm.doc.blocker_count) {
				button.prop("disabled", true);
			}
		}
	},
});
