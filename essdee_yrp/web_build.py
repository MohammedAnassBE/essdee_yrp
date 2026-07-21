"""Auto-build the /web SPA on deploy.

The essdee_yrp /web SPA is a standalone Vite project at ``apps/essdee_yrp/frontend``.
Its build output lands in ``essdee_yrp/public/frontend/`` (served at
``/assets/essdee_yrp/frontend/`` — Frappe symlinks ``{app}/public`` -> ``assets/{app}``).

That output is intentionally NOT committed to git — production builds it. Frappe's
``bench build`` only runs its own esbuild over ``*.bundle.js`` files (via
``yarn run production`` inside the frappe app) and does NOT build this Vite SPA,
so we build it here.

Wired from ``hooks.py`` as both ``after_migrate`` (via ``setup.after_migrate`` —
the guaranteed deploy step) and ``after_build`` (so ``bench build`` also refreshes
it). Same resilient entry point either way.

Design guarantees:
- **Never crashes the caller.** Every path is wrapped; a build failure logs a
  warning and returns, so it can never break ``bench migrate`` / ``bench build``.
- **Source-hash gated.** Rebuilds only when the SPA sources actually change
  (``frontend/src``, ``package.json``, ``yarn.lock``, ``vite.config.js``,
  ``index.html``, and the linked ``@yrp/web-engine`` source), so ordinary
  migrations don't pay for a full rebuild. The signature is stored in
  ``public/frontend/.build-hash``.
- **Installs deps only when missing** (``frontend/node_modules`` absent) using
  ``yarn install --frozen-lockfile``.
"""

import hashlib
import os
import shutil
import subprocess

import frappe

# apps/essdee_yrp/essdee_yrp  (this module's dir)
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
# apps/essdee_yrp  (app root — holds the frontend/ Vite project)
_APP_ROOT = os.path.dirname(_MODULE_DIR)

_FRONTEND = os.path.join(_APP_ROOT, "frontend")
_NODE_MODULES = os.path.join(_FRONTEND, "node_modules")
_OUTPUT = os.path.join(_MODULE_DIR, "public", "frontend")
_ENTRY_HTML = os.path.join(_OUTPUT, "index.html")
_HASH_FILE = os.path.join(_OUTPUT, ".build-hash")
# The @yrp/web-engine source the SPA bundles in — a change here also changes output.
_YRP_ENGINE_SRC = os.path.abspath(os.path.join(_APP_ROOT, "..", "yrp", "frontend", "src"))


def _log(msg, warning=False):
	line = f"[essdee_yrp /web build] {msg}"
	print(line)
	try:
		logger = frappe.logger("essdee_yrp")
		(logger.warning if warning else logger.info)(line)
	except Exception:
		pass


def build_web_spa():
	"""Resilient entry point for after_migrate / after_build. Never raises."""
	try:
		_build_web_spa()
	except Exception:
		# A build problem must never crash migrate/build. Log and move on.
		try:
			frappe.log_error(
				title="essdee_yrp /web build failed",
				message=frappe.get_traceback(),
			)
		except Exception:
			pass
		_log("skipped after an unexpected error — migrate/build continues", warning=True)


def _build_web_spa():
	if not os.path.isdir(_FRONTEND):
		_log("frontend/ not found; nothing to build")
		return

	yarn = shutil.which("yarn")
	if not yarn:
		_log("yarn not on PATH; skipping /web build (prod needs node + yarn)", warning=True)
		return

	signature = _source_signature()
	if _is_up_to_date(signature):
		_log("sources unchanged since last build; skipping rebuild")
		return

	if not os.path.isdir(_NODE_MODULES):
		_log("frontend/node_modules missing — running yarn install --frozen-lockfile")
		_run([yarn, "install", "--frozen-lockfile"])

	_log("building /web SPA (yarn build)…")
	_run([yarn, "build"])

	if not os.path.isfile(_ENTRY_HTML):
		_log("build finished but index.html is missing — not recording hash", warning=True)
		return

	_write_hash(signature)
	_log("/web SPA build complete")


def _run(cmd):
	"""Run a command in the frontend dir; raise (with tail output) on failure."""
	result = subprocess.run(
		cmd,
		cwd=_FRONTEND,
		capture_output=True,
		text=True,
	)
	if result.returncode != 0:
		tail = ((result.stdout or "")[-2000:] + "\n" + (result.stderr or "")[-2000:]).strip()
		raise RuntimeError(f"`{' '.join(cmd)}` failed (exit {result.returncode}):\n{tail}")


def _source_signature():
	"""sha256 over the SPA source inputs — stable, order-independent."""
	h = hashlib.sha256()
	files = []

	for name in ("package.json", "yarn.lock", "vite.config.js", "index.html"):
		p = os.path.join(_FRONTEND, name)
		if os.path.isfile(p):
			files.append(p)

	for tree in (os.path.join(_FRONTEND, "src"), _YRP_ENGINE_SRC):
		if os.path.isdir(tree):
			for dirpath, dirnames, filenames in os.walk(tree):
				dirnames.sort()
				for fn in sorted(filenames):
					files.append(os.path.join(dirpath, fn))

	for p in sorted(files):
		try:
			with open(p, "rb") as f:
				data = f.read()
		except OSError:
			continue
		h.update(p.encode("utf-8"))
		h.update(b"\0")
		h.update(data)

	return h.hexdigest()


def _is_up_to_date(signature):
	# The built entry must exist AND the signature must match. If the bundle was
	# wiped (fresh prod / cleared), rebuild even when a stale hash lingers.
	if not os.path.isfile(_ENTRY_HTML):
		return False
	return _read_hash() == signature


def _read_hash():
	try:
		with open(_HASH_FILE) as f:
			return f.read().strip()
	except OSError:
		return None


def _write_hash(signature):
	try:
		os.makedirs(_OUTPUT, exist_ok=True)
		with open(_HASH_FILE, "w") as f:
			f.write(signature)
	except OSError:
		pass
