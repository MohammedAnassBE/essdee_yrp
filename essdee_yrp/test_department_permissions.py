import json
from pathlib import Path
from unittest import TestCase

CUSTOM_DOCPERMS = Path(__file__).parent / "fixtures" / "custom_docperm.json"


class TestDepartmentPermissionFixture(TestCase):
	"""Department Custom DocPerm rows replace the standard ones, so they must keep them."""

	def _department_rows(self):
		with CUSTOM_DOCPERMS.open() as source:
			return {row["role"]: row for row in json.load(source) if row["parent"] == "Department"}

	def test_all_role_can_read_department(self):
		row = self._department_rows()["All"]
		self.assertEqual((row["read"], row["write"], row["create"], row["delete"]), (1, 0, 0, 0))

	def test_standard_department_roles_keep_full_access(self):
		rows = self._department_rows()
		for role in ("HR User", "HR Manager", "Academics User"):
			with self.subTest(role=role):
				row = rows[role]
				self.assertEqual((row["read"], row["write"], row["create"], row["delete"]), (1, 1, 1, 1))

	def test_department_is_exported_by_custom_docperm_fixture(self):
		from essdee_yrp import hooks

		fixture = next(item for item in hooks.fixtures if item.get("dt") == "Custom DocPerm")
		self.assertIn("Department", fixture["filters"][0][2])
