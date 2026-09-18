def execute():
	"""Retained as an executed-patch marker.

	Fixed Essdee fields are installed from ``fixtures/custom_field.json``. They
	must not be provisioned independently by an upgrade patch because doing so
	creates a second, drifting schema source.
	"""
