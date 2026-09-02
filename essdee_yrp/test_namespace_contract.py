"""Static contract tests for the SD YRP DocType/report namespace."""

from __future__ import annotations

import ast
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from essdee_yrp import hooks, web_build
from essdee_yrp.patches import prefix_owned_doctypes_and_reports


PACKAGE_ROOT = Path(__file__).resolve().parent
YRP_PACKAGE_ROOT = PACKAGE_ROOT.parents[1] / "yrp" / "yrp"
OWNED_MODULES = {"Essdee YRP"}
YRP_MODULES = {"YRP", "YRP Stock"}
PREFIX = "SD YRP "
YRP_PREFIX = "YRP "
LINK_FIELD_TYPES = {"Link", "Table", "Table MultiSelect"}


def _load_json(path: Path):
	try:
		return json.loads(path.read_text())
	except (OSError, UnicodeDecodeError, json.JSONDecodeError):
		return None


def _scrub(value: str) -> str:
	return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def _metadata(root: Path, modules: set[str], record_type: str):
	for path in root.rglob("*.json"):
		data = _load_json(path)
		if not isinstance(data, dict) or data.get("module") not in modules:
			continue
		if data.get("doctype") != record_type:
			continue
		name = data.get("name")
		if record_type == "Report":
			name = data.get("report_name") or name
		if name:
			yield path, data, name


def _owned_metadata(record_type: str):
	yield from _metadata(PACKAGE_ROOT, OWNED_MODULES, record_type)


def _fixture_definition(record_type: str):
	return next(row for row in hooks.fixtures if row.get("dt") == record_type)


def _layout_identity_values(value):
	"""Yield DocType identities from the supported layout vocabulary."""
	if isinstance(value, dict):
		for key, child in value.items():
			if key == "doctype" and isinstance(child, str):
				yield child
			elif key in {"doctypes", "quickCreate"} and isinstance(child, list):
				yield from (item for item in child if isinstance(item, str))
			elif key == "listViews" and isinstance(child, dict):
				yield from child
			elif key == "newCta" and isinstance(child, dict):
				primary = child.get("primary")
				if isinstance(primary, str):
					yield primary
				menu = child.get("menu")
				if isinstance(menu, list):
					yield from (item for item in menu if isinstance(item, str))
			yield from _layout_identity_values(child)
	elif isinstance(value, list):
		for child in value:
			yield from _layout_identity_values(child)


