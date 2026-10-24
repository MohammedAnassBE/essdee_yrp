function setup_purchase_order_approval_actions(frm) {
	if (
		!frm.doc.is_yrp_managed ||
		frm.doc.docstatus !== 0 ||
		frm.doc.status !== "Pending Approval" ||
		frm.is_new()
	) {
		return;
	}

	const isSystemManager = frappe.user.has_role("System Manager");
	if (!isSystemManager) {
		frm.page.btn_primary.hide();
	}

	frappe.call({
		method: "essdee_yrp.purchase_order_approval.get_purchase_order_approval_state",
		args: { name: frm.doc.name },
		callback(response) {
			const state = response.message || {};
			if (
				frappe.perm.has_perm("Purchase Order", 0, "create") &&
				!state.live_request
			) {
				frm.add_custom_button(__("Send Request"), () => {
					frappe.call({
						method: "essdee_yrp.purchase_order_approval.send_purchase_order_request",
						args: { name: frm.doc.name },
						freeze: true,
						callback(sendResponse) {
							const result = sendResponse.message || {};
							if (result.status === "Error") {
								frappe.msgprint(result.error || __("Unable to send the Telegram request."));
							}
							frm.reload_doc();
						},
					});
				});
			}

			if (!isSystemManager) {
				return;
			}
			frm.add_custom_button(__("Approve PO"), () => {
				frappe.confirm(__("Approve and submit this Purchase Order?"), () => {
					frappe.call({
						method: "essdee_yrp.purchase_order_approval.approve_purchase_order",
						args: { name: frm.doc.name },
						freeze: true,
						callback() { frm.reload_doc(); },
					});
				});
			});
			frm.add_custom_button(__("Reject PO"), () => {
				frappe.confirm(__("Reject this Purchase Order request?"), () => {
					frappe.call({
						method: "essdee_yrp.purchase_order_approval.reject_purchase_order",
						args: { name: frm.doc.name },
						freeze: true,
						callback() { frm.reload_doc(); },
					});
				});
			});
		},
	});
}

/** Replace Set Target Warehouse with the delivery location's only enabled Warehouse, else clear it. */
async function fill_purchase_order_delivery_warehouse(frm) {
	if (!frm.doc.is_yrp_managed) return;
	const location = frm.doc.default_delivery_location;
	let warehouse = "";
	if (location) {
		const response = await frappe.call({
			method: "essdee_yrp.api.supplier_warehouse.get_single_location_options",
			args: { supplier: location },
		});
		if (frm.doc.default_delivery_location !== location) return;
		warehouse = response?.message?.warehouse || "";
	}
	if ((frm.doc.set_warehouse || "") !== warehouse) await frm.set_value("set_warehouse", warehouse);
}

frappe.ui.form.on("Purchase Order", {
	default_delivery_location(frm) {
		return fill_purchase_order_delivery_warehouse(frm);
	},

	refresh(frm) {
		if (!frm.doc.is_yrp_managed) {
			return;
		}
		setup_purchase_order_approval_actions(frm);
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
