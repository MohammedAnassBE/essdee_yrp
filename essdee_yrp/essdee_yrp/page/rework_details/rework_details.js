frappe.pages["rework-details"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Rework Details"),
		single_column: true,
	});
};

frappe.pages["rework-details"].refresh = function (wrapper) {
	if (wrapper.rework_page) {
		wrapper.rework_page.app.unmount();
	}
	wrapper.rework_page = new frappe.production.ui.ReworkPage(wrapper);
};
