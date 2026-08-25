frappe.pages["sewing-details"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sewing Details"),
		single_column: true,
	});
};

frappe.pages["sewing-details"].refresh = function (wrapper) {
	if (wrapper.sewing_plan) {
		wrapper.sewing_plan.app.unmount();
	}
	wrapper.sewing_plan = new frappe.production.ui.SewingPlan(wrapper);
};
