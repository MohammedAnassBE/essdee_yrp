frappe.ui.form.on("Goods Received Note", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;
		essdee_yrp.add_send_sms_button(frm);
		essdee_yrp.add_send_whatsapp_button(frm);
		if (
			frm.doc.docstatus === 1
			&& frm.doc.against === "Work Order"
			&& !frm.doc.mrp_stock_entry_created
		) {
			frm.add_custom_button(__("Create Stock in MRP"), () => {
				frappe.confirm(
					__(
						"Transfer this GRN's finished-cloth stock to MRP? "
						+ "This creates a Material Issue in YRP and a Material Receipt in MRP."
					),
					() => frappe.call({
						method: "essdee_yrp.api.mrp_stock_transfer.create_mrp_stock",
						args: { grn_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Creating MRP Stock"),
						callback: (r) => {
							if (r.message?.ok) {
								frappe.msgprint({
									title: __("Transferred"),
									indicator: "green",
									message: __("MRP Stock Entry {0}", [r.message.mrp_stock_entry]),
								});
								frm.reload_doc();
							}
						},
					})
				);
			});
		}
	},
});
