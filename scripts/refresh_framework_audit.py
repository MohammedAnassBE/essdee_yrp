"""Re-run the entire framework audit, preserving the immutable full first pass.

This is a read-only diagnostic, not a migration or data repair. Application
results are retained with provenance; all framework rows are read again.
Both sites must remain isolated throughout the check.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from audit_framework_values import audit_framework, query
from audit_production_api_source_values import _connect, _load_site_config


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--audit', type=Path, required=True)
	parser.add_argument('--output', type=Path, required=True)
	args = parser.parse_args()
	audit_path, output = args.audit.resolve(), args.output.resolve()
	if output == audit_path or output.exists():
		raise ValueError('Use a new output path; the original audit must remain unchanged')
	original = audit_path.read_bytes()
	payload = json.loads(original)
	if not payload.get('read_only') or not payload.get('complete_application_scope'):
		raise ValueError('A complete first-pass application audit is required')
	bench = Path(payload['target']['bench'])
	site = payload['target']['site']
	source_bench = Path(payload['source']['bench'])
	source_site = payload['source']['site']
	for root, name in ((bench, site), (source_bench, source_site)):
		if not _load_site_config(root, name).get('maintenance_mode'):
			raise ValueError('Both sites must remain in maintenance mode')
	os.chdir(bench / 'sites')
	import frappe

	frappe.init(site=site, sites_path=str(bench / 'sites'))
	frappe.connect()
	try:
		from essdee_yrp.migration.config import get_migration_settings
		from essdee_yrp.migration.live import F15SourceBridge, build_live_schema_analysis

		settings = get_migration_settings()
		if settings.source_bench != source_bench or settings.source_site != source_site:
			raise ValueError('Configured source differs from the first-pass audit')
		plan, _schema = build_live_schema_analysis(settings, F15SourceBridge(settings))
		if not plan.ready:
			raise ValueError('Current schema plan is blocked')
		source_db, target_db = _connect(source_bench, source_site), _connect(bench, site)
		started = dt.datetime.now().astimezone().isoformat()
		try:
			for connection in (source_db, target_db):
				query(connection, 'SET SESSION TRANSACTION READ ONLY')
			manifest = query(target_db, 'SELECT framework_archive_json FROM '
				'`tabSD YRP MRP Data Migration` WHERE name=%s', (payload['migration_name'],))[0]
			framework = audit_framework(source_db, target_db, plan, payload['migration_name'],
				bench / 'sites' / site, _load_site_config(bench, site).get('encryption_key'),
				source_site_path=source_bench / 'sites' / source_site)
		finally:
			source_db.close()
			target_db.close()
		for root, name in ((bench, site), (source_bench, source_site)):
			if not _load_site_config(root, name).get('maintenance_mode'):
				raise ValueError('Site isolation changed during verification')
		payload['framework_audit_refresh'] = {
			'original_audit': str(audit_path),
			'original_sha256': hashlib.sha256(original).hexdigest(),
			'original_generated_on': payload['generated_on'],
			'original_framework_mismatches': payload['framework_history']['mismatch_count'],
			'started_on': started,
			'completed_on': dt.datetime.now().astimezone().isoformat(),
			'manifest_sha256': hashlib.sha256(manifest['framework_archive_json'].encode()).hexdigest(),
			'comparator_sha256': hashlib.sha256(Path(__file__).with_name('audit_framework_values.py').read_bytes()).hexdigest(),
			'method': 'All framework rows re-read with exact SQL numeric comparison; application and other auxiliary results unchanged from the complete isolated first pass',
		}
		payload['generated_on'] = payload['framework_audit_refresh']['completed_on']
		payload['framework_history'] = framework
		payload['summary']['framework_value_mismatches'] = framework['mismatch_count']
		from essdee_yrp.patches.backfill_deterministic_valuation_lineage import get_valuation_lineage_readiness

		payload['valuation_lineage_readiness'] = get_valuation_lineage_readiness()
		payload['framework_audit_refresh']['additional_read_only_check'] = 'Current new valuation-link readiness; separate from original source-field parity'
		with output.open('x', encoding='utf-8') as stream:
			json.dump(payload, stream, indent=2, default=str)
		print(json.dumps({'framework': {key: framework[key] for key in
			('status', 'rows', 'field_values', 'mismatch_count', 'numeric_representation_matches')},
			'output': str(output)}, indent=2), flush=True)
		return int(bool(framework['mismatch_count']))
	finally:
		frappe.db.rollback()
		frappe.destroy()


if __name__ == '__main__':
	raise SystemExit(main())
