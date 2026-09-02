import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection.sd_yrp_essdee_quality_inspection import (
	_get_aql_limits,
	_selected_order_quantity,
	create_inspection_debit,
)
from essdee_yrp.migration.rules import get_rule


class TestEssdeeQualityInspection(IntegrationTestCase):
	def test_quality_schema_defaults_and_debit_mapping(self):
		settings = frappe.get_meta('SD YRP MRP Settings')
		self.assertIsNotNone(settings.get_field("default_major_aql_level"))
		self.assertIsNotNone(settings.get_field("default_minor_aql_level"))
		self.assertEqual(
			frappe.db.get_single_value('SD YRP MRP Settings', "default_major_aql_level"),
			"Level-2.5",
		)
		self.assertEqual(
			frappe.db.get_single_value('SD YRP MRP Settings', "default_minor_aql_level"),
			"Level-4.0",
		)

		debit_field = frappe.get_meta('YRP Debit').get_field("quality_inspection")
		self.assertIsNotNone(debit_field)
		self.assertEqual(debit_field.options, 'SD YRP Essdee Quality Inspection')
		self.assertEqual(debit_field.module, "Essdee YRP")
		self.assertNotIn(
			"quality_inspection", get_rule("Essdee Debit").ignored_fields
		)

	def test_aql_calculation_matches_migrated_quality_inspections(self):
		rows = frappe.get_all(
			'SD YRP Essdee Quality Inspection',
			filters={
				"name": ["like", "EQI-2627-%"],
				"offer_qty": [">", 0],
				"major_aql_level": ["is", "set"],
				"minor_aql_level": ["is", "set"],
			},
			fields=[
				"name",
				"checking_level",
				"offer_qty",
				"major_aql_level",
				"minor_aql_level",
				"sample_piece_count",
				"major_defect_maximum_allowed",
				"minor_defect_maximum_allowed",
			],
		)
		self.assertGreater(len(rows), 100)
		for row in rows:
			limits = _get_aql_limits(
				row.checking_level,
				row.offer_qty,
				row.major_aql_level,
				row.minor_aql_level,
			)
			self.assertEqual(limits["sample"], row.sample_piece_count, row.name)
			self.assertEqual(
				limits["major_allowed"],
				row.major_defect_maximum_allowed,
				row.name,
			)
			self.assertEqual(
				limits["minor_allowed"],
				row.minor_defect_maximum_allowed,
				row.name,
			)

	def test_selected_order_quantity_matches_current_migrated_oracles(self):
		names = frappe.get_all(
			'SD YRP Essdee Quality Inspection',
			filters={"against_id": ["is", "set"], "order_qty": [">", 0]},
			pluck="name",
			order_by="modified desc",
			limit=5,
		)
		self.assertEqual(len(names), 5)
		for name in names:
			inspection = frappe.get_doc('SD YRP Essdee Quality Inspection', name)
			work_order = frappe.get_doc('YRP Work Order', inspection.against_id)
			self.assertEqual(
				flt(_selected_order_quantity(work_order, inspection)),
				flt(inspection.order_qty),
				name,
			)

	def test_quality_endpoints_require_login(self):
		methods = (
			"get_default_aql_level",
			"get_max_minor_defect_allowed",
			"get_against_details",
			"create_inspection_debit",
		)
		module = (
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection."
			"essdee_quality_inspection"
		)
		for method in methods:
			function = frappe.get_attr(f"{module}.{method}")
			self.assertIn(function, frappe.whitelisted)
			self.assertNotIn(function, frappe.guest_methods)

	def test_inspection_debit_uses_mapped_base_debit(self):
		inspection_name = frappe.get_all(
			'SD YRP Essdee Quality Inspection',
			filters={"docstatus": 1},
			pluck="name",
			limit=1,
		)[0]
		inspection = frappe.get_doc('SD YRP Essdee Quality Inspection', inspection_name)
		frappe.db.set_single_value('YRP YRP Settings', "debit_request_role", "System Manager")

		result = create_inspection_debit(
			quality_inspection=inspection.name,
			debit_value=125,
			reason="Quality inspection test",
			debit_document="/files/quality-inspection-test.pdf",
		)
		debit = frappe.get_doc('YRP Debit', result["name"])
		self.assertEqual(debit.docstatus, 1)
		self.assertEqual(debit.work_order, inspection.against_id)
		self.assertEqual(debit.quality_inspection, inspection.name)
		self.assertEqual(debit.inspection, 1)
