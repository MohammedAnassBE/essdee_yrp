from essdee_yrp.planning.reports import size_wise_stock


def execute(filters=None):
	report = size_wise_stock.run(filters or {})
	return report["columns"], report["result"]
