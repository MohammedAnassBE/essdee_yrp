"""Desk print choices exposed by the web workspaces."""

import frappe

from essdee_yrp.api.print import get_desk_print_formats, get_print_restriction


def get_document_print_formats(doc):
	if not doc or not frappe.has_permission(doc.doctype, "print", doc=doc) or get_print_restriction(doc):
		return []
	return [{"label": name, "format": name} for name in get_desk_print_formats(doc.doctype)]
