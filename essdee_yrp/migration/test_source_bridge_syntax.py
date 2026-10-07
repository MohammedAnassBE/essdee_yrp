import ast
from unittest import TestCase

from essdee_yrp.migration.live import SOURCE_BRIDGE

# The bridge scripts run inside the Frappe-15 source bench, whose Python is 3.10.
F15_PYTHON = (3, 10)


class TestSourceBridgeSyntax(TestCase):
	def test_bridge_scripts_parse_on_the_source_bench_python(self):
		for script in (SOURCE_BRIDGE, SOURCE_BRIDGE.with_name("f15_framework_archive.py")):
			with self.subTest(script=script.name):
				ast.parse(script.read_text(), filename=str(script), feature_version=F15_PYTHON)
