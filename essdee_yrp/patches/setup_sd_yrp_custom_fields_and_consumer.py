from essdee_yrp.sd_yrp_sync import ensure_consumer_config


def execute():
	# Supplier fields are fixture-owned. This historical patch only keeps the
	# downstream consumer configuration synchronized.
	ensure_consumer_config()
