"""Essdee's single-layout UI configuration policy.

The base YRP engine deliberately owns a generic layout resolver whose fallback
record is named ``Default``.  Essdee ships one opinionated experience instead:
``Premium White``.  Resolve that layout explicitly for every /web boot while
still applying the bounded personal overrides supported by the base engine.
"""

import frappe
from frappe import _

from yrp.yrp.api import ui_config as base_ui_config

PREMIUM_LAYOUT_NAME = "Premium White"


def resolve_config(user):
	"""Return Premium White merged with ``user``'s safe personal overrides."""
	config, meta = base_ui_config._resolve_layout_preview(PREMIUM_LAYOUT_NAME)

	# Honour the base kill switch exactly: preview resolution intentionally
	# returns the skeleton with no selected layout while it is enabled.
	if meta.get("layout") != PREMIUM_LAYOUT_NAME:
		return config, meta

	pref = None
	if user and isinstance(user, str):
		pref = frappe.db.get_value(
			"YRP UI Preference", user, ["overrides"], as_dict=True
		)

	warnings = meta.setdefault("warnings", [])
	overrides = base_ui_config._prepare_layer(
		pref.overrides if pref else None, "overrides", warnings
	)
	if overrides:
		for key in overrides:
			if key != "schema_version" and key not in base_ui_config.OVERRIDABLE_KEYS:
				warnings.append(_("overrides: unknown key '{0}' ignored").format(key))
		config = base_ui_config.merge(
			config, overrides, base_ui_config.OVERRIDABLE_KEYS
		)

	meta["has_preference"] = bool(pref)
	return config, meta


@frappe.whitelist()
def get_my_ui_config():
	"""Return the session user's Premium White-based configuration."""
	config, meta = resolve_config(frappe.session.user)
	return {"config": config, "meta": meta}


@frappe.whitelist(methods=["POST"])
def save_my_ui_overrides(overrides=None):
	"""Reuse base validation/storage, then resolve against Premium White."""
	base_payload = base_ui_config.save_my_ui_overrides(overrides)
	user = frappe.session.user
	frappe.db.set_value(
		"YRP UI Preference",
		user,
		"layout",
		PREMIUM_LAYOUT_NAME,
		update_modified=False,
	)

	# The base response prepends save-time warnings to its resolver warnings.
	# Preserve that useful validation feedback while dropping only the base
	# resolver's now-irrelevant missing-Default degradation.
	base_warnings = list((base_payload.get("meta") or {}).get("warnings") or [])
	_, base_meta = base_ui_config.resolve_config(user)
	resolver_warnings = list(base_meta.get("warnings") or [])
	if resolver_warnings and base_warnings[-len(resolver_warnings) :] == resolver_warnings:
		save_warnings = base_warnings[: -len(resolver_warnings)]
	else:
		save_warnings = base_warnings

	config, meta = resolve_config(user)
	meta["warnings"] = save_warnings + meta["warnings"]
	return {"config": config, "meta": meta}


@frappe.whitelist(methods=["POST"])
def reset_my_ui_overrides():
	"""Reuse base preference cleanup, then resolve against Premium White."""
	base_ui_config.reset_my_ui_overrides()
	config, meta = resolve_config(frappe.session.user)
	return {"config": config, "meta": meta}


@frappe.whitelist()
def get_ui_config_for(user=None, layout=None):
	"""System Manager preview using Essdee's single-layout policy for users."""
	frappe.only_for("System Manager")
	if bool(user) == bool(layout):
		frappe.throw(
			_("Pass exactly one of user= or layout="),
			title=_("Invalid UI Config Preview"),
		)

	if user:
		if not frappe.db.get_value("User", user, "enabled"):
			frappe.throw(_("Unknown or disabled user"))
		config, meta = resolve_config(user)
		perm_user = user
	else:
		config, meta = base_ui_config._resolve_layout_preview(layout)
		perm_user = frappe.session.user

	return {
		"config": config,
		"meta": meta,
		"perm_hints": base_ui_config._perm_hints(config, perm_user),
	}


def get_config_for_boot():
	"""Never let a layout failure make the Essdee /web boot fail."""
	try:
		config, meta = resolve_config(frappe.session.user)
		return {"config": config, "meta": meta}
	except Exception:
		try:
			frappe.log_error(
				message=frappe.get_traceback(),
				title="Essdee UI config: Premium White resolution failed",
			)
		except Exception:
			pass
		return None
