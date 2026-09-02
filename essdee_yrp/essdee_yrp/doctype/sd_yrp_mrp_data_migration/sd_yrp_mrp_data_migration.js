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
					frm.call({
						doc: frm.doc,
						method: "analyse",
						freeze: true,
						freeze_message: __("Analysing repository schemas..."),
					}).then(() => frm.reload_doc());
				},
				__("Migration"),
			);
		}

		if (
			frm.doc.status === "Dry Run Complete" ||
			(frm.doc.status === "Failed" && frm.doc.last_action === "Reset Target")
		) {
			frm.add_custom_button(
				__("Reset Target Data"),
				async () => {
					const { message: preview } = await frm.call({
						doc: frm.doc,
						method: "get_reset_preview",
						freeze: true,
						freeze_message: __("Calculating the exact target reset scope..."),
					});
					if (!preview?.source_maintenance_mode) {
						frappe.msgprint(__("Put source site {0} in maintenance mode first.", [preview.source_site]));
						return;
					}
					if (!preview?.server_reset_enabled) {
						frappe.msgprint(__("The one-time server reset acknowledgement is not enabled."));
						return;
					}
					const expected = `RESET ${frm.doc.target_site}`;
					frappe.prompt(
						[
							{
								fieldname: "confirmation",
								fieldtype: "Data",
								label: __("Type {0}", [expected]),
								description: __(
									"Reviewed scope: {0} parent rows, {1} child rows, {2} files, {3} generated supplier warehouses, and {4} reset-generated deletion audit rows. No naming-series counter is deleted; all {5} existing target counters are preserved and verified exactly. {6} Single/configuration DocTypes are preserved.",
									[
										preview.parent_rows,
										preview.child_rows,
										preview.file_rows,
										preview.generated_supplier_warehouses,
										preview.reset_generated_audit_rows,
										preview.preserved_naming_series_counters,
										preview.preserved_single_doctypes.length,
									],
								),
								reqd: 1,
							},
						],
						(values) =>
							frm
								.call({
									doc: frm.doc,
									method: "reset_target",
									args: { confirmation: values.confirmation },
								})
								.then(() => {
									frappe.show_alert({
										message: __("Target reset job queued."),
										indicator: "orange",
									});
									frm.reload_doc();
								}),
						__("Reset migration-owned data on {0}?", [frm.doc.target_site]),
						__("Queue Reset"),
					);
				},
				__("Migration"),
			);
		}

		const actions = [
			[__("Dry Run"), "dry_run", ["Ready", "Dry Run Complete", "Failed"]],
			[__("Migrate"), "migrate", ["Reset Complete", "Failed"]],
			[__("Verify"), "verify", ["Completed", "Verified"]],
		];
		for (const [label, method, statuses] of actions) {
			if (!statuses.includes(frm.doc.status) || frm.doc.blocker_count) {
				continue;
			}
			if (method === "migrate" && frm.doc.status === "Failed" && frm.doc.last_action !== "Migrate") {
				continue;
			}
			frm.add_custom_button(
				label,
				() =>
					frm.call({ doc: frm.doc, method }).then(() => {
						frappe.show_alert({ message: __("Migration job queued."), indicator: "blue" });
						frm.reload_doc();
				}),
				__("Migration"),
			);
		}
	},
});
