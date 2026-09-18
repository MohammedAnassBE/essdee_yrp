"""Cross-process execution lock for every MRP migration action."""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.synchronization import filelock

from essdee_yrp.migration.engine import MigrationError


MIGRATION_EXECUTION_LOCK = "sd_yrp_mrp_migration_execution"
_Return = TypeVar("_Return")


class MigrationAlreadyRunningError(MigrationError):
	"""Raised without changing the status of the process that owns the lock."""


def exclusive_migration_run(function: Callable[..., _Return]) -> Callable[..., _Return]:
	"""Serialize migration reads/writes for the current Frappe site."""

	@wraps(function)
	def locked(*args, **kwargs) -> _Return:
		try:
			with filelock(MIGRATION_EXECUTION_LOCK, timeout=0):
				return function(*args, **kwargs)
		except LockTimeoutError as exc:
			raise MigrationAlreadyRunningError(
				"Another MRP migration, verification, sample, or reset is already running"
			) from exc

	return locked
