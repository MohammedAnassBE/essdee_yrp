frappe.listview_settings["YRP Production Order"] = {
	add_fields: ["price_approval_status", "status"],
	has_indicator_for_draft: true,
	onload(listview) {
		if (!frappe.model.can_create("Purchase Order")) return;
		listview.page.add_actions_menu_item(__("Create Purchase Order"), () => {
			frappe.call({
				method: "essdee_yrp.purchase_order_against.make_purchase_order",
				args: { production_orders: listview.get_checked_items(true) },
				freeze: true,
				callback: (response) => {
					const purchase_order = frappe.model.sync(response.message)[0];
					frappe.set_route("Form", purchase_order.doctype, purchase_order.name);
				},
			});
		});
	},
	get_indicator(doc) {
		if (doc.price_approval_status === "Pending Approval") {
			return [
				__("Pending Approval"),
				"orange",
				"price_approval_status,=,Pending Approval",
			];
		}
		if (doc.docstatus === 0 && doc.status === "PPO Request") {
			return [__("PPO Request"), "orange", "status,=,PPO Request"];
		}
		if (doc.docstatus === 1 && doc.status) {
			const status_colors = {
				Open: "blue",
				"Pending Request": "orange",
				"Item Changed": "yellow",
				"Not Processed": "red",
				Closed: "green",
			};
			return [
				__(doc.status),
				status_colors[doc.status] || "blue",
				`status,=,${doc.status}`,
			];
		}
		return {
			0: [__("Draft"), "red", "docstatus,=,0"],
			1: [__("Submitted"), "blue", "docstatus,=,1"],
			2: [__("Cancelled"), "gray", "docstatus,=,2"],
		}[doc.docstatus];
	},
};
