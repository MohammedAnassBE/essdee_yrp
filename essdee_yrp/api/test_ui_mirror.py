# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

"""Client-mirror drift check (2026-07-17 review finding).

``yrp.yrp.api.ui_config`` keeps two hand-maintained constants that CLAIM to
mirror this app's frontend:

- ``BLOCK_PROP_KEYS`` — "the defineProps list of every registered block"
  (frontend/src/blocks/index.js registrations + each component's defineProps;
  summary-tiles / calculator-panel ship from the @yrp/web-engine package at
  apps/yrp/frontend/src).
- ``HOME_QUEUE_METRICS`` — "the server mirror of HomeQueues.vue
  METRIC_TO_QUEUE".

``gen-layout-schema.sh --check`` guards the SERVER side of the mirror
(constants → LAYOUT_SCHEMA.json), but nothing guarded the CLIENT edge: a
frontend dev adding a defineProps entry or a fifth queue metric silently
un-mirrors the validator, which then draws false "not a prop of block type" /
"renders NOTHING" warnings on every save and teaches a stale vocabulary via
the catalog. This test parses the ACTUAL frontend sources (no build step, no
node) and fails on either direction of drift.

House rule: no ``frappe.db.commit()`` — read-only file parsing, no writes.
"""

import os
import re

import frappe
from frappe.tests import IntegrationTestCase

from yrp.yrp.api.ui_config import BLOCK_PROP_KEYS, HOME_QUEUE_METRICS

# Props the server knows that are DELIBERATELY absent from the client's
# defineProps: RESERVED knobs (validated + stored, consumed by nothing yet —
# Track 1 item 11 wires or deletes them). Anything else on the server side
# but not in defineProps is drift.
SERVER_ONLY_RESERVED_PROPS = {"home-queues": {"maxCards"}}


def _frontend_dir(app):
	"""apps/<app>/frontend/src — the Vue sources next to the app package."""
	return os.path.join(os.path.dirname(frappe.get_app_path(app)), "frontend", "src")


def _read(path):
	with open(path, encoding="utf-8") as f:
		return f.read()


def _strip_line_comments(src):
	"""Drop // comments (none of the parsed files use // inside strings)."""
	return re.sub(r"//[^\n]*", "", src)


def _parse_object_keys(src, opener_re):
	"""Top-level keys of the FIRST object literal opened by ``opener_re``.

	Walks the braces with a quote-aware depth counter, collecting identifiers
	followed by ``:`` at depth 1 — robust against nested defaults like
	``{ type: Array, default: () => [...] }``.
	"""
	m = re.search(opener_re, src)
	if not m:
		return None
	i = src.index("{", m.start())
	depth = 0
	quote = None
	keys = []
	token = ""
	at_key_position = True  # after '{' or ',' at depth 1
	while i < len(src):
		ch = src[i]
		if quote:
			if ch == "\\":
				i += 2
				continue
			if ch == quote:
				quote = None
		elif ch in "'\"`":
			quote = ch
		elif ch in "{[(":
			depth += 1
			if depth == 2:
				at_key_position = False
		elif ch in "}])":
			depth -= 1
			if depth == 0:
				break
			if depth == 1:
				token = ""
		elif depth == 1:
			if ch == ",":
				at_key_position = True
				token = ""
			elif ch == ":":
				if at_key_position and token.strip():
					keys.append(token.strip())
				at_key_position = False
				token = ""
			elif not ch.isspace():
				token += ch
			elif token:
				token += ch
		i += 1
	return keys


class TestUIClientMirror(IntegrationTestCase):
	"""BLOCK_PROP_KEYS / HOME_QUEUE_METRICS vs the real frontend sources."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.host_blocks = os.path.join(_frontend_dir("essdee_yrp"), "blocks")
		cls.engine_src = _frontend_dir("yrp")
		cls.index_js = _read(os.path.join(cls.host_blocks, "index.js"))

	def _registrations(self):
		"""block type -> absolute component file path, from index.js."""
		local = dict(re.findall(r'import\s+(\w+)\s+from\s+"\./([\w.]+\.vue)"', self.index_js))
		engine_import = re.search(r'import\s*\{([^}]*)\}\s*from\s*"@yrp/web-engine"', self.index_js)
		engine_names = (
			{n.strip() for n in engine_import.group(1).split(",") if n.strip()}
			if engine_import
			else set()
		)
		out = {}
		for block_type, component in re.findall(
			r'registerBlock\("([\w-]+)",\s*\{\s*component:\s*(\w+)', self.index_js
		):
			if component in local:
				out[block_type] = os.path.join(self.host_blocks, local[component])
			elif component in engine_names:
				out[block_type] = os.path.join(self.engine_src, component + ".vue")
			else:
				self.fail(f"index.js registers '{block_type}' with unresolvable component {component}")
		return out

	def test_registered_block_types_match_block_prop_keys(self):
		registrations = self._registrations()
		self.assertEqual(
			set(registrations),
			set(BLOCK_PROP_KEYS),
			"blocks/index.js registrations and ui_config.BLOCK_PROP_KEYS name "
			"different block types — update the server mirror (and regenerate "
			"LAYOUT_SCHEMA.json) or the registration",
		)

	def test_block_prop_keys_mirror_each_components_define_props(self):
		for block_type, component_file in sorted(self._registrations().items()):
			self.assertTrue(os.path.exists(component_file), component_file)
			src = _strip_line_comments(_read(component_file))
			client_props = _parse_object_keys(src, r"defineProps\s*\(\s*\{")
			self.assertIsNotNone(
				client_props, f"{component_file}: could not locate defineProps({{...}})"
			)
			client, server = set(client_props), set(BLOCK_PROP_KEYS[block_type])
			self.assertEqual(
				client - server,
				set(),
				f"'{block_type}': defineProps carries props the server mirror lacks — "
				f"validate_config would FALSELY warn 'not a prop of block type' on them; "
				f"extend BLOCK_PROP_KEYS + regenerate LAYOUT_SCHEMA.json",
			)
			self.assertEqual(
				server - client,
				SERVER_ONLY_RESERVED_PROPS.get(block_type, set()),
				f"'{block_type}': BLOCK_PROP_KEYS carries props defineProps lacks that are "
				f"not documented RESERVED — stale server mirror",
			)

	def test_home_queue_metrics_mirror_metric_to_queue(self):
		src = _read(os.path.join(self.host_blocks, "HomeQueues.vue"))
		keys = _parse_object_keys(_strip_line_comments(src), r"const\s+METRIC_TO_QUEUE\s*=\s*\{")
		self.assertIsNotNone(keys, "HomeQueues.vue: could not locate METRIC_TO_QUEUE")
		self.assertEqual(len(keys), len(set(keys)), f"duplicate METRIC_TO_QUEUE keys: {keys}")
		self.assertEqual(
			set(keys),
			set(HOME_QUEUE_METRICS),
			"HomeQueues.vue METRIC_TO_QUEUE and ui_config.HOME_QUEUE_METRICS have "
			"drifted — a home-queues stats save would warn falsely (or a new queue "
			"metric would draw the 'renders NOTHING' warning); update the mirror "
			"and regenerate LAYOUT_SCHEMA.json",
		)
