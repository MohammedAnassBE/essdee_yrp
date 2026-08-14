#!/usr/bin/env python3
"""Port the approved production_api DocType schemas into Essdee YRP.

This intentionally ports schema only: DocType JSON, an empty package, and a
minimal controller. Client scripts and production_api business logic are not
copied; those are a later migration phase.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


TARGET_MODULE = "Essdee YRP"
EXPECTED_DOCTYPE_COUNT = 150
DOCTYPE_RENAMES = {"Purchase Order Lot": "Lot MultiSelect"}
LINK_OPTION_RENAMES = {
	"Essdee Raw Print Format": "ZPL Raw Print Format",
	"Essdee Raw Print Format Detail": "ZPL Raw Print Format Detail",
	"Essdee Debit": "Debit",
	"GRN Item Type": "Received Type",
	"Stock Settings": "YRP Stock Settings",
	"Vendor Bill Tracking": "Bill Tracking",
	"Vendor Bill Tracking Assignment Detail": "Bill Tracking Assignment Detail",
}
LINK_FIELD_TYPES = {"Link", "Table", "Table MultiSelect"}
LOT_TRANSFER_ITEM_FIELDS = [
	{"fieldname": "item", "fieldtype": "Link", "in_list_view": 1, "label": "Item Variant", "options": "Item Variant", "reqd": 1},
	{"fieldname": "from_lot", "fieldtype": "Link", "in_list_view": 1, "label": "From Lot", "options": "Lot", "reqd": 1},
	{"fieldname": "to_lot", "fieldtype": "Link", "in_list_view": 1, "label": "To Lot", "options": "Lot", "reqd": 1},
	{"fieldname": "warehouse", "fieldtype": "Link", "in_list_view": 1, "label": "Warehouse", "options": "Warehouse", "reqd": 1},
	{"fieldname": "received_type", "fieldtype": "Link", "in_list_view": 1, "label": "Received Type", "options": "Received Type", "reqd": 1},
	{"fieldname": "qty", "fieldtype": "Float", "in_list_view": 1, "label": "Quantity", "reqd": 1},
	{"fieldname": "uom", "fieldtype": "Link", "in_list_view": 1, "label": "UOM", "options": "UOM", "reqd": 1},
	{"fieldname": "rate", "fieldtype": "Currency", "in_list_view": 1, "label": "Rate"},
	{"fieldname": "stock_qty", "fieldtype": "Float", "hidden": 1, "label": "Stock Quantity", "read_only": 1},
	{"fieldname": "stock_uom", "fieldtype": "Link", "hidden": 1, "label": "Stock UOM", "options": "UOM", "read_only": 1},
	{"fieldname": "conversion_factor", "fieldtype": "Float", "hidden": 1, "label": "Conversion Factor", "read_only": 1},
	{"fieldname": "stock_uom_rate", "fieldtype": "Currency", "hidden": 1, "label": "Stock UOM Rate", "read_only": 1},
	{"fieldname": "amount", "fieldtype": "Currency", "hidden": 1, "label": "Amount", "read_only": 1},
]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument("source_app", type=Path)
	parser.add_argument("audit_markdown", type=Path)
	parser.add_argument("--write", action="store_true")
	return parser.parse_args()


def read_manifest(path: Path) -> list[str]:
	text = path.read_text()
	match = re.search(
		r"^## (?:Missing in essdee_yrp\.site|Schema created in essdee_yrp) \((\d+)\)\n(?P<body>.*?)(?=^## )",
		text,
		re.MULTILINE | re.DOTALL,
	)
	if not match:
		raise RuntimeError(f"Missing-DocType section was not found in {path}")

	declared_count = int(match.group(1))
	names = re.findall(
		r"^\| ([^|]+?) \| Yes \| (?:No|Yes) \| (?:N/A|Added) \|$",
		match.group("body"),
		re.MULTILINE,
	)
	if declared_count != EXPECTED_DOCTYPE_COUNT or len(names) != EXPECTED_DOCTYPE_COUNT:
		raise RuntimeError(
			f"Expected {EXPECTED_DOCTYPE_COUNT} missing DocTypes; "
			f"header says {declared_count}, rows contain {len(names)}"
		)
	if len(names) != len(set(names)):
		raise RuntimeError("The missing-DocType manifest contains duplicate names")
	return names


def build_source_index(source_app: Path) -> dict[str, list[Path]]:
	index: dict[str, list[Path]] = {}
	for path in source_app.glob("*/doctype/*/*.json"):
		doc = json.loads(path.read_text())
		name = doc.get("name")
		if not name:
			continue
		index.setdefault(name, []).append(path)
	return index


def transform_schema(source: dict, target_module: str = TARGET_MODULE) -> tuple[dict, int]:
	target = dict(source)
	target["module"] = target_module
	target["name"] = DOCTYPE_RENAMES.get(source.get("name"), source.get("name"))
	remap_count = 0
	fields = []
	for source_field in source.get("fields", []):
		field = dict(source_field)
		if field.get("fieldtype") in LINK_FIELD_TYPES and field.get("options") in LINK_OPTION_RENAMES:
			field["options"] = LINK_OPTION_RENAMES[field["options"]]
			remap_count += 1
		fields.append(field)
	target["fields"] = fields
	if target.get("name") == "Lot Transfer Item":
		# Keep the Production API name while preserving the working F16 warehouse-
		# based child structure formerly called `YRP Lot Transfer Item`.
		for key in ("allow_rename", "index_web_pages_for_search", "row_format"):
			target.pop(key, None)
		target.update(
			{
				"autoname": "hash",
				"editable_grid": 1,
				"field_order": [field["fieldname"] for field in LOT_TRANSFER_ITEM_FIELDS],
				"fields": LOT_TRANSFER_ITEM_FIELDS,
				"grid_page_length": 50,
				"istable": 1,
				"links": [],
				"naming_rule": "Random",
				"permissions": [],
				"sort_field": "modified",
				"sort_order": "DESC",
				"states": [],
			}
		)
	return target, remap_count


def validate_alignment(name: str, schema: dict) -> None:
	fieldnames = [field["fieldname"] for field in schema.get("fields", [])]
	field_order = schema.get("field_order", [])
	duplicates = [fieldname for fieldname, count in Counter(fieldnames).items() if count > 1]
	missing = [fieldname for fieldname in field_order if fieldname not in fieldnames]
	unplaced = [fieldname for fieldname in fieldnames if fieldname not in field_order]
	if duplicates or missing or unplaced:
		raise RuntimeError(
			f"Invalid field alignment for {name}: duplicates={duplicates}, "
			f"missing={missing}, unplaced={unplaced}"
		)


def controller_source(name: str, is_tree: bool, target_module: str) -> str:
	class_name = name.replace(" ", "").replace("-", "")
	publisher = "Mohammed Anas" if target_module == "YRP" else "Essdee"
	if is_tree:
		return (
			f"# Copyright (c) 2026, {publisher} and contributors\n"
			"# For license information, please see license.txt\n\n"
			"from frappe.utils.nestedset import NestedSet\n\n\n"
			f"class {class_name}(NestedSet):\n"
			"\tpass\n"
		)
	return (
		f"# Copyright (c) 2026, {publisher} and contributors\n"
		"# For license information, please see license.txt\n\n"
		"from frappe.model.document import Document\n\n\n"
		f"class {class_name}(Document):\n"
		"\tpass\n"
	)


def expected_files(
	source_path: Path,
	schema: dict,
	target_root: Path,
	target_module: str,
) -> dict[Path, str]:
	slug = re.sub(r"[^a-z0-9]+", "_", schema["name"].lower()).strip("_")
	target_dir = target_root / slug
	return {
		target_dir / "__init__.py": "",
		target_dir / f"{slug}.json": json.dumps(schema, indent=1, ensure_ascii=False) + "\n",
		target_dir / f"{slug}.py": controller_source(
			schema["name"], bool(schema.get("is_tree")), target_module
		),
	}


def main() -> None:
	args = parse_args()
	target_root = Path(__file__).resolve().parents[1] / "essdee_yrp" / "essdee_yrp" / "doctype"
	names = read_manifest(args.audit_markdown.resolve())
	index = build_source_index(args.source_app.resolve())
	missing_sources = [name for name in names if not index.get(name)]
	if missing_sources:
		raise RuntimeError(f"Missing source JSON for: {', '.join(missing_sources)}")
	duplicate_sources = [name for name in names if len(index[name]) > 1]
	if duplicate_sources:
		raise RuntimeError(f"Duplicate source JSON for: {', '.join(duplicate_sources)}")

	files: dict[Path, str] = {}
	parent_count = 0
	child_count = 0
	remap_count = 0
	for name in names:
		source_path = index[name][0]
		source = json.loads(source_path.read_text())
		target, remapped = transform_schema(source, TARGET_MODULE)
		validate_alignment(name, target)
		remap_count += remapped
		if target.get("istable"):
			child_count += 1
		else:
			parent_count += 1
		expected = expected_files(source_path, target, target_root, TARGET_MODULE)
		files.update(expected)

	if args.write:
		existing = [str(path) for path in files if path.exists()]
		if existing:
			raise RuntimeError(
				"Refusing to overwrite generated files. Re-run without --write to verify them. "
				f"First existing path: {existing[0]}"
			)
		for path, content in files.items():
			path.parent.mkdir(parents=True, exist_ok=True)
			path.write_text(content)
		mode = "generated"
	else:
		mismatches = []
		for path, expected in files.items():
			if not path.exists():
				mismatches.append(f"missing: {path}")
			elif path.name == "__init__.py" and path.read_text().strip() == expected.strip():
				continue
			elif path.suffix == ".py":
				# Controllers are allowed to grow during the later logic phase. The
				# schema verifier only requires the generated controller class to
				# remain present; it must not erase approved business behavior.
				class_match = re.search(r"^class\s+(\w+)\(", expected, re.MULTILINE)
				if not class_match or not re.search(
					rf"^class\s+{re.escape(class_match.group(1))}\(",
					path.read_text(),
					re.MULTILINE,
				):
					mismatches.append(f"missing controller class: {path}")
			elif path.read_text() != expected:
				mismatches.append(f"different: {path}")
		if mismatches:
			raise RuntimeError("Schema parity check failed:\n" + "\n".join(mismatches))
		mode = "verified"

	print(
		f"{mode}: {len(names)} DocTypes "
		f"({parent_count} parent, {child_count} child), {remap_count} link-option remaps"
	)


if __name__ == "__main__":
	main()
