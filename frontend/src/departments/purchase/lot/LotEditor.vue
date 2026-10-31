<template>
	<section class="purchase-lot-frame">
		<FabricDocumentWorkspace doctype="SD YRP Lot" title="Lot" :workspace="shellWorkspace" :loading="loading" :error="loadError || actionError" :dirty="isDirty" :acting="acting" :show-lifecycle-actions="false" :live-reload="refresh" @reload="reload">
			<template #header="{ headingId }"><LotIdentity :name="record?.name || ''" :draft-name="form.lot_name || ''" :item="form.item || ''" :delivery-date="form.expected_delivery_date || ''" :status="form.status || 'Open'" :heading-id="headingId" editing /></template>
			<template #header-actions><DocumentActionStrip class="lot-editor-actions" :actions="editorActions" /></template>
			<template #matrix>
				<Tabs v-model:value="activeTab" scrollable class="lot-tabs erp-tabs">
					<TabList class="lot-tablist"><Tab v-for="tab in tabs" :key="tab.key" :value="tab.key">{{ tab.label }}<span v-if="tab.count !== null">{{ tab.count }}</span><span v-else-if="tab.key === 'order-items'">{{ itemDetails?.items.length || 0 }}</span></Tab></TabList>
					<TabPanels ref="panels" class="lot-panels">
						<TabPanel v-if="activeTab === 'details'" value="details"><LotEditorDetails :form="form" :derived="derived" :fields="fields" :fabric-meta="fabricMeta" :attempted-save="attemptedSave" :disabled="Boolean(acting)" @set-field="setField" @fabric-rows="form.lot_fabric_details = $event" /></TabPanel>
						<TabPanel v-else-if="activeTab === 'order-items'" value="order-items"><LotOrderItemsEditor v-model:item-details="itemDetails" v-model:composer-open="composerOpen" :production-order="form.production_order || ''" :has-order-details="Boolean(orderItemDetails.length)" :disabled="Boolean(acting)" /></TabPanel>
						<TabPanel v-else-if="activeTab === 'order-details'" value="order-details"><LotOrderDetailsEditor :groups="orderItemDetails" :colour-attribute="colourAttribute" :version="derived.version || ''" :is-locked="locks.order_details" :disabled="Boolean(acting)" /></TabPanel>
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
import LotEditorDetails from "./LotEditorDetails.vue"
import LotEditorRail from "./LotEditorRail.vue"
import LotIdentity from "./LotIdentity.vue"
import LotOrderDetailsEditor from "./LotOrderDetailsEditor.vue"
import LotOrderItemsEditor from "./LotOrderItemsEditor.vue"
import { useLotEditor } from "./useLotEditor.js"
import "./lot.css"
const props = defineProps({ lotId: { type: String, default: "" } })
const { form, derived, record, fields, locks, colourAttribute, itemDetails, orderItemDetails, fabricMeta, loading, acting, loadError, actionError,
	attemptedSave, composerOpen, reloadItemsVisible, isDirty, shellWorkspace, tabs, activeTab, editorActions,
	setField, confirmReloadItems, reload, refresh } = useLotEditor(props.lotId)
const panels = ref(null)
watch(activeTab, async () => { await nextTick(); if (panels.value?.$el) panels.value.$el.scrollTop = 0 })
</script>
