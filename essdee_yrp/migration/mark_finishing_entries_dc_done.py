"""One-off: mark existing Ironing Excess and Old Lot entries as already sent by DC.

Finishing Plan ``ironing_excess_list`` and ``lot_transfer_list`` used to store
``{name: "dd-mm-YYYY HH:MM:SS"}``. Entries now store ``{name: {"datetime", "dc"}}``
and /web offers Create DC for entries whose ``dc`` is empty. Every entry that
exists before the rollout gets ``dc = "existing"`` so no button shows for it.
Entries already in the new shape are left untouched, so reruns change nothing.

Dry run (default, no writes):
	bench --site SITE execute essdee_yrp.migration.mark_finishing_entries_dc_done.run
Apply:
	bench --site SITE execute essdee_yrp.migration.mark_finishing_entries_dc_done.run --kwargs "{'apply': 1}"
"""

import frappe

from essdee_yrp.finishing.source_entries import EXISTING_DC, SOURCE_LISTS, get_raw_entries, normalize_entry

DOCTYPE = "SD YRP Finishing Plan"


def run(apply=0, verbose=1):
	fields = list(SOURCE_LISTS)
	plans = frappe.get_all(DOCTYPE, fields=["name", *fields], order_by="name")
	counts = {"plans": len(plans), "plans_changed": 0, "errors": []}
	for field in fields:
		counts[f"{field}_converted"] = 0
		counts[f"{field}_already_new"] = 0
	for plan in plans:
		try:
			updates = get_plan_updates(plan, counts)
		except Exception as error:
			counts["errors"].append({"plan": plan.name, "error": repr(error)})
			continue
		if not updates:
			continue
		counts["plans_changed"] += 1
		if apply:
			frappe.db.set_value(DOCTYPE, plan.name, updates, update_modified=False)
	if apply:
		frappe.db.commit()
	counts["applied"] = bool(apply)
	if verbose:
		print(counts)
	return counts


def get_plan_updates(plan, counts) -> dict:
	updates = {}
	for field in SOURCE_LISTS:
		entries = get_raw_entries(plan.get(field))
		changed = False
		for name, value in entries.items():
			if isinstance(value, dict):
				counts[f"{field}_already_new"] += 1
				continue
			entries[name] = {**normalize_entry(value), "dc": EXISTING_DC}
			counts[f"{field}_converted"] += 1
			changed = True
		if changed:
			updates[field] = frappe.as_json(entries)
	return updates
