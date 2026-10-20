"""Coordinator-run report metadata backfill; never modifies operational UOM.

Export source blanks with scripts/purchase_round3_parity.py first. Review the
dry-run result, then execute apply_backfill(source_path=..., dry_run=False).
This is deliberately not registered in patches.txt: the coordinator owns site
schema changes and backfills. The report also works before this field exists.
"""

import json
from pathlib import Path

import frappe

FIELD = "custom_mrp_report_uom"


def retire_changed_uom(doc, method=None):
	"""Keep report provenance until a saved UOM change, independent of timestamps."""
	previous = doc.get_doc_before_save()
	old_items = {row.name: row for row in previous.get("items", [])} if previous else {}
	for row in doc.get("items", []):
		old = old_items.get(row.name)
		marker = old.get(FIELD) if old else None
		if marker:
			provenance = json.loads(marker)
			if row.uom != old.uom or row.uom != provenance["stored_uom"]:
				marker = None
		# The saved marker is authoritative: a stale client or copied row must
		# not restore provenance after a change away from and back to the UOM.
		if marker or row.get(FIELD):
			row.update({FIELD: marker})


def plan_backfill(source_rows, target_rows):
	"""Only annotate unchanged source identities, with explicit collision checks."""
	targets = {row["name"]: row for row in target_rows}
	updates, skipped = [], []
	seen = set()
	for source in source_rows:
		name = source["name"]
		if name in seen:
			raise ValueError(f"Duplicate source PO item: {name}")
		seen.add(name)
		if source["uom"] not in (None, ""):
			continue
		target = targets.get(name)
		if (
			not target
			or not target.get("is_yrp_managed")
			or any(
				str(source.get(a)) != str(target.get(b))
				for a, b in (
					("parent", "parent"),
					("item_variant", "item_code"),
					("creation", "creation"),
					("modified", "modified"),
				)
			)
		):
			skipped.append(dict(name=name, reason="Missing, native, or edited target row"))
			continue
		if target["uom"] == source["uom"]:
			continue
		marker = dict(source_uom=source["uom"], stored_uom=target["uom"], modified=str(target["modified"]))
		if existing := target.get(FIELD):
			if json.loads(existing) != marker:
				skipped.append(dict(name=name, reason="Conflicting existing provenance"))
			continue
		updates.append(dict(name=name, marker=json.dumps(marker, separators=(",", ":"))))
	return dict(updates=updates, skipped=skipped)


def apply_backfill(source_path, dry_run=True):
	"""Default to planning; explicit application creates one hidden report field."""
	frappe.only_for("System Manager")
	from essdee_yrp.migration.config import get_migration_settings

	payload = json.loads(Path(source_path).read_text())
	if payload.get("source_site") != get_migration_settings().source_site:
		raise ValueError("UOM provenance must come from the configured migration source")
	if payload.get("doctype") != "Purchase Order Item":
		raise ValueError("Expected a Purchase Order Item provenance export")
	source_rows = payload["rows"]
	if not isinstance(source_rows, list) or not source_rows:
		raise ValueError("Expected a nonempty source row list")
	if dry_run is not True and dry_run is not False:
		raise ValueError("dry_run must be a JSON boolean")
	if not dry_run:
		from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

		create_custom_fields(
			{
				"Purchase Order Item": [
					dict(
						fieldname=FIELD,
						label="MRP report UOM provenance",
						fieldtype="Small Text",
						hidden=1,
						read_only=1,
						no_copy=1,
						allow_on_submit=1,
						description="Original blank UOM and migration fallback for report display only.",
					)
				]
			}
		)
	item, po = frappe.qb.DocType("Purchase Order Item"), frappe.qb.DocType("Purchase Order")
	query = (
		frappe.qb.from_(item)
		.join(po)
		.on(item.parent == po.name)
		.select(
			item.name, item.parent, item.item_code, item.creation, item.modified, item.uom, po.is_yrp_managed
		)
		.where(item.name.isin([row["name"] for row in source_rows]))
	)
	if frappe.db.has_column("Purchase Order Item", FIELD):
		query = query.select(item[FIELD])
	if not dry_run:
		query = query.for_update()
	plan = plan_backfill(source_rows, query.run(as_dict=True))
	if not dry_run:
		if plan["skipped"]:
			raise ValueError(f"Review skipped source identities before applying: {plan['skipped']}")
		for row in plan["updates"]:
			frappe.db.set_value(
				"Purchase Order Item", row["name"], FIELD, row["marker"], update_modified=False
			)
	return plan
