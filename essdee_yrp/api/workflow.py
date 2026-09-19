import frappe
from frappe.model.workflow import get_workflow_name


@frappe.whitelist()
def get_active_workflow(doctype):
	"""Return the active workflow contract for a readable DocType.

	The web UI uses this server-authoritative result to choose between Frappe
	workflow transitions and the ordinary Submit/Cancel lifecycle.  Looking only
	at the presence of a workflow-state Custom Field is insufficient because that
	field can remain after a workflow is disabled.
	"""
	if not doctype:
		return None

	frappe.has_permission(doctype, "read", throw=True)
	workflow_name = get_workflow_name(doctype)
	if not workflow_name:
		return None

	workflow = frappe.get_cached_doc("Workflow", workflow_name)
	return {
		"name": workflow.name,
		"state_field": workflow.workflow_state_field,
		"states": [state.state for state in workflow.states],
	}
