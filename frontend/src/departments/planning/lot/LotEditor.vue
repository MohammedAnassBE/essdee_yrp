<template>
	<section class="purchase-lot-frame planning-lot-frame">
		<FabricDocumentWorkspace doctype="SD YRP Lot" title="Lot" :workspace="shellWorkspace" :loading="loading" :error="loadError || actionError" :dirty="isDirty" :acting="acting" :show-lifecycle-actions="false" :live-reload="refresh" @reload="reload">
			<template #header="{ headingId }"><LotIdentity :name="record?.name || ''" :draft-name="form.lot_name || ''" :item="form.item || ''" :delivery-date="form.expected_delivery_date || ''" :status="form.status || 'Open'" :heading-id="headingId" editing /></template>
			<template #header-actions><DocumentActionStrip class="lot-editor-actions" :actions="editorActions" /></template>
			<template #matrix>
				<Tabs v-model:value="activeTab" scrollable class="lot-tabs erp-tabs">
					<TabList class="lot-tablist"><Tab v-for="tab in tabs" :key="tab.key" :value="tab.key">{{ tab.label }}</Tab></TabList>
					<TabPanels ref="panels" class="lot-panels">
						<TabPanel v-if="activeTab === 'lot'" value="lot">
							<LotEditorMain v-model:expanded="expanded" :form="form" :derived="derived" :fields="fields" :fabric-meta="fabricMeta" :order-item-details="orderItemDetails" :scroll-to="scrollTo" :attempted-save="attemptedSave" :disabled="Boolean(acting)" @set-field="setField" @fabric-rows="form.lot_fabric_details = $event">
								<template #quantities><LotOrderItemsEditor v-model:item-details="itemDetails" v-model:composer-open="composerOpen" :production-order="form.production_order || ''" :has-order-details="Boolean(orderItemDetails.length)" :is-locked="locks.order_details" :disabled="Boolean(acting)" /></template>
								<template #order-details><LotOrderDetailsEditor :groups="orderItemDetails" :colour-attribute="colourAttribute" :version="derived.version || ''" :is-locked="locks.order_details" :disabled="Boolean(acting)" /></template>
							</LotEditorMain>
						</TabPanel>
						<TabPanel v-else :value="activeTab"><LotEditorTabWorkspace :tab="activeTab" :workspace="tabWorkspace" :loading="tabLoading" :error="tabError" @retry="loadTabWorkspace" /></TabPanel>
					</TabPanels>
				</Tabs>
			</template>
			<template #rail><LotEditorRail :lot-id="lotId" /></template>
		</FabricDocumentWorkspace>
		<DocumentConfirmationDialog v-model:visible="reloadItemsVisible" title="Reload Order Items?" message="Changing Item Production Detail reloads the box quantities from the server." confirm-label="Reload Order Items" cancel-label="Keep Editing" severity="warn" @confirm="confirmReloadItems" />
	</section>
</template>
<script setup>
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { nextTick, ref, watch } from "vue"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import LotEditorMain from "../../purchase/lot/LotEditorMain.vue"
import LotEditorTabWorkspace from "../../purchase/lot/LotEditorTabWorkspace.vue"
import LotEditorRail from "./LotEditorRail.vue"
import LotIdentity from "../../purchase/lot/LotIdentity.vue"
import LotOrderDetailsEditor from "../../purchase/lot/LotOrderDetailsEditor.vue"
import LotOrderItemsEditor from "../../purchase/lot/LotOrderItemsEditor.vue"
import { useLotEditor } from "./useLotEditor.js"
import "../../purchase/lot/lot.css"
const props = defineProps({ lotId: { type: String, default: "" } })
const { form, derived, record, fields, locks, colourAttribute, itemDetails, orderItemDetails, fabricMeta, loading, acting, loadError, actionError,
	attemptedSave, composerOpen, reloadItemsVisible, isDirty, shellWorkspace, tabs, activeTab, expanded, scrollTo, editorActions,
	tabWorkspace, tabLoading, tabError, loadTabWorkspace, setField, confirmReloadItems, reload, refresh } = useLotEditor(props.lotId)
const panels = ref(null)
watch(activeTab, async () => { await nextTick(); if (panels.value?.$el) panels.value.$el.scrollTop = 0 })
</script>
