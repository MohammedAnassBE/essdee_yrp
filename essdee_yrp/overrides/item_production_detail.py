"""Essdee controller behaviour for Item Production Detail."""

from yrp.yrp.doctype.item_production_detail.item_production_detail import (
	ItemProductionDetail as BaseItemProductionDetail,
)


class EssdeeItemProductionDetail(BaseItemProductionDetail):
	def validate_stage_continuity(self):
		"""Do not treat optional process rows as one sequential stage chain.

		Essdee garment IPDs store independent embellishment/process operations in
		``ipd_processes``. Adjacent rows can therefore operate at different stages
		(for example fusing at Cut and ironing at Piece). The complete production
		flow is defined by the dedicated cutting, stitching, packing and fabric
		fields and is validated by Essdee's business validators.
		"""
		return
