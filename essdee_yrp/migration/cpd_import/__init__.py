"""One-off: import the submitted CPD site docs (data/import_data.json) into this site.

Dry run (everything runs, then rolls back):
	bench --site SITE execute essdee_yrp.migration.cpd_import.dry_run.run
Execute (same path, commits per doc / lot; safe to repeat via the "CPD import from <old>" marker):
	bench --site SITE execute essdee_yrp.migration.cpd_import.execute.run
Reports go to sites/SITE/private/cpd_import/.
"""
