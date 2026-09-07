import json
import unittest
from unittest.mock import patch

from essdee_yrp.boot import boot_session


class TestDeskBootDefaults(unittest.TestCase):
	def test_missing_defaults_use_core_user_scoped_values(self):
		fields = [{"fieldname": "company", "default": "Example Company"}]
		with patch("essdee_yrp.boot.get_session_default_values", return_value=json.dumps(fields)) as reader:
			bootinfo = {}
			boot_session(bootinfo)
			self.assertEqual(bootinfo["session_defaults"], fields)
			reader.assert_called_once_with()

	def test_existing_defaults_are_preserved_including_empty_list(self):
		for fields in ([], [{"fieldname": "company", "default": "Configured"}]):
			with self.subTest(fields=fields), patch("essdee_yrp.boot.get_session_default_values") as reader:
				bootinfo = {"session_defaults": fields}
				boot_session(bootinfo)
				self.assertIs(bootinfo["session_defaults"], fields)
				reader.assert_not_called()

	def test_empty_configuration_has_a_safe_real_empty_list(self):
		with patch("essdee_yrp.boot.get_session_default_values", return_value="[]"):
			bootinfo = {"session_defaults": None}
			boot_session(bootinfo)
			self.assertEqual(bootinfo["session_defaults"], [])

	def test_malformed_configuration_is_not_silently_swallowed(self):
		with patch("essdee_yrp.boot.get_session_default_values", return_value="{}"):
			with self.assertRaises(ValueError):
				boot_session({})
