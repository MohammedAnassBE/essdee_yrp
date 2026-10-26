import frappe

from essdee_yrp.migration.cpd_import.importer import Importer
from essdee_yrp.migration.cpd_import.report import Verifier, get_report_lines, print_summary, write_report


def run():
	"""Import for real: commit per Process Cost / Stock Entry / Reconciliation and per lot chain."""
	frappe.db.rollback()
	importer = Importer(commit=True)
	passed = importer.run()
	verification = Verifier(importer).run() if passed else []
	path = write_report(get_report_lines(importer, "execute", verification), "execute")
	print_summary(importer, "execute", path)
