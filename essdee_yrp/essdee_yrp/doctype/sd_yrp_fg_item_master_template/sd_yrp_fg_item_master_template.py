# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt

from yrp.yrp.doctype.yrp_item_master_template.yrp_item_master_template import (
	ItemMasterTemplate,
)


class SDYRPFGItemMasterTemplate(ItemMasterTemplate):
	"""Essdee FG template using the generic, maintained YRP mapping contract."""


FGItemMasterTemplate = SDYRPFGItemMasterTemplate