class TestNamespaceContract(unittest.TestCase):
	def test_pre_model_sync_patch_covers_the_complete_manifest(self):
		with patch.object(
			prefix_owned_doctypes_and_reports.frappe,
			"get_app_path",
			return_value=str(PACKAGE_ROOT),
		):
			records = list(prefix_owned_doctypes_and_reports._metadata_renames())

		self.assertEqual(len(records), 222)
		self.assertEqual(
			len({(record_type, new_name) for record_type, _old_name, new_name in records}),
			222,
		)

	def test_framework_owned_old_name_is_never_renamed(self):
		def get_value(_record_type, name, _fieldname):
			return {"Supplier": "Buying", "SD YRP Supplier": None}[name]

		db = SimpleNamespace(get_value=get_value)
		with (
			patch.object(prefix_owned_doctypes_and_reports.frappe, "db", db),
			patch.object(prefix_owned_doctypes_and_reports.frappe, "rename_doc") as rename_doc,
		):
			prefix_owned_doctypes_and_reports._rename_owned_record(
				"DocType",
				"Supplier",
				"SD YRP Supplier",
			)

		rename_doc.assert_not_called()

	def test_owned_rename_uses_frappe_v16_arguments(self):
		def get_value(_record_type, name, _fieldname):
			return {"Product Season": "Essdee YRP", "SD YRP Product Season": None}[name]

		db = SimpleNamespace(get_value=get_value)
		with (
			patch.object(prefix_owned_doctypes_and_reports.frappe, "db", db),
			patch.object(prefix_owned_doctypes_and_reports.frappe, "rename_doc") as rename_doc,
		):
			prefix_owned_doctypes_and_reports._rename_owned_record(
				"DocType",
				"Product Season",
				"SD YRP Product Season",
			)

		rename_doc.assert_called_once_with(
			"DocType",
			"Product Season",
			"SD YRP Product Season",
			force=True,
			show_alert=False,
			rebuild_search=False,
		)

	def test_every_owned_doctype_and_report_has_the_essdee_prefix_and_path(self):
		counts = {}
		for record_type in ("DocType", "Report"):
			records = list(_owned_metadata(record_type))
			counts[record_type] = len(records)
			for path, _data, name in records:
				with self.subTest(record_type=record_type, name=name):
					slug = _scrub(name)
					self.assertTrue(name.startswith(PREFIX), name)
					self.assertEqual(path.parent.name, slug)
					self.assertEqual(path.name, f"{slug}.json")

		self.assertEqual(counts, {"DocType": 196, "Report": 26})

	def test_owned_link_and_table_targets_never_use_an_old_name(self):
		doctypes = list(_owned_metadata("DocType"))
		yrp_doctypes = list(_metadata(YRP_PACKAGE_ROOT, YRP_MODULES, "DocType"))
		old_names = {name.removeprefix(PREFIX) for _path, _data, name in doctypes}
		old_names.update(
			name.removeprefix(YRP_PREFIX) for _path, _data, name in yrp_doctypes
		)
		for _path, data, name in doctypes:
			for field in data.get("fields") or []:
				if field.get("fieldtype") not in LINK_FIELD_TYPES:
					continue
				with self.subTest(doctype=name, fieldname=field.get("fieldname")):
					self.assertNotIn(field.get("options"), old_names)

	def test_controller_class_and_legacy_import_alias_match_the_new_name(self):
		for path, _data, name in _owned_metadata("DocType"):
			slug = _scrub(name)
			controller = path.with_name(f"{slug}.py")
			if not controller.exists():
				continue
			tree = ast.parse(controller.read_text(), filename=str(controller))
			new_class = name.replace(" ", "").replace("-", "")
			old_class = name.removeprefix(PREFIX).replace(" ", "").replace("-", "")
			classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
			aliases = {
				(target.id, node.value.id)
				for node in ast.walk(tree)
				if isinstance(node, ast.Assign)
				and isinstance(node.value, ast.Name)
				for target in node.targets
				if isinstance(target, ast.Name)
			}
			with self.subTest(doctype=name):
				self.assertIn(new_class, classes)
				self.assertIn((old_class, new_class), aliases)

	def test_customization_fixture_names_follow_frappe_autoname(self):
		custom_fields = _load_json(PACKAGE_ROOT / "fixtures" / "custom_field.json")
		for row in custom_fields:
			with self.subTest(custom_field=row["name"]):
				self.assertEqual(row["name"], f"{row['dt']}-{row['fieldname']}")

		property_setters = _load_json(PACKAGE_ROOT / "fixtures" / "property_setter.json")
		for row in property_setters:
			field = row.get("field_name") or row.get("row_name") or "main"
			with self.subTest(property_setter=row["name"]):
				self.assertEqual(
					row["name"],
					f"{row['doc_type']}-{field}-{row['property']}",
				)

	def test_customization_fixture_references_never_use_an_old_name(self):
		final_names = {name for _path, _data, name in _owned_metadata("DocType")}
		final_names.update(
			name
			for _path, _data, name in _metadata(YRP_PACKAGE_ROOT, YRP_MODULES, "DocType")
		)
		old_names = {
			name.removeprefix(PREFIX)
			if name.startswith(PREFIX)
			else name.removeprefix(YRP_PREFIX)
			for name in final_names
		}

		for filename, identity_fields in (
			("custom_field.json", ("dt", "options")),
			("property_setter.json", ("doc_type",)),
			("custom_docperm.json", ("parent",)),
		):
			for row in _load_json(PACKAGE_ROOT / "fixtures" / filename):
				for fieldname in identity_fields:
					with self.subTest(
						fixture=filename,
						record=row.get("name"),
						fieldname=fieldname,
					):
						self.assertNotIn(row.get(fieldname), old_names)

	def test_fixture_filters_match_the_records_they_export(self):
		property_setters = _load_json(PACKAGE_ROOT / "fixtures" / "property_setter.json")
		property_setter_filter = _fixture_definition("Property Setter")["filters"]
		self.assertEqual(property_setter_filter[0][:2], ["name", "in"])
		self.assertEqual(
			set(property_setter_filter[0][2]),
			{row["name"] for row in property_setters},
		)

		layouts = _load_json(PACKAGE_ROOT / "fixtures" / "ui_layout.json")
		layout_doctypes = {row["doctype"] for row in layouts}
		self.assertEqual(layout_doctypes, {"YRP UI Layout"})
		self.assertEqual(_fixture_definition("YRP UI Layout")["dt"], "YRP UI Layout")

	def test_embedded_layout_configs_use_namespaced_doctype_identities(self):
		final_names = {name for _path, _data, name in _owned_metadata("DocType")}
		final_names.update(
			name
			for _path, _data, name in _metadata(YRP_PACKAGE_ROOT, YRP_MODULES, "DocType")
		)
		old_names = {
			name.removeprefix(PREFIX)
			if name.startswith(PREFIX)
			else name.removeprefix(YRP_PREFIX)
			for name in final_names
		}

		layouts = _load_json(PACKAGE_ROOT / "fixtures" / "ui_layout.json")
		for row in layouts:
			config = json.loads(row["config"])
			for identity in _layout_identity_values(config):
				with self.subTest(layout=row["name"], identity=identity):
					self.assertNotIn(identity, old_names)

	def test_layout_fixture_changes_invalidate_the_web_build_signature(self):
		with tempfile.TemporaryDirectory() as directory:
			fixture = Path(directory) / "ui_layout.json"
			fixture.write_text('[{"name": "First"}]')
			with patch.object(web_build, "_DEFAULT_LAYOUT_FIXTURE", str(fixture)):
				before = web_build._source_signature()
				fixture.write_text('[{"name": "Second"}]')
				after = web_build._source_signature()
		self.assertNotEqual(before, after)


if __name__ == "__main__":
	unittest.main()
