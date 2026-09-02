import { createApp } from "vue";

import AccessoryItems from "./Item_Po_detail/AccessoryItems.vue";
import BundleGroup from "./Item_Po_detail/BundleGroup.vue";
import ClothAccessory from "./Item_Po_detail/ClothAccessory.vue";
import ClothAccessoryCombination from "./Item_Po_detail/ClothAccessoryCombination.vue";
import CombinationItemDetail from "./Item_Po_detail/CombinationItemDetail.vue";
import CuttingItemDetail from "./Item_Po_detail/CuttingItemDetail.vue";
import EmblishmentDetails from "./Item_Po_detail/EmblishmentDetails.vue";
import ColourYarnRecipeEditor from "./Item_Po_detail/ColourYarnRecipeEditor.vue";
import FabricSwapDetail from "./Item_Po_detail/FabricSwapDetail.vue";
import PanelWiseConsumptionMatrix from "./Item_Po_detail/PanelWiseConsumptionMatrix.vue";
import PanelWiseClothMappingMatrix from "./Item_Po_detail/PanelWiseClothMappingMatrix.vue";
import LotOrderedDetail from "./ProductionOrder/LotOrderedDetail.vue";
import ProductionOrderEntry from "./ProductionOrder/components/ProductionOrderEntry.vue";
import UpdatePrice from "./ProductionOrder/components/UpdatePrice.vue";
import FabricProgram from "./Lot/FabricProgram.vue";
import { LotOrderWrapper, OCRDetailWrapper } from "./Lot";
import {
	AlternativeDetailWrapper,
	AlternativeItemWrapper,
	FinishingDetailWrapper,
	FinishingGRNWrapper,
	FinishingInwardWrapper,
	FinishingIroningExcessWrapper,
	FinishingOCRWrapper,
	FinishingOldLotTransferWrapper,
	FinishingPackReturnWrapper,
	FinishingPlanCompleteTransferWrapper,
	FinishingPlanDispatchWrapper,
	FinishingQtyDetailWrapper,
	FinishingRejectionDetailWrapper,
} from "./Finishing";
import FabricProcesses from "./Fabric/FabricProcesses.vue";
import CuttingDetailReport from "./CuttingLaySheet/components/CuttingDetailReport.vue";
import DailyCutSheetReport from "./CuttingLaySheet/components/DailyCutSheetReport.vue";
import DailyProductionReport from "./CuttingLaySheet/components/DailyProductionReport.vue";
import CutPlanClothItems from "./CuttingPlan/components/CutPlanClothItems.vue";
import ReturnItemsMatrix from "./DeliveryChallan/ReturnItemsMatrix.vue";
import CutPlanItems from "./CuttingPlan/components/CutPlanItems.vue";
import MultiCCR from "./CuttingPlan/components/MultiCCR.vue";
import RecutPrintPanelDetail from "./CuttingPlan/components/RecutPrintPanelDetails.vue";
import RecutPrintPanelView from "./CuttingPlan/components/RecutPrintPanelView.vue";
import LayPlanResult from "./CuttingLaysheetPlan/LayPlanResult.vue";
import LaySheetAccessory from "./CuttingLaySheet/components/LaySheetAccessory.vue";
import LaySheetCloths from "./CuttingLaySheet/components/LaySheetCloths.vue";
import AttributeList from "./components/AttributeList.vue";
import ClothDetail from "./CuttingOrder/ClothDetail.vue";
import CuttingOrderItems from "./CuttingOrder/CuttingOrderItems.vue";
import CuttingCompletionDetail from "./CuttingPlan/components/CuttingCompletionDetail.vue";
import CuttingIncompletionDetail from "./CuttingPlan/components/CuttingIncompletionDetail.vue";
import CuttingMarker from "./Cutting_Marker/components/cutting_marker.vue";
import CutPanelMovementBundle from "./Cut_Panel_Movement/components/CutPanelMovementBundle.vue";
import CutBundleEdit from "./Cut_Bundle_Edit/components/CutBundleEdit.vue";
import QualityInspection from "./Quality/QualityInspection.vue";
import WOSummary from "./WorkOrder/components/WoSummary.vue";
import ReworkPage from "./WorkOrder/components/ReworkPage.vue";
import { SewingPlanWrapper } from "./SewingPlan";
import ActionDetail from "./ActionMaster/ActionDetail.vue";
import TimeAction from "./TimeAndAction/TimeAction.vue";
import TimeActionPreview from "./TimeAndAction/TimeActionPreview.vue";
import TimeActionReport from "./TimeAndAction/TimeActionReport.vue";
import TandAUpdate from "./TimeAndAction/TandAUpdate.vue";
import TimeAndActionOrderTracking from "./TimeAndAction/TimeAndActionTracking.vue";
import TimeAndActionWeeklyReport from "./TimeAndAction/TimeAndActionWeeklyReport.vue";
import WorkStation from "./Lot/components/WorkStation.vue";
import StockSummary from "./Stock/StockSummary.vue";
import ItemConversion from "./Stock/ItemConversion.vue";
import { copyElementAsImage } from "./copyElementAsImage";
import {
	ProductCostingListWrapper,
	ProductFileVersionsWrapper,
	ProductGraphicsWrapper,
	ProductImageListWrapper,
	ProductMeasurementImageWrapper,
	ProductMeasurementWrapper,
	ProductSilhoutteWrapper,
	ProductTrimColourCombWrapper,
} from "./ProductDevelopment";

