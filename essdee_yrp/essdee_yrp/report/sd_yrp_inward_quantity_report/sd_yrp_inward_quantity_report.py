from essdee_yrp.planning.reports import inward_quantity


def execute(filters=None):
	report = inward_quantity.run(filters or {})
	return report["columns"], report["result"], report.get("message")
