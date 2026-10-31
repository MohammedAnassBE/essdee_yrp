<template>
	<DepartmentPage
		title="Lot"
		back-to="/merch/lots"
		back-label="Lots"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="purchase-lot-frame merch-lot-frame">
			<FabricDocumentWorkspace
				doctype="SD YRP Lot"
				title="Lot"
				:workspace="shellWorkspace"
				:loading="loading"
				:error="loadError"
				:acting="acting"
				:show-lifecycle-actions="false"
				@reload="load"
			>
				<template #header="{ headingId }">
					<LotIdentity
						:name="workspace.name || lotId"
						:item="header.item"
						:delivery-date="header.expected_delivery_date"
						:status="workspace.status"
						:heading-id="headingId"
					/>
				</template>
				<template #header-actions>
					<DocumentActionStrip :actions="actions" />
				</template>
				<template #matrix>
					<Message
						v-if="workspace.name && !workspace.permissions?.can_write"
						severity="secondary"
						:closable="false"
					>
						Read only. You can view this lot. Editing needs write permission on SD YRP
						Lot.
					</Message>
					<Tabs v-model:value="activeTab" scrollable class="lot-tabs erp-tabs">
						<TabList class="lot-tablist">
							<Tab v-for="tab in LOT_TABS" :key="tab.key" :value="tab.key">
								{{ tab.label }}
								<span v-if="lotTabCount(workspace, tab.key) !== null">{{ lotTabCount(workspace, tab.key) }}</span>
							</Tab>
						</TabList>
						<TabPanels class="lot-panels">
							<TabPanel v-if="activeTab === 'lot'" value="lot">
								<LotViewMain v-model:expanded="expanded" :workspace="workspace" :scroll-to="scrollTo" :has-ppo="Boolean(workspace.ppo)" include-empty>
									<template #quantities-actions>
										<Message v-if="workspace.locks?.order_details" severity="warn" :closable="false">Locked: Time &amp; Action exists or the Lot was transferred.</Message>
										<Button v-if="workspace.permissions?.can_write" class="lot-main__action" label="Change box quantity" icon="pi pi-pencil" severity="secondary" text @click="openEditor('lot')" />
									</template>
									<template #order-details-actions>
										<Button v-if="workspace.permissions?.can_write" class="lot-main__action" label="Edit Lot Order Details" icon="pi pi-pencil" severity="secondary" text @click="openEditor('order-details')" />
									</template>
									<template #ppo>
										<MerchLotPpoPanel :ppo="workspace.ppo" :item="header.item" :capability="workspace.capabilities?.change_ppo" :acting="Boolean(acting)" show-panel @update:visible="ppoVisible = $event" />
									</template>
								</LotViewMain>
							</TabPanel>
							<TabPanel v-else-if="activeTab === 'fabric'" value="fabric">
								<div v-if="!workspace.fabrics?.length" class="lot-tab-stack">
									<LotEmptyState title="No cloth program yet." reason="Build Cloth Program picks colours and excess % to plan the demanded cloths." />
									<DocumentActionStrip :actions="actions.filter((action) => action.key === 'build_cloth_programs')" />
								</div>
								<LotFabricTab v-else :fabrics="workspace.fabrics" />
							</TabPanel>
							<TabPanel v-else-if="activeTab === 'dia-conversions'" value="dia-conversions">
								<LotDiaConversionsTab :fabrics="workspace.fabrics || []" :other-conversions="workspace.other_conversions || []" />
							</TabPanel>
							<TabPanel v-else-if="activeTab === 'bom'" value="bom">
								<LotBomPanel :workspace="workspace">
									<template #actions><DocumentActionStrip :actions="actions.filter((action) => action.key === 'calculate_bom')" /></template>
									<MerchLotBomTab :bom="workspace.bom" :additional-items="workspace.bom_additional_items" :can-edit="workspace.capabilities?.update_bom_additional_items?.allowed" :acting="Boolean(acting)" @save="execute('update_bom_additional_items', $event)" @error="actionError = $event" />
								</LotBomPanel>
							</TabPanel>
						</TabPanels>
					</Tabs>
				</template>
				<template #rail>
					<MerchLotDocuments
						:lot-id="lotId"
						:key="workspace.modified"
					/>
				</template>
			</FabricDocumentWorkspace>
		</section>
		<MerchLotPpoPanel
			v-model:visible="ppoVisible"
			:item="header.item"
			:capability="workspace.capabilities?.change_ppo"
			:acting="Boolean(acting)"
			@link="execute('change_ppo', $event)"
		/>
		<MerchClothProgramDialog
			v-model:visible="clothVisible"
			:lot-id="lotId"
			:excess-percentage="Number(header.cloth_excess_percentage || 0)"
			:acting="Boolean(acting)"
			@build="execute('build_cloth_programs', $event)"
			@error="actionError = $event"
		/>
		<LotPurchaseOrderDialog
			v-model:visible="purchaseOrderVisible"
			:lot="lotId"
			:mode="purchaseOrderMode"
			@changed="load"
		/>
		<DocumentConfirmationDialog
			v-model:visible="confirmationVisible"
			:title="confirmationLabel"
			:message="`${confirmationLabel} for ${lotId}?`"
			:confirm-label="confirmationLabel"
			@confirm="confirmCommand"
		/>
		<DocumentErrorDialog
			:message="actionError"
			retry-label="Reload"
			@dismiss="actionError = ''"
			@retry="load"
		/>
	</DepartmentPage>