frappe.provide("frappe.production.ui");
frappe.provide("frappe.production.utils");
frappe.provide("frappe.production.product_development.ui");

frappe.production.utils.copyElementAsImage = copyElementAsImage;

frappe.production.product_development.ui.ProductFileVersions = ProductFileVersionsWrapper;
frappe.production.product_development.ui.ProductCostingList = ProductCostingListWrapper;
frappe.production.product_development.ui.ProductImageList = ProductImageListWrapper;
frappe.production.product_development.ui.ProductTrimColourComb = ProductTrimColourCombWrapper;
frappe.production.product_development.ui.ProductMeasurement = ProductMeasurementWrapper;
frappe.production.product_development.ui.ProductSilhoutte = ProductSilhoutteWrapper;
frappe.production.product_development.ui.ProductGraphics = ProductGraphicsWrapper;
frappe.production.product_development.ui.ProductMeasurementImage =
	ProductMeasurementImageWrapper;

function mount_component(component, wrapper) {
	const app = createApp(component);
	if (typeof SetVueGlobals === "function") {
		SetVueGlobals(app);
	}
	return {
		app,
		vue: app.mount($(wrapper).get(0)),
	};
}

frappe.production.ui.StockSummary = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(StockSummary, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
};

frappe.production.ui.ItemConversion = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(ItemConversion, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data) { this.vue.load_data(data); }
	update_status() { this.vue.update_status(); }
	get_items() { return JSON.parse(JSON.stringify(this.vue.get_items())); }
	refresh_from_rates() { return this.vue.refresh_from_rates(); }
};

frappe.production.ui.SewingPlan = SewingPlanWrapper;

frappe.production.ui.ReworkPage = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(ReworkPage, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
};

