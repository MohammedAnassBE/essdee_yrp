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
- ``COMPOSITE_PRIMITIVES`` + the COMPOSITE_* binding-grammar constants — the
  Track-1-item-3 deep mirror of the ENGINE grammar
  (``apps/yrp/frontend/src/composite/grammar.js``): primitive names,
  container-ness, prop kinds/enums/ranges/defaults, showIf ops, formatter
  names, forbidden path segments and the security regexes.

``gen-layout-schema.sh --check`` guards the SERVER side of the mirror
(constants → LAYOUT_SCHEMA.json), but nothing guarded the CLIENT edge: a
frontend dev adding a defineProps entry or a fifth queue metric silently
un-mirrors the validator, which then draws false "not a prop of block type" /
"renders NOTHING" warnings on every save and teaches a stale vocabulary via
the catalog. This test parses the ACTUAL frontend sources (no build step, no
node) and fails on either direction of drift.

House rule: no ``frappe.db.commit()`` — read-only file parsing, no writes.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

import frappe
from frappe.tests import IntegrationTestCase

from yrp.yrp.api.ui_config import (
	BLOCK_PROP_KEYS,
	COMPOSITE_BIND_PATH_RE,
	COMPOSITE_FORBIDDEN_PATH_SEGMENTS,
	COMPOSITE_FORMATS,
	COMPOSITE_MAX_DEPTH,
	COMPOSITE_MAX_NODES,
	COMPOSITE_PRIMITIVES,
	COMPOSITE_SHOWIF_OPS,
	COMPOSITE_SITE_FILE_RE,
	HOME_QUEUE_METRICS,
	ICON_RE,
	LIST_VIEW_KEYS,
)

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


def _balanced(src, opener_re, open_ch="{", close_ch="}"):
	"""The full balanced ``{...}`` block opened by ``opener_re`` (quote-aware —
	strings may carry braces). Module-level twin of the class helper, so the
	wizard tests below can extract a JS function body standalone."""
	m = re.search(opener_re, src)
	if not m:
		return None
	start = src.index(open_ch, m.start())
	depth = 0
	quote = None
	i = start
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
		elif ch == open_ch:
			depth += 1
		elif ch == close_ch:
			depth -= 1
			if depth == 0:
				return src[start : i + 1]
		i += 1
	return None


