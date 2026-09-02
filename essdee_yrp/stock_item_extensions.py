"""Essdee-owned fields preserved by YRP's generic stock item pivot."""


ENTRY_FIELDS = {
	'YRP Stock Entry': (
		# The base stock editor owns the generic item/dimension pivot.  These
		# fields are Essdee trace data and must survive its group -> ungroup
		# round-trip when a Cut Panel Movement creates a Stock Entry.
		"set_combination",
	),
	'YRP Work Order Deliverables': (
		"fabric_reference_variant",
		"fabric_reference_allocations",
	),
	'YRP Work Order Receivables': (
		"fabric_reference_variant",
		"fabric_reference_allocations",
	),
}


def get_entry_fields(parent_doctype, child_doctype=None):
	del child_doctype
	return ENTRY_FIELDS.get(parent_doctype, ())
