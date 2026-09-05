import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	# Process fields are fixture-owned. This patch retains only the property/data
	# migration that cannot be represented by a Custom Field fixture.
	make_property_setter(
		"Process",
		"value_change_attributes",
		"depends_on",
		(
			"eval:doc.is_group != 1 && "
			"(!doc.is_cloth_process || !doc.is_item_conversion)"
		),
		"Data",
	)
	sync_existing_process_configuration()


def sync_existing_process_configuration():
	"""Idempotent data migration, also called after fixture synchronization."""
	meta = frappe.get_meta("Process")
	if not all(
		meta.has_field(fieldname)
		for fieldname in (
			"conversion_input_attributes",
			"conversion_output_attributes",
		)
	):
		return
	_mark_existing_cloth_processes()
	_backfill_from_existing_process_mappings()


def _mark_existing_cloth_processes():
	"""Mark Process masters already used by cloth IPDs as cloth processes.

	The flag was introduced after those IPDs were authored.  Runtime behaviour
	can then stay configuration-driven without breaking their existing routes.
	"""
	if not (
		frappe.db.exists("DocType", "Item Production Detail")
		and frappe.db.exists("DocType", "IPD Fabric Process")
		and frappe.get_meta("Process").has_field("is_cloth_process")
	):
		return

	processes = {
		row.fabric_process
		for row in frappe.db.sql(
			"""
			select distinct process.fabric_process
			from `tabIPD Fabric Process` process
			inner join `tabItem Production Detail` ipd on ipd.name = process.parent
			where process.parenttype = 'Item Production Detail'
				and ipd.is_cloth_item = 1
				and process.fabric_process is not null
			""",
			as_dict=True,
		)
		if row.fabric_process
	}
	for fieldname in ("knitting_process", "dyeing_process", "compacting_process"):
		if not frappe.get_meta("Item Production Detail").has_field(fieldname):
			continue
		processes.update(
			value
			for value in frappe.get_all(
				"Item Production Detail",
				filters={"is_cloth_item": 1, fieldname: ["is", "set"]},
				pluck=fieldname,
			)
			if value
		)

	for process_name in processes:
		if (
			frappe.db.exists("Process", process_name)
			and not frappe.db.get_value(
				"Process", process_name, "is_cloth_process"
			)
		):
			frappe.db.set_value(
				"Process",
				process_name,
				"is_cloth_process",
				1,
				update_modified=False,
			)
			frappe.clear_document_cache("Process", process_name)


def _backfill_from_existing_process_mappings():
	"""Seed the new Process contract from mappings users already authored.

	This is deliberately role-driven: no Process name, yarn concept, Colour, or
	Dia is assumed. Existing Consume rows become configured inputs and existing
	Introduce rows become configured outputs.
	"""
	if not (
		frappe.db.exists("DocType", "IPD Fabric Process")
		and frappe.db.exists("DocType", "IPD Fabric Value Mapping")
	):
		return

	rows = frappe.db.sql(
		"""
		select distinct process.fabric_process, mapping.role, mapping.attribute
		from `tabIPD Fabric Process` process
		inner join `tabIPD Fabric Value Mapping` mapping
			on mapping.parent = process.parent
			and mapping.parenttype = process.parenttype
			and mapping.sequence = process.sequence
		where process.fabric_process is not null
			and mapping.role in ('Consume', 'Introduce')
			and mapping.attribute is not null
		order by process.fabric_process, mapping.role, mapping.attribute
		""",
		as_dict=True,
	)
	by_process = {}
	for row in rows:
		contract = by_process.setdefault(row.fabric_process, {"Consume": [], "Introduce": []})
		if row.attribute not in contract[row.role]:
			contract[row.role].append(row.attribute)

	for process_name, contract in by_process.items():
		if not frappe.db.exists("Process", process_name):
			continue
		process = frappe.get_doc("Process", process_name)
		if not process.get("is_cloth_process") or not process.get("is_item_conversion"):
			continue
		changed = False
		for fieldname, role in (
			("conversion_input_attributes", "Consume"),
			("conversion_output_attributes", "Introduce"),
		):
			existing = {row.attribute for row in process.get(fieldname) or []}
			for attribute in contract[role]:
				if attribute in existing:
					continue
				process.append(fieldname, {"attribute": attribute})
				existing.add(attribute)
				changed = True
		if changed:
			process.save(ignore_permissions=True)
