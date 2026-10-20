"""Desk print choices exposed by the web workspaces."""

from essdee_yrp.api.print import get_desk_print_formats, get_print_restriction


def get_document_print_formats(doc):
	if not doc or not doc.has_permission("print") or get_print_restriction(doc):
		return []
	return [{"label": name, "format": name} for name in get_desk_print_formats(doc.doctype)]
