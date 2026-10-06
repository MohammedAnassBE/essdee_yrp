# Key page dependency trees

## `/` — Administrator

Entry: `frontend/src/components/AdministratorPage.vue`

- `frontend/src/components/DepartmentCard.vue`
- `frontend/src/departments/registry.js`
- `frontend/src/App.vue`
- `frontend/src/styles/enterprise.css`
- `frontend/src/styles/main.css`

## `/fabric-store`

Entry: `frontend/src/departments/FabricStore.vue`

- `frontend/src/components/DepartmentPage.vue`
- `frontend/src/components/common/WorkspaceLauncher.vue`
- `frontend/src/api/fabricStore.js`
- `frontend/src/departments/registry.js`

## `/fabric-store/purchase-orders/:purchaseOrderId`

Entry: `frontend/src/departments/FabricPurchaseOrder.vue`

- `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- `frontend/src/components/stock/StockItemMatrix.vue`
- `frontend/src/components/documents/DocumentActionStrip.vue`
- `frontend/src/components/documents/DocumentConfirmationDialog.vue`
- `frontend/src/components/documents/DocumentPrintButton.vue`
- `frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue`
- `frontend/src/departments/fabric-store/PurchaseOrderDialog.vue`
- `frontend/src/departments/fabric-store/SupplierNotificationPanel.vue`
- `frontend/src/api/fabricStore.js`
- `frontend/src/utils/documentValues.js`

## `/fabric-store/work-orders/:workOrderId`

Entry: `frontend/src/departments/FabricWorkOrder.vue`

- `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- `frontend/src/departments/fabric-store/WorkOrderDetails.vue`
- `frontend/src/departments/fabric-store/WorkOrderSummary.vue`
- `frontend/src/departments/fabric-store/WorkOrderActivityRail.vue`
- `frontend/src/departments/fabric-store/WorkOrderActionPanel.vue`
- `frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue`
- `frontend/src/components/documents/DocumentActionStrip.vue`
- `frontend/src/components/documents/DocumentConfirmationDialog.vue`
- `frontend/src/components/documents/DocumentPrintButton.vue`
- `frontend/src/components/stock/StockItemMatrix.vue`
- `frontend/src/api/fabricStore.js`

## `/fabric-store/delivery-challans/:deliveryChallanId`

Entry: `frontend/src/departments/FabricDeliveryChallan.vue`

- `frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue`
- `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- `frontend/src/departments/fabric-store/DeliveryChallanReturnDialog.vue`
- `frontend/src/departments/fabric-store/DeliveryChallanReturnPanel.vue`
- `frontend/src/components/common/FormField.vue`
- `frontend/src/components/stock/StockItemMatrix.vue`
- `frontend/src/components/documents/*`
- `frontend/src/api/fabricStore.js`

## `/fabric-store/goods-received-notes/:goodsReceivedNoteId`

Entry: `frontend/src/departments/FabricGoodsReceivedNote.vue`

- `frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue`
- `frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue`
- `frontend/src/departments/fabric-store/GrnCalculatePanel.vue`
- `frontend/src/departments/fabric-store/InspectionEntryPanel.vue`
- `frontend/src/components/common/FormField.vue`
- `frontend/src/components/stock/StockItemMatrix.vue`
- `frontend/src/components/documents/*`
- `frontend/src/api/fabricStore.js`

## `/cutting/orders`

Entry: `frontend/src/departments/CuttingOrders.vue`

- `frontend/src/components/common/ListView.vue`
- `frontend/src/components/common/ListviewFilters.vue`
- `frontend/src/components/common/ListviewQuickFilters.vue`
- `frontend/src/components/common/UserListviewColumns.vue`
- `frontend/src/api/frappe.js`

## `/cutting/orders/:cuttingOrderId`

Entry: `frontend/src/departments/CuttingOrder.vue`

- `frontend/src/departments/cutting/order/CuttingOrderActions.vue`
- `frontend/src/departments/cutting/order/CuttingOrderTabs.vue`
- `frontend/src/departments/cutting/order/CuttingOrderDetailDialog.vue`
- `frontend/src/departments/cutting/shared/CuttingQuantityMatrix.vue`
- `frontend/src/departments/cutting/shared/MaterialRequirementGroups.vue`
- `frontend/src/departments/cutting/shared/CuttingParentSidebar.vue`
- `frontend/src/components/documents/DocumentPrintButton.vue`
- `frontend/src/api/cuttingOrder.js`

## `/cutting/bulk-lay-sheets/:bulkLaySheetsId`

Entry: `frontend/src/departments/CuttingBulkLaySheet.vue`

- `frontend/src/departments/cutting/bulk/BulkActions.vue`
- `frontend/src/departments/cutting/bulk/BulkActiveLaySheet.vue`
- `frontend/src/departments/cutting/bulk/BulkBundleTable.vue`
- `frontend/src/departments/cutting/bulk/BulkDeliveryDialog.vue`
- `frontend/src/departments/cutting/bulk/BulkPrintDialog.vue`
- `frontend/src/departments/cutting/bulk/BulkSetupEditor.vue`
- `frontend/src/departments/cutting/bulk/BulkWorkflowRail.vue`
- `frontend/src/api/cuttingBulkLaySheets.js`

## `/cutting/lay-sheet-planner/:plannerId`

Entry: `frontend/src/departments/CuttingLaySheetPlanner.vue`

- `frontend/src/departments/cutting/planner/PlannerInputs.vue`
- `frontend/src/departments/cutting/planner/PlannerPlanWorkspace.vue`
- `frontend/src/departments/cutting/planner/PlannerStrategies.vue`
- `frontend/src/departments/cutting/planner/PlannerLayPlan.vue`
- `frontend/src/departments/cutting/planner/PlannerOrderMatrix.vue`
- `frontend/src/departments/cutting/planner/PlannerDeviationTable.vue`
- `frontend/src/api/cuttingLaySheetPlanner.js`