</template>
<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { executeMerchLotCommand, getMerchLotWorkspace } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import LotIdentity from "../../purchase/lot/LotIdentity.vue"
import LotBomPanel from "../../purchase/lot/LotBomPanel.vue"
import LotViewMain from "../../purchase/lot/LotViewMain.vue"
import { editTabFor } from "../../purchase/lot/lotEditor.js"
import { LOT_TABS } from "../../purchase/lot/lotLayout.js"
import { lotTabCount } from "../../purchase/lot/lotViews.js"
import { useLotLayout } from "../../purchase/lot/useLotLayout.js"
import LotFabricTab from "../../purchase/lot/LotFabricTab.vue"
import LotDiaConversionsTab from "../../purchase/lot/LotDiaConversionsTab.vue"
import LotEmptyState from "../../purchase/lot/LotEmptyState.vue"
import LotPurchaseOrderDialog from "../../purchase/lot/LotPurchaseOrderDialog.vue"
import { purchaseOrderLinkActions } from "../../purchase/lot/lotPurchaseActions.js"
import { useDuplicateAction } from "../../../composables/useDuplicateAction.js"
import { MERCH_ROUTES } from "../merchViews.js"
import { merchLotCommandSuccess, merchLotActions } from "./merchLotViews.js"
import MerchClothProgramDialog from "./MerchClothProgramDialog.vue"
import MerchLotBomTab from "./MerchLotBomTab.vue"
import MerchLotDocuments from "./MerchLotDocuments.vue"
import MerchLotPpoPanel from "./MerchLotPpoPanel.vue"
import "../../purchase/lot/lot.css"
import "./merchLot.css"
const props = defineProps({ lotId: { type: String, required: true } })
const router = useRouter()
const toast = useToast()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const actionError = ref("")
const acting = ref("")
const ppoVisible = ref(false)
const clothVisible = ref(false)
const purchaseOrderVisible = ref(false)
const purchaseOrderMode = ref("link")
const confirmationVisible = ref(false)
const pendingCommand = ref("")
let sequence = 0
const header = computed(() =>
	Object.fromEntries(
		(workspace.value.header || []).map((field) => [field.fieldname, field.value]),
	),
)
const shellWorkspace = computed(() =>
	workspace.value.name ? { record: { ...workspace.value, doctype: "SD YRP Lot" } } : {},
)
const { activeTab, expanded, scrollTo } = useLotLayout(LOT_TABS, useRoute(), router)
const duplicateAction = useDuplicateAction({
	canCreate: () => workspace.value.permissions?.can_create,
	newRouteName: MERCH_ROUTES.lotNew,
	name: () => workspace.value.name,
	busy: acting,
	router,
})
const actions = computed(() => [
	...merchLotActions(workspace.value, selectAction, acting.value),
	...purchaseOrderLinkActions(workspace.value, selectAction, acting.value),
	...(duplicateAction.value ? [duplicateAction.value] : []),
])
const confirmationLabel = computed(
	() => workspace.value.capabilities?.[pendingCommand.value]?.label || "Confirm",
)
function openEditor(tab = activeTab.value) {
	return router.push({
		name: MERCH_ROUTES.lotEdit,
		params: { lotId: props.lotId },
		query: { tab: tab === "order-details" ? tab : editTabFor(tab) },
		state: preserveListNavigationState(props.lotId, workspace.value.modified),
	})
}
function selectAction(command) {
	if (command === "edit") return openEditor()
	if (command === "change_ppo") {
		ppoVisible.value = true
		return
	}
	if (command === "build_cloth_programs") {
		clothVisible.value = true
		return
	}
	if (["link_po", "unlink_po"].includes(command)) {
		purchaseOrderMode.value = command === "link_po" ? "link" : "unlink"
		purchaseOrderVisible.value = true
		return
	}
	pendingCommand.value = command
	confirmationVisible.value = true
}
function confirmCommand() {
	confirmationVisible.value = false
	execute(pendingCommand.value)
}
async function load() {
	const request = ++sequence
	loading.value = true
	loadError.value = ""
	actionError.value = ""
	workspace.value = {}
	try {
		const result = await getMerchLotWorkspace(props.lotId)
		if (request === sequence) workspace.value = result
	} catch (error) {
		if (request === sequence) loadError.value = error.message
	} finally {
		if (request === sequence) {
			loading.value = false
			acting.value = ""
		}
	}
}
async function execute(command, payload = {}) {
	if (acting.value) return
	const request = sequence
	acting.value = command
	actionError.value = ""
	try {
		const result = await executeMerchLotCommand(
			props.lotId,
			command,
			payload,
			workspace.value.modified,
		)
		if (request !== sequence) return
		workspace.value = result
		ppoVisible.value = false
		clothVisible.value = false
		toast.add(merchLotCommandSuccess(command, props.lotId))
	} catch (error) {
		if (request === sequence) actionError.value = error.message
	} finally {
		if (request === sequence) acting.value = ""
	}
}
watch(
	() => props.lotId,
	() => {
		ppoVisible.value = false
		clothVisible.value = false
		purchaseOrderVisible.value = false
		load()
	},
	{ immediate: true },
)
onBeforeUnmount(() => {
	++sequence
})
</script>
