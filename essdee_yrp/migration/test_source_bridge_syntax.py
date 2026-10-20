import ast
import runpy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from essdee_yrp.migration.live import SOURCE_BRIDGE

# The bridge scripts run inside the Frappe-15 source bench, whose Python is 3.10.
F15_PYTHON = (3, 10)


class TestSourceBridgeSyntax(TestCase):
	def test_bridge_scripts_parse_on_the_source_bench_python(self):
		for script in (SOURCE_BRIDGE, SOURCE_BRIDGE.with_name("f15_framework_archive.py")):
			with self.subTest(script=script.name):
				ast.parse(script.read_text(), filename=str(script), feature_version=F15_PYTHON)


class TestFinishingStatusHistoryBridge(TestCase):
	def test_exports_version_history_with_current_plan_status(self):
		bridge = runpy.run_path(str(SOURCE_BRIDGE))
		versions = [{"docname": "FP-1", "creation": "2026-05-15 12:30:00", "data": '{"changed":[["fp_status","Planned","Dispatched"]]}'}]
		frappe = SimpleNamespace(get_all=Mock(side_effect=[[{"name": "FP-1", "fp_status": "Dispatched"}], versions]))
		rows = list(bridge["finishing_plan_status_history"](frappe))
		self.assertEqual(rows, [{"kind": "finishing_plan_status_history", "name": "FP-1", "fp_status": "Dispatched", "versions": versions}])

	def test_parent_export_passes_versions_to_transformer(self):
		bridge = runpy.run_path(str(SOURCE_BRIDGE))
		versions = [{"docname": "FP-1", "creation": "2026-05-15 12:30:00", "data": "{}"}]
		frappe = SimpleNamespace(get_all=Mock(return_value=versions))
		emit = bridge["_emit_export_parent_rows"]
		with patch.dict(emit.__globals__, {"_write": Mock(), "_add_passwords": Mock()}):
			emit(frappe, {}, "Finishing Plan", {"fields": []}, [{"name": "FP-1", "fp_status": "Dispatched"}])
			output = emit.__globals__["_write"].call_args.args[0]
		self.assertEqual(output.get("__migration_fp_status_versions"), versions)
