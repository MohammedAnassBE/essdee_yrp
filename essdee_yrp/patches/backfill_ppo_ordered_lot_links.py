import frappe


def execute():
	"""Make every Lot row on a Production Order carry both the direct `lot` and the dynamic reference.

	Migrated rows had only `lot`; rows written by F16 Lot saves had only the reference, so
	re-saved Lots left their migrated rows behind as duplicates.
	"""
	frappe.db.sql(
		"""
		DELETE legacy FROM `tabYRP Production Ordered Detail` legacy
		JOIN `tabYRP Production Ordered Detail` current
			ON current.parent = legacy.parent
			AND current.reference_doctype = 'SD YRP Lot'
			AND current.reference_name = legacy.lot
		WHERE IFNULL(legacy.lot, '') != '' AND IFNULL(legacy.reference_name, '') = ''
		"""
	)
	frappe.db.sql(
		"""
		UPDATE `tabYRP Production Ordered Detail` row
		JOIN `tabSD YRP Lot` lot ON lot.name = row.lot
		SET row.reference_doctype = 'SD YRP Lot', row.reference_name = row.lot
		WHERE IFNULL(row.reference_name, '') = ''
		"""
	)
	frappe.db.sql(
		"""
		UPDATE `tabYRP Production Ordered Detail`
		SET lot = reference_name
		WHERE reference_doctype = 'SD YRP Lot' AND IFNULL(reference_name, '') != '' AND IFNULL(lot, '') = ''
		"""
	)
