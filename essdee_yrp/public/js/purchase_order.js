frappe.ui.form.on("YRP Purchase Order", {
	refresh(frm) {
		if (frm.fields_dict.sd_lot) {
			frm.set_df_property("sd_lot", "read_only", frm.doc.docstatus === 1 ? 1 : 0);
		}
		if (frm.doc.docstatus === 1 && frm.doc.open_status === "Open") {
			frm.add_custom_button(__("Manage Linked Lots"), () => manage_linked_lots(frm));
		}
		essdee_yrp.add_send_sms_button(frm, {
			hidden_statuses: ["Closed", "Cancelled", "Partially Cancelled"],
		});
		essdee_yrp.add_send_whatsapp_button(frm, {
			hidden_statuses: ["Closed", "Cancelled", "Partially Cancelled"],
		});
	},
});

function manage_linked_lots(frm) {
	frappe.call({
		method: "essdee_yrp.purchase_order_lots.get_purchase_order_lots",
		args: { purchase_order: frm.doc.name },
		callback(r) {
			const current = r.message || [];
			const dialog = new frappe.ui.Dialog({
				title: __("Manage Linked Lots"),
				fields: [
					{
						fieldname: "lots",
						fieldtype: "Table MultiSelect",
						label: __("Lots"),
						options: "SD YRP Lot MultiSelect",
						get_data(txt) {
							return frappe.db.get_link_options("SD YRP Lot", txt);
						},
					},
					{
						fieldname: "comment",
						fieldtype: "Small Text",
						label: __("Reason"),
						reqd: 1,
					},
				],
				primary_action_label: __("Save"),
				primary_action(values) {
					const desired = (values.lots || []).map((row) => row.lot);
					const addLots = desired.filter((lot) => !current.includes(lot));
					const removeLots = current.filter((lot) => !desired.includes(lot));
					if (!addLots.length && !removeLots.length) {
						dialog.hide();
						return;
					}
					frappe.call({
						method: "essdee_yrp.purchase_order_lots.update_po_lot_links",
						args: {
							doc_name: frm.doc.name,
							add_lots: addLots,
							remove_lots: removeLots,
							comment: values.comment,
						},
						freeze: true,
						callback() {
							dialog.hide();
							frm.reload_doc();
						},
					});
				},
			});
			dialog.fields_dict.lots.df.data = current.map((lot) => ({ lot }));
			dialog.show();
			dialog.fields_dict.lots.grid.refresh();
		},
	});
}
