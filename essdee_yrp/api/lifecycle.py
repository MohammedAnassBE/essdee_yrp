# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Document lifecycle endpoints for the separate web UI.

The REST resource update path locks a parent before it calls ``doc.save()``.
Calling the controller's public lifecycle method instead is required for
DocTypes such as Essdee's GRN controller that deliberately acquire a broader
business lock before Frappe locks the voucher parent.
"""

import frappe


def _load_for_lifecycle(doctype, name, modified=None):
	doc = frappe.get_doc(doctype, name)
	# Preserve the web form's stale-document contract. check_if_latest compares
	# this client-observed timestamp with a current locked database document.
	if modified:
		doc.modified = modified
	return doc


def _safe_result(doc):
	doc.apply_fieldlevel_read_permissions()
	return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def submit_document(doctype, name, modified=None):
	doc = _load_for_lifecycle(doctype, name, modified)
	doc.submit()
	return _safe_result(doc)


@frappe.whitelist(methods=["POST"])
def cancel_document(doctype, name, modified=None):
	doc = _load_for_lifecycle(doctype, name, modified)
	doc.cancel()
	return _safe_result(doc)