frappe.production.ui.CombinationItemDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(CombinationItemDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(JSON.parse(JSON.stringify(items)));
	}
	set_attributes() {
		this.vue.set_attributes();
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.CuttingItemDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(CuttingItemDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(items);
	}
	set_attributes() {
		this.vue.set_attributes();
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.PanelWiseConsumptionMatrix = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(PanelWiseConsumptionMatrix, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(payload, locked = false) {
		this.vue.load_data(JSON.parse(JSON.stringify(payload || {})), locked);
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.PanelWiseClothMappingMatrix = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(PanelWiseClothMappingMatrix, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(payload, locked = false) {
		this.vue.load_data(JSON.parse(JSON.stringify(payload || {})), locked);
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.ReturnItemsMatrix = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(ReturnItemsMatrix, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data) {
		return this.vue.load_data(data || {});
	}
	get_data() {
		return this.vue.get_data();
	}
};

frappe.production.ui.ClothAccessory = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(ClothAccessory, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(items);
	}
	set_attributes() {
		this.vue.set_attributes();
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.ClothAccessoryCombination = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(ClothAccessoryCombination, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(items);
	}
	set_attributes() {
		this.vue.set_attributes();
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.AccessoryItems = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(AccessoryItems, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(typeof items === "string" ? JSON.parse(items) : items);
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_items()));
	}
};

frappe.production.ui.BundleGroup = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_app();
	}
	make_app() {
		const mounted = mount_component(BundleGroup, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(items);
	}
	get_items() {
		return this.vue.get_items();
	}
};

frappe.production.ui.EmblishmentDetails = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(EmblishmentDetails, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_items(typeof items === "string" ? items : JSON.stringify(items || {}));
	}
	get_items() {
		return JSON.parse(JSON.stringify(this.vue.get_items()));
	}
};

frappe.production.ui.FabricSwapDetail = class {
	constructor(wrapper, opts = {}) {
		this.$wrapper = $(wrapper);
		this.opts = opts;
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(FabricSwapDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data) {
		// on_change is passed alongside (not inside) the data so the JSON
		// round-trip cannot strip the callback.
		this.vue.load_data(JSON.parse(JSON.stringify(data || {})), this.opts.on_change);
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.ColourYarnRecipeEditor = class {
	constructor(wrapper, opts = {}) {
		this.$wrapper = $(wrapper);
		this.opts = opts;
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(ColourYarnRecipeEditor, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(payload) {
		this.vue.load_data(JSON.parse(JSON.stringify(payload || {})), this.opts.on_change);
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
};

frappe.production.ui.LotOrderedDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(LotOrderedDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(context) {
		this.vue.load_data(JSON.parse(JSON.stringify(context || {})));
	}
};

frappe.production.ui.LotOrder = LotOrderWrapper;
frappe.production.ui.OCRDetail = OCRDetailWrapper;

frappe.production.ui.CutPlanItems = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_app();
	}
	make_app() {
		const mounted = mount_component(CutPlanItems, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(item_details, length) {
		this.vue.load_data(JSON.parse(JSON.stringify(item_details)));
		if (length > 0) this.update_status();
	}
	get_items() {
		return this.vue.get_items();
	}
	update_status() {
		this.vue.update_docstatus();
	}
};

frappe.production.ui.LayPlanResult = class {
	constructor(wrapper, on_select = null) {
		this.$wrapper = $(wrapper);
		this.on_select = on_select;
		this.make_body();
	}
	make_body() {
		const app = createApp(LayPlanResult, {
			onSelect: this.on_select,
		});
		if (typeof SetVueGlobals === "function") {
			SetVueGlobals(app);
		}
		this.app = app;
		this.vue = app.mount(this.$wrapper.get(0));
	}
	load_data(data) {
		this.vue.load_data(data);
	}
	set_selected(strategy) {
		this.vue.set_selected(strategy);
	}
};

frappe.production.ui.ItemAttributeList = class {
	constructor({ wrapper } = {}) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(AttributeList, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
};

frappe.production.ui.ClothDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(ClothDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data) {
		this.vue.load_data(data);
	}
	get_data() {
		return this.vue.get_data();
	}
};

frappe.production.ui.CuttingOrderItems = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(CuttingOrderItems, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data) {
		this.vue.load_data(data);
	}
	get_data() {
		return this.vue.get_data();
	}
	set_read_only(value) {
		this.vue.set_read_only(value);
	}
};

frappe.production.ui.CuttingMarker = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(CuttingMarker, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(JSON.parse(JSON.stringify(items || [])));
	}
	get_items() {
		return this.vue.get_items();
	}
};

frappe.production.ui.CutPanelMovementBundle = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(CutPanelMovementBundle, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(JSON.parse(JSON.stringify(items || {})));
	}
	get_items() {
		return JSON.parse(JSON.stringify(this.vue.get_items()));
	}
};

frappe.production.ui.CutBundleEdit = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(CutBundleEdit, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(items) {
		this.vue.load_data(JSON.parse(JSON.stringify(items || {})));
	}
	get_items() {
		return JSON.parse(JSON.stringify(this.vue.get_items()));
	}
};

frappe.production.ui.CuttingCompletionDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(CuttingCompletionDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(item_details, pop_up) {
		this.vue.load_data(`[${item_details}]`, pop_up);
	}
	get_items() {
		return this.vue.get_items();
	}
};

frappe.production.ui.CuttingIncompletionDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(CuttingIncompletionDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(item_details) {
		this.vue.load_data(`[${item_details}]`);
	}
};

frappe.production.ui.CutPlanClothItems = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(CutPlanClothItems, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(item_details, type) {
		this.vue.load_data(JSON.parse(JSON.stringify(item_details || [])), type);
	}
	get_items() {
		return this.vue.get_items();
	}
};

frappe.production.ui.RecutPrintPanelDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(RecutPrintPanelDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data() {
		this.vue.load_data();
	}
	get_items() {
		return this.vue.get_items();
	}
};

frappe.production.ui.RecutPrintPanelView = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(RecutPrintPanelView, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(type) {
		this.vue.load_data(type);
	}
};

for (const [name, component] of Object.entries({
	CuttingDetailReport,
	DailyCutSheetReport,
	DailyProductionReport,
	MultiCCR,
})) {
	frappe.production.ui[name] = class {
		constructor(wrapper) {
			this.$wrapper = $(wrapper);
			const mounted = mount_component(component, this.$wrapper);
			this.app = mounted.app;
			this.vue = mounted.vue;
		}
	};
}

frappe.production.ui.LaySheetCloths = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(LaySheetCloths, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(item_details) {
		this.vue.load_data(JSON.parse(JSON.stringify(item_details || [])));
	}
	get_items() {
		return this.vue.get_items();
	}
	set_status(status) {
		if (typeof this.vue.set_status === "function") {
			this.vue.set_status(status);
		}
	}
};

frappe.production.ui.LaySheetAccessory = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(LaySheetAccessory, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(item_details) {
		this.vue.load_data(JSON.parse(JSON.stringify(item_details || [])));
	}
	get_items() {
		return this.vue.get_items();
	}
	set_status(status) {
		if (typeof this.vue.set_status === "function") {
			this.vue.set_status(status);
		}
	}
};

frappe.production.ui.WOSummary = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(WOSummary, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(item_details, delivered_items, options) {
		this.vue.load_data(
			JSON.parse(JSON.stringify(item_details || [])),
			JSON.parse(JSON.stringify(delivered_items || [])),
			options,
		);
	}
};

frappe.production.ui.QualityInspection = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(QualityInspection, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data, docstatus) {
		this.vue.load_data(JSON.parse(JSON.stringify(data || {})), docstatus);
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
	unmount() {
		this.app.unmount();
	}
};

Object.assign(frappe.production.ui, {
	AlternativeDetail: AlternativeDetailWrapper,
	AlternativeItem: AlternativeItemWrapper,
	FinishingDetail: FinishingDetailWrapper,
	FinishingGRN: FinishingGRNWrapper,
	FinishingInward: FinishingInwardWrapper,
	FinishingIroningExcess: FinishingIroningExcessWrapper,
	FinishingOCR: FinishingOCRWrapper,
	FinishingOldLotTransfer: FinishingOldLotTransferWrapper,
	FinishingPackReturn: FinishingPackReturnWrapper,
	FinishingPlanCompleteTransfer: FinishingPlanCompleteTransferWrapper,
	FinishingPlanDispatch: FinishingPlanDispatchWrapper,
	FinishingQtyDetail: FinishingQtyDetailWrapper,
	FinishingRejectionDetail: FinishingRejectionDetailWrapper,
});

frappe.production.ui.FabricProgram = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(FabricProgram, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(entries) {
		this.vue.load_data(JSON.parse(JSON.stringify(entries || [])));
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_data()));
	}
	get_requirement() {
		return JSON.parse(JSON.stringify(this.vue.get_requirement()));
	}
};

frappe.production.ui.FabricProcesses = class {
	constructor(wrapper, opts = {}) {
		this.$wrapper = $(wrapper);
		this.opts = opts;
		this.make_body();
	}
	make_body() {
		const mounted = mount_component(FabricProcesses, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(payload) {
		// on_change is passed alongside (not inside) the payload so the JSON
		// round-trip cannot strip the callback (same as FabricSwapDetail).
		this.vue.load_data(JSON.parse(JSON.stringify(payload || {})), this.opts.on_change);
	}
	get_steps() {
		return this.vue.get_steps();
	}
};

frappe.production.ui.ActionDetail = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(ActionDetail, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data, previous = [], preview = false) {
		this.vue.load_data(
			JSON.parse(JSON.stringify(data || [])),
			JSON.parse(JSON.stringify(previous || [])),
			preview,
		);
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_items()));
	}
};

frappe.production.ui.UpdatePrice = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(UpdatePrice, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data) {
		this.vue.load_data(JSON.parse(JSON.stringify(data || {})));
	}
	get_data() {
		return JSON.parse(JSON.stringify(this.vue.get_items()));
	}
};

frappe.production.ui.EssdeeProductionOrder = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(ProductionOrderEntry, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data, can_edit = false) {
		this.vue.load_data(JSON.parse(JSON.stringify(data || {})), can_edit);
	}
	set_settings() {}
	set_edit(value) {
		this.vue.set_edit(value);
	}
	get_final_output() {
		return JSON.parse(JSON.stringify(this.vue.get_final_output()));
	}
};

