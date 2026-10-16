# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Essdee Cutting Plan adapter for actual fabric substitutions."""

import frappe
from essdee_yrp.cutting.cloth_substitution import (
	expand_cutting_rows,
	split_required_weight as _split_required_weight,
)



@frappe.whitelist()
def get_cloth1(cutting_plan):
	"""Compatibility route to the single migrated Generate implementation."""
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		get_cloth1 as generate_cloth,
	)

	return generate_cloth(cutting_plan)
