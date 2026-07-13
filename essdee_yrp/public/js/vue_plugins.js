import { createApp } from "vue";

import AccessoryItems from "./Item_Po_detail/AccessoryItems.vue";
import BundleGroup from "./Item_Po_detail/BundleGroup.vue";
import ClothAccessory from "./Item_Po_detail/ClothAccessory.vue";
import ClothAccessoryCombination from "./Item_Po_detail/ClothAccessoryCombination.vue";
import CombinationItemDetail from "./Item_Po_detail/CombinationItemDetail.vue";
import CuttingItemDetail from "./Item_Po_detail/CuttingItemDetail.vue";
import EmblishmentDetails from "./Item_Po_detail/EmblishmentDetails.vue";
import FabricSwapDetail from "./Item_Po_detail/FabricSwapDetail.vue";
import LotOrderedDetail from "./ProductionOrder/LotOrderedDetail.vue";
import FabricProgram from "./Lot/FabricProgram.vue";
import FabricProcesses from "./Fabric/FabricProcesses.vue";

frappe.provide("frappe.production.ui");

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