class TestDcWizardStepsEntry(IntegrationTestCase):
	"""dcEntry 'wizard-steps' reachability + blocked-save reveal (2026-07-18
	review findings). Both are FRONTEND presentation seams with no standalone
	JS module to run, so — like the block-prop mirror above — they are proven by
	parsing the ACTUAL .vue sources (no build, no node). House rule: no
	``frappe.db.commit()`` — read-only file parsing."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		dyn = os.path.join(_frontend_dir("essdee_yrp"), "views", "dynamic")
		cls.host_src = _read(os.path.join(dyn, "DocOverlayHost.vue"))
		cls.detail_src = _read(os.path.join(dyn, "DocDetail.vue"))

	def test_wizard_step1_is_not_a_dead_end(self):
		"""Finding 1: step 1 (WO quick-pick) must offer a forward path that does
		NOT depend on tapping a chip — the strip lists only the 8 most-recent
		submitted WOs, so the target WO may not appear (or the strip is empty),
		and the form's own work_order Link lives in step 2. Assert the step-1
		panel carries a control that advances to step 2 on its own (Continue),
		scoped to the step-1 region so the step-2 '← Back' button can't satisfy
		it."""
		start = self.host_src.index("v-show=\"wizardStep === '1'\"")
		end = self.host_src.index("v-show=\"wizardStep === '2'\"")
		step1 = self.host_src[start:end]
		self.assertIn(
			"@click=\"wizardStep = '2'\"",
			step1,
			"wizard-steps step 1 has no chip-independent forward path — it is a "
			"dead-end whenever the target Work Order isn't one of the recent-8 chips "
			"(or the strip is empty). Restore the 'Continue to form' button so the "
			"form's own work_order Link (step 2) stays reachable.",
		)

	def test_wizard_save_reveals_a_blocked_form(self):
		"""Finding 2: on the Review step the form (step 2) is display:none, so a
		blocked save's red field + banner are invisible and only a toast shows.
		The fix is a two-part contract: onSave RESOLVES a boolean (true=success,
		false=blocked/rejected) and onWizardSave AWAITS it and returns to step 2
		on a false result. Assert both halves so neither can silently regress."""
		on_save = _balanced(self.detail_src, r"async function onSave\(\)\s*\{")
		self.assertIsNotNone(on_save, "DocDetail.vue: could not locate onSave()")
		self.assertIn(
			"return true",
			on_save,
			"onSave no longer signals a successful save — the wizard host cannot "
			"tell success from a block",
		)
		self.assertIn(
			"return false",
			on_save,
			"onSave no longer signals a BLOCKED save (missing required / server "
			"reject) — the wizard host would strand the user on the Review step with "
			"only a toast and an invisible red field",
		)
		# The missing-required guard specifically must return the blocked signal
		# (not a bare early return that the host reads as success).
		guard = on_save[
			on_save.index("const missing = firstMissingRequired()") : on_save.index(
				"missingField.value = null"
			)
		]
		self.assertIn(
			"return false",
			guard,
			"the firstMissingRequired guard must resolve false so the host reveals "
			"the hidden form",
		)
		on_wizard = _balanced(self.host_src, r"async function onWizardSave\(\)\s*\{")
		self.assertIsNotNone(
			on_wizard,
			"DocOverlayHost.vue: onWizardSave must be async (it awaits the exposed "
			"save()) — a non-async handler cannot read the blocked/success result",
		)
		self.assertIn("createRef.value?.save", on_wizard, "onWizardSave must fire the exposed save()")
		self.assertIn(
			"=== false",
			on_wizard,
			"onWizardSave must branch on the blocked (false) result",
		)
		self.assertIn(
			'wizardStep.value = "2"',
			on_wizard,
			"onWizardSave must return to step 2 on a blocked save so the form's "
			"banner + reddened field become visible",
		)


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

	def test_composite_caps_mirror_engine_grammar(self):
		"""ui_config.COMPOSITE_MAX_NODES/DEPTH are a hand-maintained mirror of
		the engine grammar (apps/yrp/frontend/src/composite/grammar.js) — the
		Track-1-item-1 third copy. Either side drifting breaks the caps story
		the item-3 server validator and the catalog document."""
		src = _strip_line_comments(_read(os.path.join(self.engine_src, "composite", "grammar.js")))
		caps = {}
		for name in ("COMPOSITE_MAX_NODES", "COMPOSITE_MAX_DEPTH"):
			m = re.search(rf"export\s+const\s+{name}\s*=\s*(\d+)", src)
			self.assertIsNotNone(m, f"grammar.js: could not locate {name}")
			caps[name] = int(m.group(1))
		self.assertEqual(
			caps,
			{"COMPOSITE_MAX_NODES": COMPOSITE_MAX_NODES, "COMPOSITE_MAX_DEPTH": COMPOSITE_MAX_DEPTH},
			"composite caps drifted between engine grammar.js and the ui_config "
			"server mirror — update both sides together (and regenerate LAYOUT_SCHEMA.json)",
		)

	# ── Track 1 item 3: the DEEP grammar mirror (validator vs grammar.js) ──

	def _grammar_js(self):
		return _read(os.path.join(self.engine_src, "composite", "grammar.js"))

	@staticmethod
	def _extract_braced(src, opener_re, open_ch="{", close_ch="}"):
		"""The full balanced ``{...}``/``[...]`` literal opened by
		``opener_re``, quote-aware (strings may contain braces)."""
		m = re.search(opener_re, src)
		if not m:
			return None
		start = src.index(open_ch, m.start())
		depth = 0
		quote = None
		i = start
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
			elif ch == open_ch:
				depth += 1
			elif ch == close_ch:
				depth -= 1
				if depth == 0:
					return src[start : i + 1]
			i += 1
		return None

	@classmethod
	def _js_object_to_python(cls, literal):
		"""JSON-ify a boring declarative JS object literal (the grammar file
		keeps itself 'declarative and boring' for exactly this consumer):
		strip // comments, quote identifier keys, drop trailing commas."""
		text = _strip_line_comments(literal)
		text = re.sub(r"([{\[,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)\s*:", r'\1"\2":', text)
		text = re.sub(r",(\s*[}\]])", r"\1", text)
		return json.loads(text)

	def _parsed_primitives(self):
		"""grammar.js COMPOSITE_PRIMITIVES as a Python dict, with the GAP/ALIGN
		shared-const references resolved first. Comments are stripped BEFORE
		brace extraction — an apostrophe inside a comment would otherwise open
		a phantom string for the quote-aware walker."""
		src = _strip_line_comments(self._grammar_js())
		consts = {}
		for name in ("GAP", "ALIGN"):
			literal = self._extract_braced(src, rf"const\s+{name}\s*=\s*\{{")
			self.assertIsNotNone(literal, f"grammar.js: could not locate const {name}")
			consts[name] = literal
		block = self._extract_braced(src, r"export\s+const\s+COMPOSITE_PRIMITIVES\s*=\s*\{")
		self.assertIsNotNone(block, "grammar.js: could not locate COMPOSITE_PRIMITIVES")
		for name, literal in consts.items():
			block = re.sub(rf"(:\s*){name}\b", lambda m, lit=literal: m.group(1) + lit, block)
		return self._js_object_to_python(block)

	def _parsed_array(self, name):
		src = self._grammar_js()
		literal = self._extract_braced(
			src, rf"export\s+const\s+{name}\s*=\s*\[", open_ch="[", close_ch="]"
		)
		self.assertIsNotNone(literal, f"grammar.js: could not locate {name}")
		return json.loads(_strip_line_comments(literal))

	def _parsed_regex_source(self, name):
		"""The ``/^...$/`` literal's source with the anchors stripped and JS
		``\\/`` unescaped — the shape a Python fullmatch pattern carries."""
		m = re.search(rf"export\s+const\s+{name}\s*=\s*/(.+?)/\n", self._grammar_js())
		self.assertIsNotNone(m, f"grammar.js: could not locate regex {name}")
		source = m.group(1)
		source = re.sub(r"^\^", "", source)
		source = re.sub(r"\$$", "", source)
		return source.replace("\\/", "/")

	def test_composite_primitive_registry_mirrors_engine_grammar(self):
		"""The item-3 validator's COMPOSITE_PRIMITIVES (names, container-ness,
		prop names, kinds, enum members, int ranges, defaults) is a
		hand-maintained deep mirror of grammar.js — the exact third-copy class
		the review amendment guards. Compared value-for-value, both ways."""
		engine = self._parsed_primitives()
		server = json.loads(json.dumps(COMPOSITE_PRIMITIVES))  # tuples -> lists
		self.assertEqual(
			engine,
			server,
			"COMPOSITE_PRIMITIVES drifted between engine grammar.js and the "
			"ui_config server mirror — update both sides together, regenerate "
			"LAYOUT_SCHEMA.json, and (for a BREAKING change) bump "
			"COMPOSITE_GRAMMAR_VERSION + ship a COMPOSITE_TREE_UPGRADERS entry",
		)

	def test_composite_binding_grammar_mirrors_engine(self):
		"""showIf ops, formatter names, forbidden path segments and the three
		security regexes (bind path, site file, icon) must agree between the
		engine grammar and the server validator."""
		self.assertEqual(self._parsed_array("SHOWIF_OPS"), list(COMPOSITE_SHOWIF_OPS))
		self.assertEqual(self._parsed_array("COMPOSITE_FORMATS"), list(COMPOSITE_FORMATS))
		self.assertEqual(
			self._parsed_array("FORBIDDEN_PATH_SEGMENTS"),
			list(COMPOSITE_FORBIDDEN_PATH_SEGMENTS),
		)
		self.assertEqual(
			self._parsed_regex_source("BIND_PATH_RE"),
			COMPOSITE_BIND_PATH_RE.pattern,
			"bind-path grammar drifted",
		)
		self.assertEqual(
			self._parsed_regex_source("SITE_FILE_RE"),
			COMPOSITE_SITE_FILE_RE.pattern,
			"site-file grammar drifted",
		)
		self.assertEqual(
			self._parsed_regex_source("COMPOSITE_ICON_RE"),
			ICON_RE.pattern,
			"icon grammar drifted (the server validator reuses ICON_RE)",
		)

	def test_card_template_seam_stays_wired_end_to_end(self):
		"""Track 1 item 2 drift guard. The per-row cardTemplate seam has FOUR
		client surfaces (ListCards/ListKanban accept the prop; RecordList and
		DynamicListPage pass it into BOTH renderers) and TWO server vocabulary
		entries (BLOCK_PROP_KEYS['record-list'] + LIST_VIEW_KEYS). Any side
		dropping the knob silently un-mirrors the validator — the exact
		documented third-copy failure class the review amendment guards."""
		self.assertIn("cardTemplate", BLOCK_PROP_KEYS["record-list"])
		self.assertIn("cardTemplate", LIST_VIEW_KEYS)
		src_dir = _frontend_dir("essdee_yrp")
		for rel in ("components/list/ListCards.vue", "components/list/ListKanban.vue"):
			path = os.path.join(src_dir, rel)
			props = _parse_object_keys(
				_strip_line_comments(_read(path)), r"defineProps\s*\(\s*\{"
			)
			self.assertIn(
				"cardTemplate",
				props or [],
				f"{rel}: defineProps lost the cardTemplate prop — the seam's renderer "
				"side is gone while the server vocabulary still documents it",
			)
		for rel in ("blocks/RecordList.vue", "views/dynamic/DynamicListPage.vue"):
			src = _read(os.path.join(src_dir, rel))
			self.assertEqual(
				src.count(":card-template="),
				2,
				f"{rel}: must pass :card-template= to BOTH ListCards and ListKanban — "
				"a dropped pass-through makes the validated knob silently dead",
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


class TestStatusColorPrototypeSafety(IntegrationTestCase):
	"""Composite badge.status runtime-crash guard (2026-07-18 review finding).

	``statusColors.statusColor`` did ``STATUS_COLORS[status] || STATUS_FALLBACK``
	on a plain object LITERAL, so a status string equal to an inherited
	``Object.prototype`` member ('constructor', 'toString', 'hasOwnProperty',
	'valueOf', '__proto__', 'isPrototypeOf', 'propertyIsEnumerable',
	'toLocaleString', …) resolved to a truthy inherited FUNCTION instead of the
	grey fallback; ``statusColor`` then read ``fn['light']`` = undefined and
	``statusTint`` crashed on ``undefined.slice(1)``. The composite layer makes
	this newly reachable: ``badge.status`` is a BINDABLE prop wired to arbitrary
	row data, and a Work Order whose bound field is literally valued
	'constructor'/'valueOf' arrives as clean DB data the server validator cannot
	reject — the throw then propagates through the un-boundaried routed
	cards/kanban list (DynamicListPage has no onErrorCaptured) and blanks the
	whole list for every viewer. Fix: own-property lookup only.

	This is a JS RUNTIME crash, so the regression is proven by RUNNING the
	shipped engine module (statusColors.js is import-free — it loads standalone
	under bare node). A source parse cannot prove no-throw. Skips only if node
	is genuinely absent, which would already break this bench's node-based
	verify pipeline (npm build, lint-layout.mjs, verify-ui.mjs).

	House rule: no ``frappe.db.commit()`` — reads a file + runs node, no writes.
	"""

	# ESM harness (top-level await, run via `node --input-type=module -e`):
	# every inherited Object.prototype member name IS a crash input, so drive
	# the full own-property-names list plus an ordinary unknown ('Foo') and ''.
	HARNESS = r"""
	const { statusColor, statusChipStyle } = await import(process.env.SC_URL);
	const GREY_LIGHT = "#6b7280";
	const GREY_BG = "rgba(107, 114, 128, 0.14)";
	const inputs = [...Object.getOwnPropertyNames(Object.prototype), "Foo", ""];
	for (const s of inputs) {
		const style = statusChipStyle(s, false); // pre-fix: throws on prototype names
		if (statusColor(s, false) !== GREY_LIGHT || style.background !== GREY_BG) {
			console.error("bad-fallback " + JSON.stringify(s) + " " + JSON.stringify(style));
			process.exit(2);
		}
	}
	// the own-property guard must NOT clobber genuine registry hits
	if (statusColor("Draft", false) !== "#b45309" || statusColor("Completed", true) !== "#34d399") {
		console.error("named-status-broken");
		process.exit(3);
	}
	console.log("OK");
	"""

	def test_bound_status_of_prototype_name_does_not_crash(self):
		node = shutil.which("node") or shutil.which("nodejs")
		if not node:
			self.skipTest("node not on PATH — JS runtime regression cannot run")
		status_colors = os.path.join(_frontend_dir("yrp"), "statusColors.js")
		self.assertTrue(os.path.exists(status_colors), status_colors)
		env = dict(os.environ, SC_URL=pathlib.Path(status_colors).as_uri())
		proc = subprocess.run(
			[node, "--input-type=module", "-e", self.HARNESS],
			capture_output=True,
			text=True,
			env=env,
			timeout=30,
			check=False,
		)
		self.assertEqual(
			proc.returncode,
			0,
			"statusColor crashes or mis-falls-back on an inherited-prototype status "
			"name — composite badge.status binds arbitrary row data, so a field valued "
			"'constructor'/'valueOf'/'__proto__' would tear down the routed cards/kanban "
			f"list. rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}",
		)
		self.assertIn("OK", proc.stdout)
