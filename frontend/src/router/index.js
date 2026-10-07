import { createRouter, createWebHistory } from "vue-router"

import { departments } from "../departments/registry.js"

const AdministratorPage = () => import("../components/AdministratorPage.vue")
const DocumentUnavailable = () => import("../components/documents/DocumentUnavailable.vue")
const CuttingPlan = () => import("../departments/CuttingPlan.vue")
const CuttingPlanEditorPage = () => import("../departments/CuttingPlanEditorPage.vue")
const CuttingPlans = () => import("../departments/CuttingPlans.vue")
const CuttingOrders = () => import("../departments/CuttingOrders.vue")
const CuttingOrder = () => import("../departments/CuttingOrder.vue")
const CuttingOrderEditorPage = () => import("../departments/CuttingOrderEditorPage.vue")
const CuttingBulkLaySheets = () => import("../departments/CuttingBulkLaySheets.vue")
const CuttingBulkLaySheet = () => import("../departments/CuttingBulkLaySheet.vue")
const CuttingBulkLaySheetEditorPage = () => import("../departments/CuttingBulkLaySheetEditorPage.vue")
const CuttingLaySheetPlanners = () => import("../departments/CuttingLaySheetPlanners.vue")
const CuttingLaySheetPlanner = () => import("../departments/CuttingLaySheetPlanner.vue")
const CuttingLaySheetPlannerEditorPage = () => import("../departments/CuttingLaySheetPlannerEditorPage.vue")
const CuttingReports = () => import("../departments/CuttingReports.vue")
const FabricPurchaseOrder = () => import("../departments/FabricPurchaseOrder.vue")
const FabricPurchaseOrderEditorPage = () => import("../departments/FabricPurchaseOrderEditorPage.vue")
const FabricWorkOrder = () => import("../departments/FabricWorkOrder.vue")
const FabricWorkOrderEditorPage = () => import("../departments/FabricWorkOrderEditorPage.vue")
const FabricDeliveryChallan = () => import("../departments/FabricDeliveryChallan.vue")
const FabricGoodsReceivedNote = () => import("../departments/FabricGoodsReceivedNote.vue")
const FabricStoreSection = () => import("../departments/FabricStoreSection.vue")
const CutPanelStoreSection = () => import("../departments/CutPanelStoreSection.vue")

