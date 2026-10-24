"""Desk print choices exposed by the web workspaces."""

from contextlib import contextmanager

import frappe

from essdee_yrp.api.print import get_desk_print_formats, get_print_restriction


@contextmanager
def print_format_scope():
	"""Read each doctype's Desk print formats once while one payload is built; nested scopes join the outer one."""
	if getattr(frappe.local, "web_print_formats", None) is not None:
		yield
		return
	frappe.local.web_print_formats = {}
	try:
		yield
	finally:
		frappe.local.web_print_formats = None


def get_document_print_formats(doc):
	if not doc or not frappe.has_permission(doc.doctype, "print", doc=doc) or get_print_restriction(doc):
		return []
	scoped = getattr(frappe.local, "web_print_formats", None)
	if scoped is None:
		names = get_desk_print_formats(doc.doctype)
	else:
		if doc.doctype not in scoped:
			scoped[doc.doctype] = get_desk_print_formats(doc.doctype)
		names = scoped[doc.doctype]
	return [{"label": name, "format": name} for name in names]
