import unittest
from unittest.mock import patch

import frappe

from essdee_yrp.cloth_execution import (
	get_row_execution_parameters,
	get_supported_execution_route,
	has_fabric_execution_key,
	resolve_downstream_execution_version,
	stamp_cloth_execution_version,
)


def _settings():
	return frappe._dict(
		default_knitting_process="KNIT-PROCESS",
		default_dyeing_process="DYE-PROCESS",
	)


def _step(process_name, shape, attribute=None, position=0):
	return {
		"process_name": process_name,
		"shape": shape,
		"attribute": attribute,
		"position": position,
	}


def _source(execution_key=None):
	parameters = "{}"
	if execution_key:
		parameters = frappe.as_json({"fabric_execution_key": execution_key})
	return frappe._dict(additional_parameters=parameters)


class TestClothExecutionRoute(unittest.TestCase):
	@patch("essdee_yrp.cloth_execution.frappe.get_cached_doc", return_value=_settings())
	@patch(
		"essdee_yrp.cloth_execution.get_fabric_steps",
		return_value=[
			_step("KNIT-PROCESS", "conversion", position=0),
			_step("DYE-PROCESS", "swap", "Colour", 1),
			_step("WASH-PROCESS", "identity", position=2),
			_step("LATER-COMPACTING", "swap", "Dia", 3),
		],
	)
	def test_supported_route_is_exact_knitting_dyeing_identity_washing(self, _steps, _settings_doc):
		route = get_supported_execution_route(frappe._dict(name="IPD-CLOTH"))

		self.assertEqual(
			{
				"knitting": ("KNIT-PROCESS", 0),
				"dyeing": ("DYE-PROCESS", 1),
				"washing": ("WASH-PROCESS", 2),
			},
			{key: (value["process_name"], value["position"]) for key, value in route.items()},
		)

	@patch("essdee_yrp.cloth_execution.frappe.get_cached_doc", return_value=_settings())
	@patch(
		"essdee_yrp.cloth_execution.get_fabric_steps",
		return_value=[
			_step("KNIT-PROCESS", "conversion", position=0),
			_step("COMPACTING-PROCESS", "swap", "Dia", 1),
			_step("DYE-PROCESS", "swap", "Colour", 2),
			_step("WASH-PROCESS", "identity", position=3),
		],
	)
	def test_compacting_or_intervening_step_is_not_versioned(self, _steps, _settings_doc):
		self.assertIsNone(get_supported_execution_route(frappe._dict(name="IPD-CLOTH")))

	@patch("essdee_yrp.cloth_execution.get_supported_execution_route")
	@patch("essdee_yrp.cloth_execution.frappe.get_cached_doc")
	def test_new_supported_work_order_is_stamped_version_one(self, get_cached_doc, supported_route):
		get_cached_doc.return_value = frappe._dict(name="IPD-CLOTH")
		supported_route.return_value = {
			"knitting": _step("KNIT-PROCESS", "conversion", position=0),
			"dyeing": _step("DYE-PROCESS", "swap", "Colour", 1),
			"washing": _step("WASH-PROCESS", "identity", position=2),
		}
		work_order = frappe._dict(
			production_detail="IPD-CLOTH",
			process_name="DYE-PROCESS",
			cloth_execution_version=0,
		)

		stamp_cloth_execution_version(work_order)

		self.assertEqual(work_order.cloth_execution_version, 1)


class TestClothExecutionVersionBoundary(unittest.TestCase):
	def test_existing_zero_version_never_upgrades_on_recalculate(self):
		work_order = frappe._dict(cloth_execution_version=0)

		version = resolve_downstream_execution_version(
			work_order, [_source()], first_calculation=True
		)

		self.assertEqual(version, 0)
		self.assertEqual(work_order.cloth_execution_version, 0)

	def test_new_downstream_all_legacy_sources_downgrades_only_on_first_calculation(self):
		work_order = frappe._dict(cloth_execution_version=1)

		version = resolve_downstream_execution_version(
			work_order, [_source(), _source()], first_calculation=True
		)

		self.assertEqual(version, 0)
		self.assertEqual(work_order.cloth_execution_version, 0)

	def test_new_downstream_all_keyed_sources_keeps_version_one(self):
		work_order = frappe._dict(cloth_execution_version=1)

		version = resolve_downstream_execution_version(
			work_order, [_source("source-a"), _source("source-b")], first_calculation=True
		)

		self.assertEqual(version, 1)
		self.assertEqual(work_order.cloth_execution_version, 1)

	def test_mixed_keyed_and_legacy_sources_are_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "mixed keyed and legacy"):
			resolve_downstream_execution_version(
				frappe._dict(cloth_execution_version=1),
				[_source("source-a"), _source()],
				first_calculation=True,
			)

	def test_version_zero_work_order_rejects_keyed_source(self):
		with self.assertRaisesRegex(frappe.ValidationError, "legacy Work Order"):
			resolve_downstream_execution_version(
				frappe._dict(cloth_execution_version=0),
				[_source("source-a")],
				first_calculation=True,
			)

	def test_later_version_one_recalculation_rejects_all_unkeyed_sources(self):
		with self.assertRaisesRegex(frappe.ValidationError, "versioned Work Order"):
			resolve_downstream_execution_version(
				frappe._dict(cloth_execution_version=1),
				[_source(), _source()],
				first_calculation=False,
			)

	def test_execution_key_parser_rejects_invalid_or_blank_values(self):
		self.assertEqual(
			get_row_execution_parameters(
				frappe._dict(additional_parameters='{"fabric_execution_key":"fabric-123"}')
			),
			{"fabric_execution_key": "fabric-123"},
		)
		self.assertTrue(
			has_fabric_execution_key(
				frappe._dict(additional_parameters='{"fabric_execution_key":"fabric-123"}')
			)
		)
		self.assertEqual(get_row_execution_parameters(frappe._dict(additional_parameters="broken")), {})
		self.assertFalse(
			has_fabric_execution_key(frappe._dict(additional_parameters='{"fabric_execution_key":""}'))
		)
