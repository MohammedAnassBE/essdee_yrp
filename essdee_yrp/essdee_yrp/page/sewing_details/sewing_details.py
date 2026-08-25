"""Desk page endpoints for Essdee Sewing Details."""

from essdee_yrp.sewing.closed_work_order import (
	create_closed_work_order_grn,
	get_closed_sewing_work_orders,
	get_closed_work_order_grn_details,
)

__all__ = [
	"create_closed_work_order_grn",
	"get_closed_sewing_work_orders",
	"get_closed_work_order_grn_details",
]
