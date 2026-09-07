"""Independent physical GRN coverage and commercial-value checks for WO PIs.

These checks do not call Fetch GRN or the migration projection builder. Original
positive GRN quantities must survive exactly per invoice/variant/UOM/lot/set.
Derived rate/value checks allow only a stated bound for nine-decimal storage.
"""

import json
from collections import defaultdict
from decimal import Decimal


def number(value):
	return Decimal(str(value or 0))


def combination(value):
	if value in (None, ''):
		return '{}'
	if isinstance(value, str):
		value = json.loads(value)
	return json.dumps(value or {}, sort_keys=True, separators=(',', ':'))


def physical_key(row):
	return (row['invoice'], row['item'], row.get('uom') or '', row.get('lot') or '',
		combination(row.get('set_combination')))


def compare_physical_projection(original, physical, commercial, unlinked=()):
	expected = defaultdict(lambda: {'qty': Decimal(0), 'stock_value': Decimal(0)})
	actual = defaultdict(lambda: {'qty': Decimal(0), 'actual_qty': Decimal(0),
		'stock_value': Decimal(0), 'rounding_bound': Decimal(0)})
	groups = {}
	failures = []
	issue_count = 0

	def fail(reason, identity):
		nonlocal issue_count
		issue_count += 1
		if len(failures) < 100:
			failures.append({'reason': reason, 'identity': list(identity)})

	for row in original:
		if number(row['quantity']) <= 0:
			continue
		group = expected[physical_key(row)]
		group['qty'] += number(row['quantity'])
		group['stock_value'] += number(row['quantity']) * number(row['rate'])
	for row in commercial:
		key = (row['invoice'], row['group_key'])
		if not key[1] or key in groups:
			fail('Missing/duplicate commercial group identity', key)
		groups[key] = {'row': row, 'amount': Decimal(0), 'rows': 0}
	for row in physical:
		key = physical_key(row)
		group = actual[key]
		qty, rate, amount = number(row['qty']), number(row['rate']), number(row['amount'])
		group['qty'] += qty
		group['actual_qty'] += number(row['actual_qty'])
		group['stock_value'] += number(row['actual_qty']) * number(row['actual_rate'])
		group['rounding_bound'] += abs(number(row['actual_qty'])) * Decimal('0.0000000005')
		if abs(qty * rate - amount) > abs(qty) * Decimal('0.0000000005') + Decimal('0.000000001'):
			fail('Physical qty/rate/amount do not reconcile', key)
		group_key = (row['invoice'], row.get('essdee_group_key'))
		commercial_group = groups.get(group_key)
		if commercial_group is None:
			fail('Physical row lacks its commercial group', group_key)
			continue
		commercial_group['amount'] += amount
		commercial_group['rows'] += 1
		billed_rate = number(commercial_group['row']['rate'])
		weight = number(row['essdee_rate_weight'])
		if abs(rate - billed_rate * weight) > (abs(billed_rate) + 1) * Decimal('0.0000000005') + Decimal('0.000000001'):
			fail('Commercial rate is not applied through the physical weight', key)
	for key in expected.keys() | actual.keys():
		if key not in expected or key not in actual:
			fail('Missing/unexpected direct GRN variant bucket', key)
			continue
		left, right = expected[key], actual[key]
		if left['qty'] != right['qty'] or left['qty'] != right['actual_qty']:
			fail('Direct GRN quantity changed', key)
		if abs(left['stock_value'] - right['stock_value']) > right['rounding_bound'] + Decimal('0.000001'):
			fail('Original GRN weighted rate/value changed', key)
	for key, group in groups.items():
		if key[0] in unlinked:
			continue
		wanted = number(group['row']['qty']) * number(group['row']['rate'])
		if not group['rows'] or abs(wanted - group['amount']) > Decimal('0.000001'):
			fail('Physical group value differs from commercial value', key)
	return {'mismatch_count': issue_count, 'failures': failures,
		'source_positive_grn_rows': sum(number(row['quantity']) > 0 for row in original),
		'physical_rows': len(physical), 'physical_variant_buckets': len(expected),
		'commercial_groups': len(groups), 'unlinked_drafts': sorted(unlinked),
		'quantity_comparison': 'Exact decimal totals; no rounding allowance',
		'derived_value_comparison': 'Nine-decimal half-unit storage bound plus 0.000001 arithmetic tolerance',
		'method': 'Independent SQL-selected original GRNs and stored PI rows; no projection builder used'}


def audit_invoice_grn_values(source_db, target_db, wo_names):
	def read(db, sql, params=()):
		with db.cursor() as cursor:
			cursor.execute(sql, params)
			return list(cursor.fetchall())

	original, physical, commercial, unlinked = [], [], [], set()
	names = sorted(wo_names)
	for offset in range(0, len(names), 500):
		batch = tuple(names[offset:offset + 500])
		original.extend(read(source_db, '''
			SELECT refs.parent AS invoice, item.item_variant AS item, item.uom,
			 item.set_combination, item.quantity, item.rate,
			 COALESCE(NULLIF(grn.lot,''),wo.lot) AS lot
			FROM (SELECT DISTINCT parent,grn FROM `tabPurchase Invoice GRN`
			 WHERE parenttype='Purchase Invoice' AND parentfield='grn' AND parent IN %s) refs
			JOIN `tabGoods Received Note` grn ON grn.name=refs.grn
			LEFT JOIN `tabWork Order` wo ON wo.name=grn.against_id
			JOIN `tabGoods Received Note Item` item ON item.parent=grn.name
			 AND item.parenttype='Goods Received Note' AND item.parentfield='items'
			WHERE item.quantity>0
		''', (batch,)))
		unlinked.update(row['name'] for row in read(source_db, '''
			SELECT pi.name FROM `tabPurchase Invoice` pi WHERE pi.name IN %s AND pi.docstatus=0
			AND NOT EXISTS (SELECT 1 FROM `tabPurchase Invoice GRN` refs
			 WHERE refs.parent=pi.name AND refs.parenttype='Purchase Invoice'
			 AND refs.parentfield='grn' AND COALESCE(refs.grn,'')<>'')
		''', (batch,)))
		physical.extend(read(target_db, '''
			SELECT parent AS invoice,item,uom,lot,set_combination,qty,actual_qty,
			 actual_rate,rate,amount,essdee_group_key,essdee_rate_weight
			FROM `tabYRP Purchase Invoice Item` WHERE parent IN %s
			 AND parenttype='YRP Purchase Invoice' AND parentfield='items'
		''', (batch,)))
		commercial.extend(read(target_db, '''
			SELECT parent AS invoice,group_key,qty,rate FROM `tabSD YRP Essdee Purchase Invoice Item`
			WHERE parent IN %s AND parenttype='YRP Purchase Invoice' AND parentfield='essdee_items'
		''', (batch,)))
	return compare_physical_projection(original, physical, commercial, unlinked)
