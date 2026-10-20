"""Read-only C1-C4 parity against mrp3.site; two filters per report.

Run with frappe-16/env/bin/python scripts/planning_web_mrp_parity.py.
Uses the independently audited page normalizer from report-compare. Both DB
sessions are READ ONLY and rolled back. Raw output and differences are saved.
"""
import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

BENCHES = Path('/home/anas/pilot/benches')
CASES = [
    ('C1-a', 'inhouse-quantity-rep', {'lot': 'JB2627-016', 'process': 'Stitching'}),
    ('C1-b', 'inhouse-quantity-rep', {'lot': 'C0826-57', 'process': 'Cutting'}),
    ('C2-a', 'colour-wise-diff-rep', {'lot': 'C0826-57', 'process_list': ['Yolk Fusing', 'Bottom Fusing']}),
    ('C2-b', 'colour-wise-diff-rep', {'lot': 'JB2627-016', 'process_list': []}),
    ('C3-a', 'work-in-progress-rep', {'lot': ['F0726-05/1 W PJ 3'], 'lot_status': 'Open', 'from_date': '2026-09-14', 'to_date': '2026-09-14'}),
    ('C3-b', 'work-in-progress-rep', {'lot': ['F0726-05/1 W PJ 3'], 'lot_status': 'Open', 'from_date': '2026-09-14', 'to_date': '2026-09-15'}),
    ('C4-a', 'process-pending', {'lot': ['F0726-05/1 W PJ 3'], 'lot_status': 'Open', 'process': 'Stitching'}),
    ('C4-b', 'process-pending', {'lot': ['F0726-05/1 W PJ 2'], 'lot_status': 'Open', 'process': 'Stitching'}),
]
MODULES = {'C1': 'inhouse_quantity', 'C2': 'colour_wise_diff', 'C3': 'work_in_progress', 'C4': 'process_pending'}


def child(side, output):
    import frappe
    bench = BENCHES / ('frappe-15' if side == 'mrp' else 'frappe-16')
    os.chdir(bench / 'sites')
    frappe.init(site='mrp3.site' if side == 'mrp' else 'erp-migration-test.site')
    frappe.connect()
    frappe.set_user('Administrator')
    frappe.db.sql('SET TRANSACTION READ ONLY')
    results = {}
    try:
        for case, page, filters in CASES:
            filters = json.loads(json.dumps(filters))
            if side == 'mrp':
                from production_api import utils
                if case.startswith('C1'):
                    result = utils.get_inhouse_qty(**filters)
                elif case.startswith('C2'):
                    filters['process_list'] = [{'process_name': p} for p in filters['process_list']]
                    result = utils.get_colour_wise_diff_report(**filters)
                else:
                    kwargs = dict(category='', status=filters['lot_status'], lot_list_val=filters['lot'], item_list=[])
                    if case.startswith('C3'):
                        result = utils.get_work_in_progress_report(**kwargs, process_list=[], from_date=filters['from_date'], to_date=filters['to_date'])
                    else:
                        result = utils.get_sewing_progress_report(**kwargs, process=filters['process'])
            else:
                module = importlib.import_module('essdee_yrp.planning.reports.' + MODULES[case[:2]])
                result = module.run(filters)
                if case.startswith('C3'):
                    from essdee_yrp.merch.reports import run_work_in_progress
                    results[case + '-merch'] = run_work_in_progress(filters)
            results[case] = result
        output.write_text(json.dumps(results, indent=2, default=str))
    finally:
        frappe.db.rollback()
        frappe.destroy()


def run(out, evidence_root):
    out.mkdir(parents=True, exist_ok=True)
    for side, version in [('mrp', 'frappe-15'), ('erp', 'frappe-16')]:
        subprocess.run([str(BENCHES / version / 'env/bin/python'), str(Path(__file__).resolve()), '--side', side, '--out', str(out)], check=True)
    sys.path.insert(0, str(evidence_root))
    from compare_pages_shard4 import cube
    source = json.loads((out / 'mrp.json').read_text())
    target = json.loads((out / 'erp.json').read_text())
    summaries = []
    for case, page, filters in CASES:
        for key in ([case, case + '-merch'] if case.startswith('C3') else [case]):
            a = cube(page, source[case])
            b = cube(page, target[key], erp=True)
            differences = []
            for cell in sorted(a.keys() | b.keys()):
                av, bv = a.get(cell), b.get(cell)
                if cell not in a and isinstance(bv, (int, float)): av = 0
                if cell not in b and isinstance(av, (int, float)): bv = 0
                equal = abs(av - bv) < .001 if isinstance(av, (int, float)) and isinstance(bv, (int, float)) else av == bv
                if not equal: differences.append({'cell': json.loads(cell), 'mrp': av, 'erp': bv})
            if case.startswith('C2'):
                expected_rows = [(colour, label) for colour, group in source[case]['values'].items() for section in ('cut_rows', 'against_cut_rows', 'sew_rows', 'against_sew_rows') for label in group['rows'][section]]
                actual_rows = [(row['colour'], row['process']) for row in target[key]['result']]
                if expected_rows != actual_rows:
                    differences.append({'row_sequence_mrp': expected_rows, 'row_sequence_erp': actual_rows})
                if source[case]['sizes'] != [column['label'] for column in target[key]['columns'] if column['fieldname'].startswith('size_')]:
                    differences.append({'size_column_order': 'different'})
            if case.startswith('C4'):
                erp_rows = {r['lot']: r for r in target[key]['result'] if not r.get('is_total_row')}
                for row in source[case]['rows']:
                    for supplier, qty in row['supplier_qty'].items():
                        if qty:
                            expected = row['supplier_pending_days'].get(supplier)
                            actual = erp_rows[row['lot']].get('supplier_pending_days', {}).get(supplier)
                            if expected != actual: differences.append({'age': supplier, 'mrp': expected, 'erp': actual})
            summaries.append({'case': key, 'filters': filters, 'mrp_cells': len(a), 'erp_cells': len(b), 'different_cells': len(differences), 'differences': differences})
    (out / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    print(json.dumps([{k: v for k, v in row.items() if k != 'differences'} for row in summaries], indent=2))
    return int(any(row['different_cells'] for row in summaries))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--side', choices=['mrp', 'erp'])
    parser.add_argument('--out', type=Path, default=Path('/home/anas/report-build/port/parity/planning-web-worker4'))
    parser.add_argument('--evidence-root', type=Path, default=Path('/home/anas/report-compare'))
    args = parser.parse_args()
    if args.side:
        child(args.side, args.out / (args.side + '.json'))
    else:
        raise SystemExit(run(args.out.resolve(), args.evidence_root))
