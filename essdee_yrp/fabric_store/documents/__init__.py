"""Shared document services for Fabric Store web workspaces."""

from essdee_yrp.fabric_store.documents.common import (
	assert_expected_modified,
	filter_authorized_capabilities,
	get_document_permissions,
	get_effective_fields,
	get_workspace_base,
)
from essdee_yrp.fabric_store.documents.purchase_order import (
	execute_purchase_order_command,
	get_purchase_order_editor,
	get_purchase_order_workspace,
	save_purchase_order_document,
)
from essdee_yrp.fabric_store.documents.work_order import (
	execute_work_order_command,
	get_work_order_editor,
	get_work_order_workspace,
	save_work_order_document,
)

__all__ = (
	"assert_expected_modified",
	"execute_purchase_order_command",
	"execute_work_order_command",
	"filter_authorized_capabilities",
	"get_document_permissions",
	"get_effective_fields",
	"get_purchase_order_editor",
	"get_purchase_order_workspace",
	"get_work_order_editor",
	"get_work_order_workspace",
	"get_workspace_base",
	"save_purchase_order_document",
	"save_work_order_document",
)
