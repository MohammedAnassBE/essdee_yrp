import frappe

from essdee_yrp.migration.cpd_import.importer import Importer
from essdee_yrp.migration.cpd_import.report import (
	Verifier,
	get_report_lines,
	print_summary,
	table,
	write_report,
)
from essdee_yrp.migration.cpd_import.side_effects import (
	DryRunGuard,
	get_new_jobs,
	get_rows_created_since,
	get_snapshot,
	get_snapshot_diff,
)


def run(ignore_markers=False):
	"""Run the whole import in one transaction, report it, then roll everything back.

	`ignore_markers=True` is a test switch: it re-imports docs that already carry a CPD marker.
	"""
	mode = "dry-run-ignore-markers" if ignore_markers else "dry-run"
	frappe.db.rollback()
	before = get_snapshot()
	importer = Importer(commit=False, ignore_markers=bool(ignore_markers))
	try:
		with DryRunGuard() as guard:
			passed = importer.run()
			verification = Verifier(importer).run() if passed else []
	finally:
		frappe.db.rollback()
	after = get_snapshot()
	diff = get_snapshot_diff(before, after)
	changed = [row for row in diff if row[-1] != "same"]
	new_jobs = get_new_jobs(before, after)
	proof = [
		"## Side-effect proof (before vs after the rollback)\n",
		f"Rows changed: {len(changed)} of {len(diff)}. Tables show [count, max(modified), CHECKSUM TABLE].\n",
		*table(["Section", "Key", "Before", "After", "Check"], diff),
		"Rows created in changed tables while the dry run was open (other sessions on the site):\n",
		*table(
			["Doctype", "Name", "Creation", "Owner", "Reference", "Reference name"],
			[
				r
				for row in changed
				if row[0] == "tables"
				for r in get_rows_created_since(row[1], before["at"])
			],
		),
	]
	path = write_report(
		get_report_lines(importer, mode, verification, [*guard.get_report_lines(), *proof]), mode
	)
	print_summary(importer, mode, path)
	print(
		"GUARD commits skipped",
		len(guard.commits),
		"blocked",
		len(guard.blocked),
		"jobs intercepted",
		len(guard.jobs),
		"realtime intercepted",
		len(guard.realtime),
	)
	print("SIDE EFFECTS", "none" if not changed else changed)
	print("NEW RQ JOBS", new_jobs or "none")
