"""Essdee-owned fields preserved by YRP's generic stock item pivot."""


ENTRY_FIELDS = {
	"Work Order Deliverables": (
		"fabric_reference_variant",
		"fabric_reference_allocations",
	),
	"Work Order Receivables": (
		"fabric_reference_variant",
		"fabric_reference_allocations",
	),
}


def get_entry_fields(parent_doctype, child_doctype=None):
	del child_doctype
	return ENTRY_FIELDS.get(parent_doctype, ())
