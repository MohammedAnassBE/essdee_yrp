<template>
	<Tabs :value="activeTab" scrollable class="pd-product-tabs erp-tabs" @update:value="emit('update:active-tab', $event)">
		<TabList>
			<Tab v-for="tab in visibleTabs" :key="tab.key" :value="tab.key">{{ tab.label }}</Tab>
		</TabList>
		<TabPanels>
			<TabPanel value="basic">
				<div class="pd-product-tabs__panel">
					<div v-for="group in PRODUCT_FIELD_GROUPS.basic" :key="group.key" class="pd-product-fields-group">
						<h2>{{ group.label }}</h2>
						<ProductFieldsPanel
							:fields="group.fields"
							:tables="group.tables || []"
							:form="form"
							:is-new="isNew"
							:meta-by-name="metaByName"
							:link-filters="workspace.link_filters || {}"
							:disabled="fieldsDisabled"
							@update="forwardFieldUpdate"
						/>
						<ProductSizeChips
							v-if="group.key === 'sizes'"
							:rows="form.sizes || []"
							:labels="workspace.size_labels || {}"
							:has-size-range="Boolean(form.size_range)"
						/>
					</div>
				</div>
			</TabPanel>
			<TabPanel value="silhouette">
				<div class="pd-product-tabs__panel">
					<ProductSilhouette
						doctype="SD YRP Product"
						:record="record"
						:readonly="!canUploadImages"
						:can-upload="canUploadImages"
						:busy="mediaBusy"
						:is-new="isNew"
						:editing="!fieldsDisabled"
						@update-field="forwardFieldUpdate"
						@edit-requested="emit('edit-requested')"
						@operation-started="emit('operation-started')"
						@operation-finished="emit('operation-finished', $event)"
					/>
					<ProductImagePicker
						:model-value="images.placement"
						label="Placement"
						:readonly="!canEditImages"
						@update:model-value="emit('update-image-group', 'placement', $event)"
					/>
				</div>
			</TabPanel>
			<TabPanel value="trims">
				<ProductImagePicker
					:model-value="images.trims"
					label="Trims"
					:readonly="!canEditImages"
					@update:model-value="emit('update-image-group', 'trims', $event)"
				/>
			</TabPanel>
			<TabPanel value="colours">
				<div class="pd-product-tabs__panel">
					<ProductColours
						v-if="!isSetItem"
						:model-value="form.product_colours || []"
						:disabled="fieldsDisabled"
						@update:model-value="forwardFieldUpdate('product_colours', $event)"
					/>
					<ProductFieldsPanel
						v-else
						:tables="colourTables"
						:form="form"
						:is-new="isNew"
						:meta-by-name="metaByName"
						:link-filters="workspace.link_filters || {}"
						:disabled="fieldsDisabled"
						@update="forwardFieldUpdate"
					/>
					<ProductTrimCombination
						:model-value="images.combination"
						:colours="trimColours"
						:is-set-item="isSetItem"
						:readonly="!canEditImages"
						@update:model-value="emit('update-image-group', 'combination', $event)"
					/>
				</div>
			</TabPanel>
			<TabPanel value="graphics">
				<ProductGraphics
					:docname="record.name"
					:rows="record.product_designs || []"
					:readonly="!canUploadImages"
					:can-upload="canUploadImages"
					:busy="mediaBusy"
					:is-new="isNew"
					:editing="!fieldsDisabled"
					@update:rows="forwardFieldUpdate('product_designs', $event)"
					@edit-requested="emit('edit-requested')"
					@operation-started="emit('operation-started')"
					@operation-finished="emit('operation-finished', $event)"
				/>
			</TabPanel>
			<TabPanel value="accessories">
				<div class="pd-product-tabs__panel">
					<ProductGraphics
						:docname="record.name"
						:rows="record.product_box_details || []"
						is-box
						:readonly="!canUploadImages"
						:can-upload="canUploadImages"
						:busy="mediaBusy"
						:is-new="isNew"
						:editing="!fieldsDisabled"
						@update:rows="forwardFieldUpdate('product_box_details', $event)"
						@edit-requested="emit('edit-requested')"
						@operation-started="emit('operation-started')"
						@operation-finished="emit('operation-finished', $event)"
					/>
					<ProductImagePicker
						:model-value="images.accessories"
						label="Accessory"
						:readonly="!canEditImages"
						@update:model-value="emit('update-image-group', 'accessories', $event)"
					/>
				</div>
			</TabPanel>
			<TabPanel value="measurement">
				<div class="pd-product-tabs__panel">
					<ProductFieldsPanel
						:fields="PRODUCT_FIELD_GROUPS.measurement"
						:form="form"
						:is-new="isNew"
						:meta-by-name="metaByName"
						:link-filters="workspace.link_filters || {}"
						:disabled="fieldsDisabled"
						@update="forwardFieldUpdate"
					/>
					<ProductMeasurementPanel :measurement="workspace.measurement" :is-set-item="isSetItem" readonly />
				</div>
			</TabPanel>
			<TabPanel v-if="!isNew" value="costing">
				<ProductCostingList
					:rows="workspace.costing"
					:product-name="record.name"
					:can-create="canCreateCosting"
					:readonly="!canCreateCosting"
				/>
			</TabPanel>
			<TabPanel value="extras">
				<ProductFieldsPanel
					:tables="PRODUCT_FIELD_GROUPS.extrasTables"
					:form="form"
					:is-new="isNew"
					:meta-by-name="metaByName"
					:link-filters="workspace.link_filters || {}"
					:disabled="fieldsDisabled"
					@update="forwardFieldUpdate"
				/>
			</TabPanel>
		</TabPanels>
	</Tabs>
</template>

<script setup>
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"

import { PRODUCT_FIELD_GROUPS } from "../pdViews.js"
import ProductColours from "./ProductColours.vue"
import ProductCostingList from "./ProductCostingList.vue"
import ProductFieldsPanel from "./ProductFieldsPanel.vue"
import ProductGraphics from "./ProductGraphics.vue"
import ProductImagePicker from "./ProductImagePicker.vue"
import ProductMeasurementPanel from "./ProductMeasurementPanel.vue"
import ProductSilhouette from "./ProductSilhouette.vue"
import ProductSizeChips from "./ProductSizeChips.vue"
import ProductTrimCombination from "./ProductTrimCombination.vue"

defineProps({
	activeTab: { type: String, required: true },
	visibleTabs: { type: Array, required: true },
	workspace: { type: Object, required: true },
	record: { type: Object, required: true },
	form: { type: Object, required: true },
	images: { type: Object, required: true },
	metaByName: { type: Object, required: true },
	colourTables: { type: Array, required: true },
	trimColours: { type: Array, required: true },
	isNew: { type: Boolean, default: false },
	isSetItem: { type: Boolean, default: false },
	fieldsDisabled: { type: Boolean, default: false },
	canEditImages: { type: Boolean, default: false },
	canUploadImages: { type: Boolean, default: false },
	canCreateCosting: { type: Boolean, default: false },
	mediaBusy: { type: Boolean, default: false },
})
const emit = defineEmits([
	"update:active-tab",
	"update-field",
	"update-image-group",
	"edit-requested",
	"operation-started",
	"operation-finished",
])

function forwardFieldUpdate(fieldname, value) {
	emit("update-field", fieldname, value)
}
</script>
