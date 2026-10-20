frappe.pages["audit-pending-finishing-plans"].on_page_load = function (wrapper) {
	wrapper.audit_pending_page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Audit Pending Finishing Plans"),
		single_column: true,
	})
	wrapper.audit_pending_mount = document.createElement("div")
	wrapper.audit_pending_page.main.append(wrapper.audit_pending_mount)
}

frappe.pages["audit-pending-finishing-plans"].refresh = async function (wrapper) {
	const generation = (wrapper.audit_pending_generation || 0) + 1
	wrapper.audit_pending_generation = generation
	await frappe.require("audit_pending_finishing_plans.bundle.js")
	if (generation !== wrapper.audit_pending_generation) return
	wrapper.audit_pending?.app.unmount()
	wrapper.audit_pending = new frappe.production.ui.AuditPendingFinishingPlans(wrapper.audit_pending_mount)
}
