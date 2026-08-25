frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		setTimeout(() => {
			essdee_yrp.contain_item_editor_matrix(frm, ["item_html"]);
		}, 0);
		// Base YRP mounts the generic stock editor. A new Stock Entry prepared
		// from Cut Panel Movement carries grouped rows in item_details rather
		// than __onload, so load that payload after the base refresh handler.
		if (frm.is_new() && frm.doc.cut_panel_movement && frm.doc.item_details && frm.itemEditor) {
			try {
				const items =
					typeof frm.doc.item_details === "string"
						? JSON.parse(frm.doc.item_details)
						: frm.doc.item_details;
				frm.itemEditor.load_data(items || []);
				frm.itemEditor.update_status();
			} catch (error) {
				frappe.msgprint(__("Unable to load Cut Panel Movement items. Please return and try again."));
			}
		}
		if (frm.doc.docstatus === 2) return;
		const supplier_key = frm.doc.to_supplier
			? "to_supplier"
			: frm.doc.from_supplier
				? "from_supplier"
				: null;
		if (!supplier_key) return;
		essdee_yrp.add_send_sms_button(frm, { supplier_key: supplier_key });
		essdee_yrp.add_send_whatsapp_button(frm, { supplier_key: supplier_key });
	},
});
