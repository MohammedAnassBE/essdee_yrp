"""Server-owned configuration for the Production API historical migration.

Connection details deliberately come from ``site_config.json`` rather than the
MRP Data Migration document.  A Desk user may trigger a reviewed migration,
but cannot turn the source bridge into an arbitrary subprocess/filesystem
reader by editing a document field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import frappe

from essdee_yrp.migration.engine import MigrationError


CONFIG_KEY = "essdee_yrp_migration"
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
SUPPORTED_SOURCE_APP = "production_api"
TARGET_APPS = ("yrp", "essdee_yrp")


@dataclass(frozen=True)
class MigrationSettings:
	adapter: str
	source_bench: Path
	source_site: str
	source_app: str
	target_site: str
	target_apps: tuple[str, ...]
	required_defaults: Mapping[str, Any]

	@property
	def source_python(self) -> Path:
		return self.source_bench / "env" / "bin" / "python"

	@property
	def source_sites_path(self) -> Path:
		return self.source_bench / "sites"

	@property
	def source_app_root(self) -> Path:
		return self.source_bench / "apps" / self.source_app / self.source_app

	def public_dict(self) -> dict[str, Any]:
		"""Return non-secret connection identity safe for audit reports."""

		return {
			"adapter": self.adapter,
			"source_bench": str(self.source_bench),
			"source_site": self.source_site,
			"source_app": self.source_app,
			"target_site": self.target_site,
			"target_apps": list(self.target_apps),
		}


def get_migration_settings() -> MigrationSettings:
	"""Resolve and validate the migration profile for the current target site.

	Every site, including development sites, must define
	``essdee_yrp_migration`` in its server-owned configuration. This keeps local
	machine paths and site names out of deployable application code.
	"""

	target_site = str(getattr(frappe.local, "site", "") or "")
	if not target_site:
		raise MigrationError("Migration configuration requires an active target site")

	raw = frappe.conf.get(CONFIG_KEY)
	if not isinstance(raw, Mapping):
		raise MigrationError(
			f"Configure {CONFIG_KEY} in {target_site}/site_config.json before "
			"using the migration"
		)

	adapter = str(raw.get("adapter") or "local_bench")
	if adapter != "local_bench":
		raise MigrationError(
			f"Unsupported migration source adapter {adapter!r}; expected 'local_bench'"
		)

	source_bench_value = raw.get("source_bench")
	if not source_bench_value:
		raise MigrationError(f"{CONFIG_KEY}.source_bench is required")
	source_bench = Path(str(source_bench_value)).expanduser()
	if not source_bench.is_absolute():
		raise MigrationError(f"{CONFIG_KEY}.source_bench must be an absolute path")
	source_bench = source_bench.resolve()

	source_site = _safe_name(raw.get("source_site"), "source_site")
	source_app = _safe_name(
		raw.get("source_app") or SUPPORTED_SOURCE_APP, "source_app"
	)
	if source_app != SUPPORTED_SOURCE_APP:
		raise MigrationError(
			f"This migration contract supports only source app {SUPPORTED_SOURCE_APP!r}"
		)

	required_defaults = raw.get("required_defaults") or {}
	if not isinstance(required_defaults, Mapping):
		raise MigrationError(f"{CONFIG_KEY}.required_defaults must be an object")

	settings = MigrationSettings(
		adapter=adapter,
		source_bench=source_bench,
		source_site=source_site,
		source_app=source_app,
		target_site=target_site,
		target_apps=TARGET_APPS,
		required_defaults=dict(required_defaults),
	)
	missing_target_apps = sorted(set(settings.target_apps) - set(frappe.get_installed_apps()))
	if missing_target_apps:
		raise MigrationError(
			"Migration target is missing required apps: "
			+ ", ".join(missing_target_apps)
		)
	_validate_local_source(settings)
	return settings


def _safe_name(value: Any, fieldname: str) -> str:
	value = str(value or "")
	if not value or not SAFE_NAME.fullmatch(value):
		raise MigrationError(f"Invalid {CONFIG_KEY}.{fieldname}: {value!r}")
	return value


def _validate_local_source(settings: MigrationSettings) -> None:
	required_paths = {
		"source bench": settings.source_bench,
		"source Python": settings.source_python,
		"source site": settings.source_sites_path / settings.source_site / "site_config.json",
		"source app": settings.source_app_root,
	}
	missing = [label for label, path in required_paths.items() if not path.exists()]
	if missing:
		raise MigrationError(
			"Configured migration source is incomplete: " + ", ".join(missing)
		)
