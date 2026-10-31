<template>
	<section class="purchase-lot-frame merch-lot-frame">
		<FabricDocumentWorkspace
			doctype="SD YRP Lot"
			title="Lot"
			:workspace="shellWorkspace"
			:loading="loading"
			:error="loadError || (hasStaleError ? actionError : '')"
			:dirty="isDirty"
			:acting="acting"
			:show-lifecycle-actions="false"
			:live-reload="refresh"
			@reload="reload"
		>
			<template #header="{ headingId }">
				<LotIdentity
					:name="record?.name || ''"
					:draft-name="form.lot_name || ''"
					:item="form.item || ''"
					:delivery-date="form.expected_delivery_date || ''"
					:status="form.status || 'Open'"
					:heading-id="headingId"
					editing
				/>
			</template>
			<template #header-actions>
				<DocumentActionStrip
					class="lot-editor-actions"
					:actions="editorActions"
				/>
			</template>
			<template #matrix>
				<Message
					v-if="quantityWarning"
					severity="warn"
					:closable="false"
				>
					{{ quantityWarning }}
				</Message>
				<Tabs
					v-model:value="activeTab"
					scrollable
					class="lot-tabs erp-tabs"
				>
					<TabList class="lot-tablist">
						<Tab
							v-for="tab in tabs"
							:key="tab.key"
							:value="tab.key"
						>
							{{ tab.label }}
							<span v-if="tab.count !== null">{{ tab.count }}</span>
							<span v-else-if="tab.key === 'order-items'">
								{{ itemDetails?.items.length || 0 }}
							</span>
						</Tab>
					</TabList>
					<TabPanels
						ref="panels"
						class="lot-panels"
					>
						<TabPanel
							v-if="activeTab === 'details'"
							value="details"
						>
							<MerchLotEditorDetails
								:form="form"
								:derived="derived"
								:fields="fields"
								:fabric-meta="fabricMeta"
								:attempted-save="attemptedSave"
								:disabled="Boolean(acting)"
								@set-field="setField"
								@fabric-rows="form.lot_fabric_details = $event"
							/>
						</TabPanel>
						<TabPanel
							v-else-if="activeTab === 'order-items'"
							value="order-items"
						>
							<MerchBoxQuantityEditor
								v-model:item-details="itemDetails"
								v-model:composer-open="composerOpen"
								:production-order="form.production_order || ''"
								:has-order-details="Boolean(orderItemDetails.length)"
								:is-locked="locks.order_details"
								:box-locked="locks.box_locked"
								:disabled="Boolean(acting)"
							/>
						</TabPanel>
						<TabPanel
							v-else-if="activeTab === 'order-details'"
							value="order-details"
						>
							<MerchColourwiseEditor
								:groups="orderItemDetails"
								:colour-attribute="colourAttribute"
								:version="derived.version || ''"
								:is-locked="locks.order_details"
								:disabled="Boolean(acting)"
							/>
							<LotOrderDetailsTab
								v-if="readOnlyWorkspace.order_details"
								:order-details="readOnlyWorkspace.order_details"
							/>
						</TabPanel>
						<TabPanel
							v-else-if="activeTab === 'fabric'"
							value="fabric"
						>
							<LotFabricTab
								:fabrics="readOnlyWorkspace.fabrics"
								:other-conversions="readOnlyWorkspace.other_conversions"
							/>
						</TabPanel>
					</TabPanels>
				</Tabs>
			</template>
			<template #rail>
				<MerchLotDocuments :lot-id="lotId" />
			</template>
		</FabricDocumentWorkspace>
		<DocumentConfirmationDialog
			v-model:visible="reloadItemsVisible"
			title="Reload Order Items?"
			message="Changing Item Production Detail reloads the box quantities from the server."
			confirm-label="Reload Order Items"
			cancel-label="Keep Editing"
			severity="warn"
			@confirm="confirmReloadItems"
		/>
		<DocumentErrorDialog
			:message="hasStaleError ? '' : actionError"
			retry-label="Reload"
			@dismiss="actionError = ''"
			@retry="load"
		/>
	</section>
</template>
<script setup>
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import Message from "primevue/message"
import { computed, nextTick, provide, ref, watch } from "vue"
import { ENTRY_GRID_INVALID_KEY } from "../../../components/common/entryGrid.js"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import MerchLotEditorDetails from "./MerchLotEditorDetails.vue"
import MerchLotDocuments from "./MerchLotDocuments.vue"
import LotOrderDetailsTab from "../../purchase/lot/LotOrderDetailsTab.vue"
import LotFabricTab from "../../purchase/lot/LotFabricTab.vue"
import LotIdentity from "../../purchase/lot/LotIdentity.vue"
import MerchColourwiseEditor from "./MerchColourwiseEditor.vue"
import MerchBoxQuantityEditor from "./MerchBoxQuantityEditor.vue"
import { useMerchLotEditor } from "./useMerchLotEditor.js"
import { totalsWarning } from "./merchLotViews.js"
import "../../purchase/lot/lot.css"
import "./merchLot.css"
const props = defineProps({ lotId: { type: String, default: "" } })
const {
	form,
	derived,
	record,
	fields,
	locks,
	colourAttribute,
	itemDetails,
	orderItemDetails,
	readOnlyWorkspace,
	invalidRegistry,
	fabricMeta,
	loading,
	acting,
	loadError,
	actionError,
	attemptedSave,
	composerOpen,
	reloadItemsVisible,
	isDirty,
	hasStaleError,
	shellWorkspace,
	tabs,
	activeTab,
	editorActions,
	setField,
	confirmReloadItems,
	reload,
	refresh,
	load,
} = useMerchLotEditor(props.lotId)
provide(ENTRY_GRID_INVALID_KEY, invalidRegistry)
const quantityWarning = computed(() =>
	totalsWarning(itemDetails.value, orderItemDetails.value, derived.packing_combo),
)
const panels = ref(null)
watch(activeTab, async () => {
	await nextTick()
	if (panels.value?.$el) panels.value.$el.scrollTop = 0
})
</script>
