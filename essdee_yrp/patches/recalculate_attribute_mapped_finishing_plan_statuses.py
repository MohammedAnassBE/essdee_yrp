import frappe
from frappe.utils import now

from essdee_yrp.finishing.status import AUTO_FP_STATUSES, compute_received_status


def execute():
	candidates = get_candidate_plans()
	result = {
		"total": len(candidates),
		"updated": 0,
		"unchanged": 0,
		"skipped": 0,
	}

	for candidate in candidates:
		current_status = candidate.fp_status or ""
		if current_status not in AUTO_FP_STATUSES:
			result["skipped"] += 1
			continue

		finishing_plan = frappe.get_doc("SD YRP Finishing Plan", candidate.name)
		new_status = compute_received_status(finishing_plan) or "Planned"
		if new_status == current_status:
			result["unchanged"] += 1
			continue

		frappe.db.set_value(
			"SD YRP Finishing Plan",
			candidate.name,
			{"fp_status": new_status, "fp_status_since": now()},
			update_modified=False,
		)
		result["updated"] += 1

	print(
		"Attribute-mapped Finishing Plan status recalculation: "
		f"updated={result['updated']}, unchanged={result['unchanged']}, "
		f"skipped={result['skipped']}, total={result['total']}"
	)
	return result


def get_candidate_plans():
	return frappe.db.sql(
		"""
			SELECT fp.name, fp.fp_status
			FROM `tabSD YRP Finishing Plan` fp
			INNER JOIN `tabYRP Item Production Detail` ipd
				ON ipd.name = fp.production_detail
			WHERE
				fp.docstatus < 2
				AND (
					COALESCE(ipd.based_on_other_attribute_mapping, 0) = 1
					OR ipd.packing_mode = 'Size Wise Packing'
				)
			ORDER BY fp.name
		""",
		as_dict=True,
	)
