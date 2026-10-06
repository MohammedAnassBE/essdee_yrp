"""Helpers for real multi-connection transaction tests.

Frappe's normal test transaction is intentionally not committed. A concurrency
test is the exception: independent MariaDB connections cannot observe its
fixture or each other's successful changes until they commit. Callers must
delete every uniquely named fixture row before returning.
"""

import frappe


def commit_connection():
	"""Commit only the active connection used by a concurrency test."""
	frappe.db.commit()

