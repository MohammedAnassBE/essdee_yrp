// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP MRP Data Migration", {
	async refresh(frm) {
		frm.set_df_property("allow_missing_source_blobs", "read_only", !frm.is_new());
		if (frm.is_new()) {
			const { message } = await frappe.call({
				method:
					"essdee_yrp.essdee_yrp.doctype.sd_yrp_mrp_data_migration.sd_yrp_mrp_data_migration.get_connection_defaults",
			});
			for (const [fieldname, value] of Object.entries(message || {})) {
				await frm.set_value(fieldname, value);
			}
			frm.dashboard.set_headline(__("Save this run to enable schema analysis."));
			return;
		}

		if (!["Analysing", "Queued", "Running"].includes(frm.doc.status)) {
			frm.add_custom_button(
				__("Analyse Schema"),
				() => {
					run_migration_action(frm, "analyse", {
						freeze: true,
						freeze_message: __("Analysing repository schemas..."),
					}).then(() => frm.reload_doc());
				},
				__("Migration"),
			);
		}

		const actions = [
			[__("Dry Run"), "dry_run", ["Ready", "Dry Run Complete", "Failed"]],
			[__("Migrate"), "migrate", ["Dry Run Complete", "Failed"]],
			[__("Verify"), "verify", ["Completed", "Verified", "Verified With Source Gaps", "Failed"]],
		];
		for (const [label, method, statuses] of actions) {
			if (!statuses.includes(frm.doc.status) || frm.doc.blocker_count) {
				continue;
			}
			if (method === "migrate" && frm.doc.status === "Failed" && frm.doc.last_action !== "Migrate") {
				continue;
			}
			if (method === "verify" && frm.doc.status === "Failed" && frm.doc.last_action !== "Verify") {
				continue;
			}
			frm.add_custom_button(
				label,
				() =>
					run_migration_action(frm, method).then(() => {
						frappe.show_alert({ message: __("Migration job queued."), indicator: "blue" });
						frm.reload_doc();
				}),
				__("Migration"),
			);
		}
	},
});

function run_migration_action(frm, method, options = {}) {
	// Reports can exceed request-size limits. Load the saved audit on the server;
	// its controller remains responsible for permissions, locks and state gates.
	return frappe.call({
		...options,
		method: "run_doc_method",
		args: { dt: frm.doctype, dn: frm.doc.name, method },
	});
}
