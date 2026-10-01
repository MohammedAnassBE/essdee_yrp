import AccessoryStore from "./AccessoryStore.vue"
import CutPanelStore from "./CutPanelStore.vue"
import Cutting from "./Cutting.vue"
import FabricStore from "./FabricStore.vue"
import Finishing from "./Finishing.vue"
import Merch from "./Merch.vue"
import Planning from "./Planning.vue"
import Purchase from "./Purchase.vue"
import Sales from "./Sales.vue"
import Sewing from "./Sewing.vue"

export const departments = [
	{
		key: "cutting",
		label: "Cutting",
		shortLabel: "CT",
		path: "/cutting",
		accent: "#e85d3f",
		component: Cutting,
	},
	{
		key: "fabric-store",
		label: "Fabric Store",
		shortLabel: "FS",
		path: "/fabric-store",
		accent: "#2f7d68",
		component: FabricStore,
	},
	{
		key: "cut-panel-store",
		label: "Cut Panel Store",
		shortLabel: "CP",
		path: "/cut-panel-store",
		accent: "#315da8",
		component: CutPanelStore,
	},
	{
		key: "accessory-store",
		label: "Accessory Store",
		shortLabel: "AS",
		path: "/accessory-store",
		accent: "#8b5fbf",
		component: AccessoryStore,
	},
	{
		key: "sewing",
		label: "Sewing",
		shortLabel: "SW",
		path: "/sewing",
		accent: "#c64b73",
		component: Sewing,
	},
	{
		key: "finishing",
		label: "Finishing",
		shortLabel: "FN",
		path: "/finishing",
		accent: "#087c91",
		component: Finishing,
	},
	{
		key: "merch",
		label: "Merch",
		shortLabel: "MR",
		path: "/merch",
		accent: "#a26a13",
		component: Merch,
	},
	{
		key: "purchase",
		label: "Purchase",
		shortLabel: "PU",
		path: "/purchase",
		accent: "#536f2d",
		component: Purchase,
	},
	{
		key: "sales",
		label: "Sales",
		shortLabel: "SA",
		path: "/sales",
		accent: "#b7493f",
		component: Sales,
	},
	{
		key: "planning",
		label: "Planning",
		shortLabel: "PL",
		path: "/planning",
		accent: "#5257a6",
		component: Planning,
	},
]
