from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import patch

from frappe.utils.file_lock import LockTimeoutError

from essdee_yrp.migration import locking


class TestMigrationExecutionLock(TestCase):
	def test_allows_one_execution(self):
		wrapped = locking.exclusive_migration_run(lambda value: value + 1)
		with patch.object(locking, "filelock", return_value=nullcontext()):
			self.assertEqual(wrapped(2), 3)

	def test_rejects_an_overlapping_execution(self):
		wrapped = locking.exclusive_migration_run(lambda: self.fail("must not run"))
		with patch.object(
			locking, "filelock", side_effect=LockTimeoutError("already held")
		):
			with self.assertRaisesRegex(
				locking.MigrationAlreadyRunningError, "already running"
			):
				wrapped()
