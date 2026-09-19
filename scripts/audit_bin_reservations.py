"""Independent historic Bin cache and active SRE quantity reconciliation.

Raw field parity is still checked by the full value auditor. This additional
check distinguishes preservation of the source cache from live reservation
semantics; it imports neither the migration writer nor the stock calculator.
"""

from collections import defaultdict
from decimal import Decimal


BUCKET_FIELDS = ('item_code', 'warehouse', 'lot', 'received_type')


def query(connection, sql, params=()):
	with connection.cursor() as cursor:
		cursor.execute(sql, params)
		return list(cursor.fetchall())


def quantity(value):
	return Decimal(str(value or 0))


def bucket(row):
	return tuple(row[field] for field in BUCKET_FIELDS)


def reconcile_reservations(source_bins, target_bins, source_sres, target_sres):
	source_history = {row['name']: (bucket(row), quantity(row['reserved_qty'])) for row in source_bins}
	target_history = {row['name']: (bucket(row), quantity(row['reserved_qty'])) for row in target_bins}
	history_mismatches = sum(source_history.get(name) != target_history.get(name)
		for name in source_history.keys() | target_history.keys())
	source_active, target_active, cached = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
	for row in source_bins:
		cached[bucket(row)] += quantity(row['reserved_qty'])
	for row in source_sres:
		source_active[bucket(row)] += quantity(row['reserved_qty']) - quantity(row['delivered_qty'])
	for row in target_sres:
		target_active[bucket(row)] += max(quantity(row['reserved_qty']) - quantity(row['delivered_qty'])
			- quantity(row.get('closed_qty')), Decimal(0))
	source_active = {key: value for key, value in source_active.items() if value}
	target_active = {key: value for key, value in target_active.items() if value}
	active_mismatches = sum(source_active.get(key, 0) != target_active.get(key, 0)
		for key in source_active.keys() | target_active.keys())
	cache_differences = {key: cached.get(key, 0) - source_active.get(key, 0)
		for key in cached.keys() | source_active.keys()
		if cached.get(key, 0) != source_active.get(key, 0)}
	stale_only = {key: value for key, value in cache_differences.items() if key not in source_active}
	return {
		'mismatch_count': history_mismatches + active_mismatches,
		'historic_cache_identity_or_value_mismatches': history_mismatches,
		'active_reservation_bucket_mismatches': active_mismatches,
		'source_nonzero_bin_rows': len(source_bins), 'target_nonzero_bin_rows': len(target_bins),
		'source_cached_reserved_total': str(sum(cached.values(), Decimal(0))),
		'target_reserved_total': str(sum((quantity(row['reserved_qty']) for row in target_bins), Decimal(0))),
		'source_active_sre_rows': len(source_sres), 'target_active_sre_rows': len(target_sres),
		'source_active_sre_buckets': len(source_active), 'target_active_sre_buckets': len(target_active),
		'source_active_sre_total': str(sum(source_active.values(), Decimal(0))),
		'target_active_sre_total': str(sum(target_active.values(), Decimal(0))),
		'source_cache_different_buckets': len(cache_differences),
		'stale_source_cache_only_buckets': len(stale_only),
		'stale_source_cache_only_total': str(sum(stale_only.values(), Decimal(0))),
		'method': 'Original nonzero Bin identities/buckets/values retained in reserved_qty; '
			'independently aggregated active SRE quantities by item, warehouse, lot and received type. '
			'Stale source cache is historical data, not newly activated reservations. Runtime enforcement is tested separately.',
	}


def audit_bin_reservations(source_db, target_db):
	fields = ','.join(BUCKET_FIELDS)
	source_bins = query(source_db, f'SELECT name,{fields},reserved_qty FROM tabBin WHERE COALESCE(reserved_qty,0)<>0')
	target_bins = query(target_db, f'SELECT name,{fields},reserved_qty FROM `tabYRP Bin` '
		'WHERE COALESCE(reserved_qty,0)<>0')
	source_sres = query(source_db, f'SELECT name,{fields},reserved_qty,delivered_qty FROM `tabStock Reservation Entry` '
		"WHERE docstatus=1 AND status NOT IN ('Delivered','Cancelled')")
	target_sres = query(target_db, f'SELECT name,{fields},reserved_qty,delivered_qty,closed_qty FROM `tabYRP Stock Reservation Entry` '
		"WHERE docstatus=1 AND status NOT IN ('Delivered','Closed','Cancelled')")
	result = reconcile_reservations(source_bins, target_bins, source_sres, target_sres)
	# This source has two stock dimensions. Do not silently collapse a new
	# populated target dimension into its old four-part grouping.
	dimensions = query(target_db, 'SELECT fieldname FROM `tabYRP Stock Dimension` '
		'WHERE parent=%s AND parenttype=%s AND parentfield=%s',
		('YRP Stock Settings', 'YRP Stock Settings', 'stock_dimensions'))
	extra_rows = 0
	for row in dimensions:
		if row['fieldname'] in BUCKET_FIELDS:
			continue
		column = '`' + str(row['fieldname']).replace('`', '``') + '`'
		extra_rows += int(query(target_db, f'SELECT COUNT(*) n FROM `tabYRP Stock Reservation Entry` '
			f"WHERE docstatus=1 AND status NOT IN ('Delivered','Closed','Cancelled') AND COALESCE({column},'')<>''")[0]['n'])
	result['active_target_rows_with_additional_dimensions'] = extra_rows
	result['mismatch_count'] += extra_rows
	return result
