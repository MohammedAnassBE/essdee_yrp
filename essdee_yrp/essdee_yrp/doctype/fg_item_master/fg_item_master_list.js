frappe.listview_settings["FG Item Master"] = {
	onload(listview) {
		const method = "essdee_yrp.essdee_yrp.doctype.fg_item_master.fg_item_master.sync_fg_items";
		listview.page.add_action_item(__("Create / Update YRP Items"), () => {
			listview.call_for_selected_items(method, { rename: 0 });
		});
		listview.page.add_action_item(__("Rename YRP Items"), () => {
			listview.call_for_selected_items(method, { rename: 1 });
		});
	},
};
