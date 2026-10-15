"""Let template Items copy their disabled and deprecated flags to variants, and sync existing variants."""

from collections import defaultdict

import frappe

FIELDS = ("disabled", "custom_deprecated")


def execute():
	add_variant_fields()
	sync_variant_flags()


def add_variant_fields():
	settings = frappe.get_single("Item Variant Settings")
	existing = {row.field_name for row in settings.fields}
	missing = [field for field in FIELDS if field not in existing]
	if not missing:
		return
	for field in missing:
		settings.append("fields", {"field_name": field})
	settings.save(ignore_permissions=True)


def sync_variant_flags():
	variant = frappe.qb.DocType("Item")
	template = frappe.qb.DocType("Item").as_("template")
	rows = (
		frappe.qb.from_(variant)
		.join(template)
		.on(template.name == variant.variant_of)
		.select(variant.name, template.disabled, template.custom_deprecated)
		.where(
			(variant.disabled != template.disabled)
			| (variant.custom_deprecated != template.custom_deprecated)
		)
		.run()
	)
	variants_by_flags = defaultdict(list)
	for name, *flags in rows:
		variants_by_flags[tuple(flags)].append(name)

	for flags, names in variants_by_flags.items():
		frappe.db.set_value("Item", {"name": ["in", names]}, dict(zip(FIELDS, flags, strict=True)))
