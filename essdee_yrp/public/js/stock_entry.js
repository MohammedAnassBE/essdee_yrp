frappe.ui.form.on("YRP Stock Entry", {
	refresh(frm) {
		exclude_stock_entry_cut_panel_movement_from_cancel_all(frm);
		allow_positive_material_receipt_rates(frm);
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

function allow_positive_material_receipt_rates(frm) {
	const wrapper = frm.fields_dict.item_html?.wrapper;
	if (!wrapper) return;

	const normalize = () => {
		for (const label of wrapper.querySelectorAll(".new-item-form label")) {
			if (label.textContent.trim() !== __("Rate")) continue;
			const input = label.parentElement?.querySelector('input[type="number"]');
			if (input && input.step !== "any") input.step = "any";
		}
	};

	frm.__essdee_stock_rate_observer?.disconnect();
	frm.__essdee_stock_rate_observer = new MutationObserver(normalize);
	frm.__essdee_stock_rate_observer.observe(wrapper, { childList: true, subtree: true });
	normalize();
}

function exclude_stock_entry_cut_panel_movement_from_cancel_all(frm) {
	if (frm.doc.docstatus !== 1 || !frm.doc.cut_panel_movement) return;
	const ignored = new Set(frm.ignore_doctypes_on_cancel_all || []);
	ignored.add("SD YRP Cut Panel Movement");
	frm.ignore_doctypes_on_cancel_all = [...ignored];
}