frappe.production.ui.TimeAction = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(TimeAction, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data) {
		this.vue.load_data(JSON.parse(JSON.stringify(data || [])));
	}
	async get_data() {
		const result = await this.vue.get_data();
		return {
			items: JSON.parse(JSON.stringify(result.items || [])),
			changed: Boolean(result.changed),
		};
	}
};

frappe.production.ui.TimeActionReport = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(TimeActionReport, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
};

frappe.production.ui.TimeActionPreview = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(TimeActionPreview, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	load_data(data, startDate) {
		this.vue.load_data(JSON.parse(JSON.stringify(data || {})), startDate);
	}
};

frappe.production.ui.WorkStation = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(WorkStation, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
	async load_data(data, type) {
		await this.vue.load_data(JSON.parse(JSON.stringify(data || {})), type);
	}
	set_attributes() {
		this.vue.set_attributes();
	}
	get_items() {
		return JSON.parse(JSON.stringify(this.vue.get_items()));
	}
};

frappe.production.ui.TandAUpdate = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(TandAUpdate, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
};

frappe.production.ui.TimeAndActionOrderTracking = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(TimeAndActionOrderTracking, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
};

frappe.production.ui.TimeAndActionWeeklyReport = class {
	constructor(wrapper) {
		this.$wrapper = $(wrapper);
		const mounted = mount_component(TimeAndActionWeeklyReport, this.$wrapper);
		this.app = mounted.app;
		this.vue = mounted.vue;
	}
};
