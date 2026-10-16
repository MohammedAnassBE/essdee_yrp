"""Check source DocType field identities and ordering without a Frappe site."""

import json
from collections import Counter
from pathlib import Path


def validate_doctype_metadata():
	root = Path(__file__).resolve().parents[1]
	errors = []
	paths = sorted((root / "essdee_yrp").rglob("doctype/*/*.json"))
	count = 0
	for path in paths:
		metadata = json.loads(path.read_text())
		if metadata.get("doctype") != "DocType":
			continue
		count += 1
		fields = [field.get("fieldname") for field in metadata.get("fields", [])]
		order = metadata.get("field_order", [])
		problems = []
		for label, values in (("fieldname", fields), ("field_order entry", order)):
			for value, occurrences in Counter(values).items():
				if not value or occurrences > 1:
					problems.append(f"invalid {label}: {value!r} ({occurrences} occurrences)")
		for fieldname in sorted(set(order) - set(fields)):
			problems.append(f"field_order references undefined field: {fieldname}")
		for fieldname in sorted(set(fields) - set(order), key=str):
			problems.append(f"field missing from field_order: {fieldname}")
		errors.extend(f"{path.relative_to(root)}: {problem}" for problem in problems)
	if errors:
		raise SystemExit("\n".join(errors))
	print(f"DocType metadata: {count} schemas passed field identity and ordering checks")


if __name__ == "__main__":
	validate_doctype_metadata()
