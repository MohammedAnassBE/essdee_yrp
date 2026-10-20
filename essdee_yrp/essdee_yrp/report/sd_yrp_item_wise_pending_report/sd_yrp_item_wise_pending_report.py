"""Native YRP port of the OMS page; live parity pending."""

from essdee_yrp.sales.desk_page_reports import pending


def execute(filters=None):
	return pending(filters)
