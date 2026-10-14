import { createRouter, createWebHistory } from "vue-router"

import { departments } from "../departments/registry.js"
import { PD_ROUTES } from "../departments/pd/pdViews.js"
import { PURCHASE_ROUTES } from "../departments/purchase/purchaseViews.js"

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
const FinishingPlans = () => import("../departments/finishing/FinishingPlans.vue")
const FinishingPlan = () => import("../departments/finishing/FinishingPlan.vue")
const FinishingReports = () => import("../departments/finishing/FinishingReports.vue")
const FinishingReworkDetails = () => import("../departments/finishing/FinishingReworkDetails.vue")
const FinishingReworkGroups = () => import("../departments/finishing/FinishingReworkGroups.vue")
const FinishingDispatches = () => import("../departments/finishing/FinishingDispatches.vue")
const FinishingDispatch = () => import("../departments/finishing/FinishingDispatch.vue")
const SalesSection = () => import("../departments/sales/SalesSection.vue")
const ProductionOrder = () => import("../departments/sales/ProductionOrder.vue")
const ProductionOrderEditorPage = () => import("../departments/sales/ProductionOrderEditorPage.vue")
const SalesReports = () => import("../departments/sales/SalesReports.vue")
const PdSection = () => import("../departments/pd/PdSection.vue")
const ProductPage = () => import("../departments/pd/ProductPage.vue")
const ProductReleasePage = () => import("../departments/pd/ProductReleasePage.vue")
const LotwiseItemProfitPage = () => import("../departments/pd/LotwiseItemProfitPage.vue")
const PurchaseInvoices = () => import("../departments/accounts/PurchaseInvoices.vue")
const PurchaseInvoice = () => import("../departments/accounts/PurchaseInvoice.vue")
const PurchaseInvoiceEditorPage = () => import("../departments/accounts/PurchaseInvoiceEditorPage.vue")
const AccountsReports = () => import("../departments/accounts/AccountsReports.vue")
const BillTrackings = () => import("../departments/hr/BillTrackings.vue")
const BillTracking = () => import("../departments/hr/BillTracking.vue")
const BillTrackingEditorPage = () => import("../departments/hr/BillTrackingEditorPage.vue")
const HrReports = () => import("../departments/hr/HrReports.vue")
const LotsList = () => import("../departments/purchase/lot/LotsList.vue")
const LotPage = () => import("../departments/purchase/lot/LotPage.vue")
const LotEditorPage = () => import("../departments/purchase/lot/LotEditorPage.vue")
const ItemsList = () => import("../departments/purchase/ItemsList.vue")
const ItemPage = () => import("../departments/purchase/ItemPage.vue")
const ItemEditorPage = () => import("../departments/purchase/ItemEditorPage.vue")
const ItemPricesList = () => import("../departments/purchase/ItemPricesList.vue")
const ItemPricePage = () => import("../departments/purchase/ItemPricePage.vue")
const ItemPriceEditor = () => import("../departments/purchase/ItemPriceEditor.vue")

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
	{ path: "/finishing/plans", name: "finishing-plans", component: FinishingPlans },
	{ path: "/finishing/plans/:finishingPlanId", name: "finishing-plan", component: FinishingPlan },
	{ path: "/finishing/reports", name: "finishing-reports", component: FinishingReports },
	{ path: "/finishing/rework-details", name: "finishing-rework-details", component: FinishingReworkDetails },
	{ path: "/finishing/rework-groups", name: "finishing-rework-groups", component: FinishingReworkGroups },
	{ path: "/finishing/dispatches", name: "finishing-dispatches", component: FinishingDispatches },
	{ path: "/finishing/dispatches/new", name: "finishing-dispatch-new", component: FinishingDispatch },
	{ path: "/finishing/dispatches/:dispatchId", name: "finishing-dispatch", component: FinishingDispatch },
	{ path: "/sales/production-orders", name: "sales-production-orders", component: SalesSection },
	{ path: "/sales/production-orders/new", name: "sales-production-order-new", component: ProductionOrderEditorPage },
	{ path: "/sales/production-orders/:productionOrderId/edit", name: "sales-production-order-edit", component: ProductionOrderEditorPage, props: true },
	{ path: "/sales/production-orders/:productionOrderId", name: "sales-production-order", component: ProductionOrder, props: true },
	{ path: "/sales/reports", name: "sales-reports", component: SalesReports },
	{ path: "/pd/products", name: PD_ROUTES.products, component: PdSection, props: { section: "products" } },
	{ path: "/pd/products/new", name: PD_ROUTES.productNew, component: ProductPage },
	{ path: "/pd/products/:productId/edit", name: PD_ROUTES.productEdit, component: ProductPage, props: true },
	{ path: "/pd/products/:productId", name: PD_ROUTES.product, component: ProductPage, props: true },
	{
		path: "/pd/product-releases",
		name: PD_ROUTES.releases,
		component: PdSection,
		props: { section: "product_releases" },
	},
	{
		path: "/pd/product-releases/:releaseId",
		name: PD_ROUTES.release,
		component: ProductReleasePage,
		props: true,
	},
	{
		path: "/pd/lotwise-item-profits",
		name: PD_ROUTES.lotwiseList,
		component: PdSection,
		props: { section: "lotwise_item_profits" },
	},
	{
		path: "/pd/lotwise-item-profits/new",
		name: PD_ROUTES.lotwiseNew,
		component: LotwiseItemProfitPage,
	},
	{
		path: "/pd/lotwise-item-profits/:profitId",
		name: PD_ROUTES.lotwise,
		component: LotwiseItemProfitPage,
		props: true,
	},
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
		path: "/purchase/purchase-orders",
		name: "purchase-purchase-orders",
		component: FabricStoreSection,
		props: {
			section: "purchase_orders",
			storeName: "Purchase",
			basePath: "/purchase",
			purchaseOrderViewRouteName: "purchase-purchase-order",
			purchaseOrderNewRouteName: "purchase-purchase-order-new",
		},
	},
	{ path: "/purchase/lots", name: PURCHASE_ROUTES.lots, component: LotsList },
	{ path: "/purchase/lots/new", name: PURCHASE_ROUTES.lotNew, component: LotEditorPage },
	{ path: "/purchase/lots/:lotId", name: PURCHASE_ROUTES.lot, component: LotPage, props: true },
	{ path: "/purchase/lots/:lotId/edit", name: PURCHASE_ROUTES.lotEdit, component: LotEditorPage, props: true },
	{
		path: "/purchase/items",
		name: PURCHASE_ROUTES.items,
		component: ItemsList,
	},
	{
		path: "/purchase/items/new",
		name: PURCHASE_ROUTES.itemNew,
		component: ItemEditorPage,
	},
	{
		path: "/purchase/items/:itemId/edit",
		name: PURCHASE_ROUTES.itemEdit,
		component: ItemEditorPage,
		props: true,
	},
	{
		path: "/purchase/items/:itemId",
		name: PURCHASE_ROUTES.item,
		component: ItemPage,
		props: true,
	},
	{
		path: "/purchase/item-prices",
		name: PURCHASE_ROUTES.itemPrices,
		component: ItemPricesList,
	},
	{
		path: "/purchase/item-prices/new",
		name: PURCHASE_ROUTES.itemPriceNew,
		component: ItemPriceEditor,
	},
	{
		path: "/purchase/item-prices/:priceId/edit",
		name: PURCHASE_ROUTES.itemPriceEdit,
		component: ItemPriceEditor,
		props: true,
	},
	{
		path: "/purchase/item-prices/:priceId",
		name: PURCHASE_ROUTES.itemPrice,
		component: ItemPricePage,
		props: true,
	},
	{
		path: "/purchase/stock-transfers",
		name: "purchase-stock-transfers",
		component: FabricStoreSection,
		props: { section: "stock_transfers", storeName: "Purchase", basePath: "/purchase" },
	},
	{
		path: "/purchase/box-sticker-prints",
		name: "purchase-box-stickers",
		component: CutPanelStoreSection,
		props: { section: "box_stickers", backTo: "/purchase", backLabel: "Purchase" },
	},
	{
		path: "/purchase/reports",
		name: "purchase-reports",
		component: FabricStoreSection,
		props: {
			section: "reports",
			storeName: "Purchase",
			basePath: "/purchase",
			reportKeys: ["stock_balance", "purchase_order_itemwise", "lot_cut_quantity"],
		},
	},
	{
		path: "/purchase/purchase-orders/new",
		name: "purchase-purchase-order-new",
		component: FabricPurchaseOrderEditorPage,
		props: {
			backTo: "/purchase/purchase-orders",
			backLabel: "Purchase Orders",
			listRouteName: "purchase-purchase-orders",
			viewRouteName: "purchase-purchase-order",
		},
	},
	{
		path: "/purchase/purchase-orders/:purchaseOrderId/edit",
		name: "purchase-purchase-order-edit",
		component: FabricPurchaseOrderEditorPage,
		props: {
			backTo: "/purchase/purchase-orders",
			backLabel: "Purchase Orders",
			listRouteName: "purchase-purchase-orders",
			viewRouteName: "purchase-purchase-order",
		},
	},
	{
		path: "/purchase/purchase-orders/:purchaseOrderId",
		name: "purchase-purchase-order",
		component: FabricPurchaseOrder,
		props: {
			backTo: "/purchase/purchase-orders",
			backLabel: "Purchase Orders",
			viewRouteName: "purchase-purchase-order",
			newRouteName: "purchase-purchase-order-new",
			editRouteName: "purchase-purchase-order-edit",
		},
	},
	{
		path: "/document-unavailable",
		name: "document-unavailable",
		component: DocumentUnavailable,
	},
	{
		path: "/accounts/purchase-invoices",
		name: "accounts-purchase-invoices",
		component: PurchaseInvoices,
	},
	{
		path: "/accounts/purchase-invoices/new",
		name: "accounts-purchase-invoice-new",
		component: PurchaseInvoiceEditorPage,
	},
	{
		path: "/accounts/purchase-invoices/:purchaseInvoiceId/edit",
		name: "accounts-purchase-invoice-edit",
		component: PurchaseInvoiceEditorPage,
		props: true,
	},
	{
		path: "/accounts/purchase-invoices/:purchaseInvoiceId",
		name: "accounts-purchase-invoice",
		component: PurchaseInvoice,
		props: true,
	},
	{
		path: "/accounts/reports",
		name: "accounts-reports",
		component: AccountsReports,
	},
	{
		path: "/hr/bill-tracking",
		name: "hr-bill-trackings",
		component: BillTrackings,
	},
	{
		path: "/hr/bill-tracking/new",
		name: "hr-bill-tracking-new",
		component: BillTrackingEditorPage,
	},
	{
		path: "/hr/bill-tracking/:billTrackingId/edit",
		name: "hr-bill-tracking-edit",
		component: BillTrackingEditorPage,
		props: true,
	},
	{
		path: "/hr/bill-tracking/:billTrackingId",
		name: "hr-bill-tracking",
		component: BillTracking,
		props: true,
	},
	{
		path: "/hr/reports",
		name: "hr-reports",
		component: HrReports,
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