const routes = [
	{
		path: "/",
		name: "administrator",
		component: AdministratorPage,
	},
	...departments.map((department) => ({
		path: department.path,
		name: department.key,
		component: department.component,
	})),
	{
		path: "/cutting/plans",
		name: "cutting-plans",
		component: CuttingPlans,
	},
	{
		path: "/cutting/plans/new",
		name: "cutting-plan-new",
		component: CuttingPlanEditorPage,
	},
	{
		path: "/cutting/reports",
		name: "cutting-reports",
		component: CuttingReports,
	},
	{
		path: "/cutting/orders",
		name: "cutting-orders",
		component: CuttingOrders,
	},
	{
		path: "/cutting/orders/new",
		name: "cutting-order-new",
		component: CuttingOrderEditorPage,
	},
	{
		path: "/cutting/orders/:cuttingOrderId",
		name: "cutting-order",
		component: CuttingOrder,
	},
	{
		path: "/cutting/bulk-lay-sheets",
		name: "cutting-bulk-lay-sheets",
		component: CuttingBulkLaySheets,
	},
	{
		path: "/cutting/bulk-lay-sheets/new",
		name: "cutting-bulk-lay-sheet-new",
		component: CuttingBulkLaySheetEditorPage,
	},
	{
		path: "/cutting/bulk-lay-sheets/:bulkLaySheetsId",
		name: "cutting-bulk-lay-sheet",
		component: CuttingBulkLaySheet,
	},
	{
		path: "/cutting/lay-sheet-planner",
		name: "cutting-lay-sheet-planners",
		component: CuttingLaySheetPlanners,
	},
	{
		path: "/cutting/lay-sheet-planner/new",
		name: "cutting-lay-sheet-planner-new",
		component: CuttingLaySheetPlannerEditorPage,
	},
	{
		path: "/cutting/lay-sheet-planner/:plannerId",
		name: "cutting-lay-sheet-planner",
		component: CuttingLaySheetPlanner,
	},
	{
		path: "/cutting/plans/:cuttingPlanId",
		name: "cutting-plan",
		component: CuttingPlan,
	},
	{
		path: "/cutting/:cuttingPlanId",
		redirect: (to) => ({
			name: "cutting-plan",
			params: { cuttingPlanId: to.params.cuttingPlanId },
		}),
	},
	{
		path: "/fabric-store/work-orders",
		name: "fabric-work-orders",
		component: FabricStoreSection,
		props: { section: "work_orders" },
	},
	{
		path: "/cut-panel-store/movements",
		name: "cut-panel-movements",
		component: CutPanelStoreSection,
		props: { section: "movements" },
	},
	{
		path: "/cut-panel-store/work-orders",
		name: "cut-panel-work-orders",
		component: CutPanelStoreSection,
		props: { section: "work_orders" },
	},
	{
		path: "/cut-panel-store/cut-bundle-edits",
		name: "cut-panel-cut-bundle-edits",
		component: CutPanelStoreSection,
		props: { section: "cut_bundle_edits" },
	},
	{
		path: "/cut-panel-store/box-sticker-prints",
		name: "cut-panel-box-stickers",
		component: CutPanelStoreSection,
		props: { section: "box_stickers" },
	},
	{
		path: "/cut-panel-store/excel-sticker-prints",
		name: "cut-panel-excel-stickers",
		component: CutPanelStoreSection,
		props: { section: "excel_stickers" },
	},
	{
		path: "/cut-panel-store/reports",
		name: "cut-panel-reports",
		component: CutPanelStoreSection,
		props: { section: "reports" },
	},
	{
		path: "/fabric-store/purchase-orders",
		name: "fabric-purchase-orders",
		component: FabricStoreSection,
		props: { section: "purchase_orders" },
	},
	{
		path: "/fabric-store/stock-transfers",
		name: "fabric-stock-transfers",
		component: FabricStoreSection,
		props: { section: "stock_transfers" },
	},
	{
		path: "/fabric-store/reports",
		name: "fabric-reports",
		component: FabricStoreSection,
		props: { section: "reports" },
	},
	{
		path: "/fabric-store/work-orders/new",
		name: "fabric-work-order-new",
		component: FabricWorkOrderEditorPage,
	},
	{
		path: "/fabric-store/work-orders/:workOrderId/edit",
		name: "fabric-work-order-edit",
		component: FabricWorkOrderEditorPage,
	},
	{
		path: "/fabric-store/work-orders/:workOrderId",
		name: "fabric-work-order",
		component: FabricWorkOrder,
	},
	{
		path: "/fabric-store/purchase-orders/new",
		name: "fabric-purchase-order-new",
		component: FabricPurchaseOrderEditorPage,
	},
	{
		path: "/fabric-store/purchase-orders/:purchaseOrderId/edit",
		name: "fabric-purchase-order-edit",
		component: FabricPurchaseOrderEditorPage,
	},
	{
		path: "/fabric-store/purchase-orders/:purchaseOrderId",
		name: "fabric-purchase-order",
		component: FabricPurchaseOrder,
	},
	{
		path: "/fabric-store/delivery-challans/new",
		name: "fabric-delivery-challan-new",
		component: FabricDeliveryChallan,
	},
	{
		path: "/fabric-store/delivery-challans/:deliveryChallanId/edit",
		name: "fabric-delivery-challan-edit",
		component: FabricDeliveryChallan,
	},
	{
		path: "/fabric-store/delivery-challans/:deliveryChallanId",
		name: "fabric-delivery-challan",
		component: FabricDeliveryChallan,
	},
	{
		path: "/fabric-store/goods-received-notes/new",
		name: "fabric-goods-received-note-new",
		component: FabricGoodsReceivedNote,
	},
	{
		path: "/fabric-store/goods-received-notes/:goodsReceivedNoteId/edit",
		name: "fabric-goods-received-note-edit",
		component: FabricGoodsReceivedNote,
	},
	{
		path: "/fabric-store/goods-received-notes/:goodsReceivedNoteId",
		name: "fabric-goods-received-note",
		component: FabricGoodsReceivedNote,
	},
	{
		path: "/document-unavailable",
		name: "document-unavailable",
		component: DocumentUnavailable,
	},
	{
		path: "/:pathMatch(.*)*",
		component: DocumentUnavailable,
	},
]

export default createRouter({
	history: createWebHistory("/web/"),
	routes,
})
