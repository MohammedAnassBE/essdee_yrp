from yrp.namespace_migration import reconcile_legacy_single_child_parents


def execute():
	reconcile_legacy_single_child_parents(("essdee_yrp",))
