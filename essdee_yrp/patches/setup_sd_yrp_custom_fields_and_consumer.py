from essdee_yrp.sd_yrp_sync import ensure_consumer_config


def execute():
	# Fixed fields are fixture-owned. This patch now retains only the unrelated
	# consumer configuration side effect needed by existing installations.
	ensure_consumer_config()
