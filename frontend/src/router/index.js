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
const SewingPlans = () => import("../departments/sewing/SewingPlans.vue")
const SewingReports = () => import("../departments/sewing/SewingReports.vue")
const SewingAttendance = () => import("../departments/sewing/SewingAttendance.vue")
const SalesSection = () => import("../departments/sales/SalesSection.vue")
const ProductionOrder = () => import("../departments/sales/ProductionOrder.vue")
const ProductionOrderEditorPage = () => import("../departments/sales/ProductionOrderEditorPage.vue")

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
	{ path: "/sewing/plans", name: "sewing-plans", component: SewingPlans },
	{
		path: "/sewing/work-orders",
		name: "sewing-work-orders",
		component: FabricStoreSection,
		props: {
			section: "work_orders",
			storeName: "Sewing",
			basePath: "/sewing",
			workOrderViewRouteName: "sewing-work-order",
			workOrderNewRouteName: "sewing-work-order-new",
		},
	},
	{
		path: "/sewing/work-orders/new",
		name: "sewing-work-order-new",
		component: FabricWorkOrderEditorPage,
		props: {
			backTo: "/sewing/work-orders",
			backLabel: "Work Orders",
			listRouteName: "sewing-work-orders",
			viewRouteName: "sewing-work-order",
		},
	},
	{
		path: "/sewing/work-orders/:workOrderId/edit",
		name: "sewing-work-order-edit",
		component: FabricWorkOrderEditorPage,
		props: {
			backTo: "/sewing/work-orders",
			backLabel: "Work Orders",
			listRouteName: "sewing-work-orders",
			viewRouteName: "sewing-work-order",
		},
	},
	{
		path: "/sewing/work-orders/:workOrderId",
		name: "sewing-work-order",
		component: FabricWorkOrder,
		props: {
			backTo: "/sewing/work-orders",
			backLabel: "Work Orders",
			viewRouteName: "sewing-work-order",
			newRouteName: "sewing-work-order-new",
			editRouteName: "sewing-work-order-edit",
		},
	},
	{ path: "/sewing/reports", name: "sewing-reports", component: SewingReports },
	{ path: "/sewing/attendance", name: "sewing-attendance", component: SewingAttendance },
	{ path: "/sales/production-orders", name: "sales-production-orders", component: SalesSection },
	{ path: "/sales/production-orders/new", name: "sales-production-order-new", component: ProductionOrderEditorPage },
	{ path: "/sales/production-orders/:productionOrderId/edit", name: "sales-production-order-edit", component: ProductionOrderEditorPage, props: true },
	{ path: "/sales/production-orders/:productionOrderId", name: "sales-production-order", component: ProductionOrder, props: true },
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
		path: "/cut-panel-store/work-orders/new",
		name: "cut-panel-work-order-new",
		component: FabricWorkOrderEditorPage,
		props: {
			backTo: "/cut-panel-store/work-orders",
			backLabel: "Work Orders",
			listRouteName: "cut-panel-work-orders",
			viewRouteName: "cut-panel-work-order",
		},
	},
	{
		path: "/cut-panel-store/work-orders/:workOrderId/edit",
		name: "cut-panel-work-order-edit",
		component: FabricWorkOrderEditorPage,
		props: {
			backTo: "/cut-panel-store/work-orders",
			backLabel: "Work Orders",
			listRouteName: "cut-panel-work-orders",
			viewRouteName: "cut-panel-work-order",
		},
	},
	{
		path: "/cut-panel-store/work-orders/:workOrderId",
		name: "cut-panel-work-order",
		component: FabricWorkOrder,
		props: {
			backTo: "/cut-panel-store/work-orders",
			backLabel: "Work Orders",
			viewRouteName: "cut-panel-work-order",
			newRouteName: "cut-panel-work-order-new",
			editRouteName: "cut-panel-work-order-edit",
		},
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
		path: "/accessory-store/work-orders",
		name: "accessory-work-orders",
		component: FabricStoreSection,
		props: {
			section: "work_orders",
			storeName: "Accessory Store",
			basePath: "/accessory-store",
			workOrderViewRouteName: "accessory-work-order",
			workOrderNewRouteName: "accessory-work-order-new",
		},
	},
	{
		path: "/accessory-store/purchase-orders",
		name: "accessory-purchase-orders",
		component: FabricStoreSection,
		props: {
			section: "purchase_orders",
			storeName: "Accessory Store",
			basePath: "/accessory-store",
			purchaseOrderViewRouteName: "accessory-purchase-order",
			purchaseOrderNewRouteName: "accessory-purchase-order-new",
		},
	},
	{
		path: "/accessory-store/stock-transfers",
		name: "accessory-stock-transfers",
		component: FabricStoreSection,
		props: { section: "stock_transfers", storeName: "Accessory Store", basePath: "/accessory-store" },
	},
	{
		path: "/accessory-store/reports",
		name: "accessory-reports",
		component: FabricStoreSection,
		props: { section: "reports", storeName: "Accessory Store", basePath: "/accessory-store" },
	},
	{
		path: "/accessory-store/work-orders/new",
		name: "accessory-work-order-new",
		component: FabricWorkOrderEditorPage,
		props: {
			backTo: "/accessory-store/work-orders",
			backLabel: "Work Orders",
			listRouteName: "accessory-work-orders",
			viewRouteName: "accessory-work-order",
		},
	},
	{
		path: "/accessory-store/work-orders/:workOrderId/edit",
		name: "accessory-work-order-edit",
		component: FabricWorkOrderEditorPage,
		props: {
			backTo: "/accessory-store/work-orders",
			backLabel: "Work Orders",
			listRouteName: "accessory-work-orders",
			viewRouteName: "accessory-work-order",
		},
	},
	{
		path: "/accessory-store/work-orders/:workOrderId",
		name: "accessory-work-order",
		component: FabricWorkOrder,
		props: {
			backTo: "/accessory-store/work-orders",
			backLabel: "Work Orders",
			viewRouteName: "accessory-work-order",
			newRouteName: "accessory-work-order-new",
			editRouteName: "accessory-work-order-edit",
		},
	},
	{
		path: "/accessory-store/purchase-orders/new",
		name: "accessory-purchase-order-new",
		component: FabricPurchaseOrderEditorPage,
		props: {
			backTo: "/accessory-store/purchase-orders",
			backLabel: "Purchase Orders",
			listRouteName: "accessory-purchase-orders",
			viewRouteName: "accessory-purchase-order",
		},
	},
	{
		path: "/accessory-store/purchase-orders/:purchaseOrderId/edit",
		name: "accessory-purchase-order-edit",
		component: FabricPurchaseOrderEditorPage,
		props: {
			backTo: "/accessory-store/purchase-orders",
			backLabel: "Purchase Orders",
			listRouteName: "accessory-purchase-orders",
			viewRouteName: "accessory-purchase-order",
		},
	},
	{
		path: "/accessory-store/purchase-orders/:purchaseOrderId",
		name: "accessory-purchase-order",
		component: FabricPurchaseOrder,
		props: {
			backTo: "/accessory-store/purchase-orders",
			backLabel: "Purchase Orders",
			viewRouteName: "accessory-purchase-order",
			newRouteName: "accessory-purchase-order-new",
			editRouteName: "accessory-purchase-order-edit",
		},
	},
	{
		path: "/accessory-store/delivery-challans/new",
		name: "accessory-delivery-challan-new",
		component: FabricDeliveryChallan,
		props: { backTo: "/accessory-store/work-orders", backLabel: "Work Orders", viewRouteName: "accessory-delivery-challan", duplicateRouteName: "accessory-delivery-challan-new" },
	},
	{
		path: "/accessory-store/delivery-challans/:deliveryChallanId/edit",
		name: "accessory-delivery-challan-edit",
		component: FabricDeliveryChallan,
		props: { backTo: "/accessory-store/work-orders", backLabel: "Work Orders", viewRouteName: "accessory-delivery-challan", duplicateRouteName: "accessory-delivery-challan-new" },
	},
	{
		path: "/accessory-store/delivery-challans/:deliveryChallanId",
		name: "accessory-delivery-challan",
		component: FabricDeliveryChallan,
		props: { backTo: "/accessory-store/work-orders", backLabel: "Work Orders", viewRouteName: "accessory-delivery-challan", duplicateRouteName: "accessory-delivery-challan-new" },
	},
	{
		path: "/accessory-store/goods-received-notes/new",
		name: "accessory-goods-received-note-new",
		component: FabricGoodsReceivedNote,
		props: { backTo: "/accessory-store/work-orders", backLabel: "Work Orders", viewRouteName: "accessory-goods-received-note", duplicateRouteName: "accessory-goods-received-note-new" },
	},
	{
		path: "/accessory-store/goods-received-notes/:goodsReceivedNoteId/edit",
		name: "accessory-goods-received-note-edit",
		component: FabricGoodsReceivedNote,
		props: { backTo: "/accessory-store/work-orders", backLabel: "Work Orders", viewRouteName: "accessory-goods-received-note", duplicateRouteName: "accessory-goods-received-note-new" },
	},
	{
		path: "/accessory-store/goods-received-notes/:goodsReceivedNoteId",
		name: "accessory-goods-received-note",
		component: FabricGoodsReceivedNote,
		props: { backTo: "/accessory-store/work-orders", backLabel: "Work Orders", viewRouteName: "accessory-goods-received-note", duplicateRouteName: "accessory-goods-received-note-new" },
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
