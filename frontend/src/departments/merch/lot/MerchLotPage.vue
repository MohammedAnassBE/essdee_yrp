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
							</Tab>
						</TabList>
						<TabPanels class="lot-panels">
							<TabPanel
								v-if="activeTab === 'details'"
								value="details"
							>
								<DocumentOverview
									:fields="detailFields"
									:definitions="MERCH_DETAIL_GROUPS"
									id-prefix="merch-lot"
									aria-label="Lot details"
									include-empty
								/>
							</TabPanel>
							<TabPanel
								v-else-if="activeTab === 'order-items'"
								value="order-items"
							>
								<Message
									v-if="workspace.locks?.order_details"
									severity="warn"
									:closable="false"
								>
									Locked: Time &amp; Action exists or the Lot was transferred.
								</Message>
								<Button
									v-if="workspace.permissions?.can_write"
									label="Change box quantity"
									icon="pi pi-pencil"
									severity="secondary"
									text
									@click="openEditor('order-items')"
								/>
								<LotOrderItemsTab :order-items="workspace.order_items" />
							</TabPanel>
							<TabPanel
								v-else-if="activeTab === 'order-details'"
								value="order-details"
							>
								<Button
									v-if="workspace.permissions?.can_write"
									label="Edit Lot Order Details"
									icon="pi pi-pencil"
									severity="secondary"
									text
									@click="openEditor('order-details')"
								/>
								<LotOrderDetailsTab :order-details="workspace.order_details" />
							</TabPanel>
							<TabPanel
								v-else-if="activeTab === 'fabric'"
								value="fabric"
							>
								<div
									v-if="
										!workspace.fabrics?.length &&
										!workspace.other_conversions?.length
									"
									class="lot-tab-stack"
								>
									<LotEmptyState
										title="No cloth program yet."
										reason="Build Cloth Program picks colours and excess % to plan the demanded cloths."
									/>
									<DocumentActionStrip
										:actions="
											actions.filter(
												(action) => action.key === 'build_cloth_programs',
											)
										"
									/>
								</div>
								<LotFabricTab
									v-else
									:fabrics="workspace.fabrics"
									:other-conversions="workspace.other_conversions"
								/>
							</TabPanel>
							<TabPanel
								v-else-if="activeTab === 'ppo'"
								value="ppo"
							>
								<MerchLotPpoPanel
									v-model:visible="ppoVisible"
									:ppo="workspace.ppo"
									:item="header.item"
									:capability="workspace.capabilities?.change_ppo"
									:acting="Boolean(acting)"
									show-panel
									@link="execute('change_ppo', $event)"
								/>
							</TabPanel>
							<TabPanel
								v-else-if="activeTab === 'bom'"
								value="bom"
							>
								<MerchLotBomTab
									:bom="workspace.bom"
									:additional-items="workspace.bom_additional_items"
									:can-edit="
										workspace.capabilities?.update_bom_additional_items?.allowed
									"
									:acting="Boolean(acting)"
									@save="execute('update_bom_additional_items', $event)"
									@error="actionError = $event"
								/>
							</TabPanel>
							<TabPanel
								v-else-if="activeTab === 'ocr'"
								value="ocr"
							>
								<LotOcrTable
									:payload="workspace.ocr"
									linked
								/>
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
			v-if="activeTab !== 'ppo'"
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
import DocumentOverview from "../../../components/documents/DocumentOverview.vue"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import LotIdentity from "../../purchase/lot/LotIdentity.vue"
import LotOrderItemsTab from "../../purchase/lot/LotOrderItemsTab.vue"
import LotOrderDetailsTab from "../../purchase/lot/LotOrderDetailsTab.vue"
import LotFabricTab from "../../purchase/lot/LotFabricTab.vue"
import LotEmptyState from "../../purchase/lot/LotEmptyState.vue"
import LotOcrTable from "../../sales/LotOcrTable.vue"
import { MERCH_ROUTES } from "../merchViews.js"
import { MERCH_DETAIL_GROUPS, merchLotCommandSuccess, merchLotTabs, merchLotActions } from "./merchLotViews.js"
import MerchClothProgramDialog from "./MerchClothProgramDialog.vue"
import MerchLotBomTab from "./MerchLotBomTab.vue"
import MerchLotDocuments from "./MerchLotDocuments.vue"
import MerchLotPpoPanel from "./MerchLotPpoPanel.vue"
import "../../purchase/lot/lot.css"
import "./merchLot.css"
const props = defineProps({ lotId: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const toast = useToast()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const actionError = ref("")
const acting = ref("")
const ppoVisible = ref(false)
const clothVisible = ref(false)
const confirmationVisible = ref(false)
const pendingCommand = ref("")
let sequence = 0
const header = computed(() =>
	Object.fromEntries(
		(workspace.value.header || []).map((field) => [field.fieldname, field.value]),
	),
)
const detailFields = computed(() => [
	...(workspace.value.header || []),
	...(workspace.value.details || []),
	...(workspace.value.ipd_facts || []),
])
const shellWorkspace = computed(() =>
	workspace.value.name ? { record: { ...workspace.value, doctype: "SD YRP Lot" } } : {},
)
const tabs = computed(() => merchLotTabs(workspace.value))
const activeTab = computed({
	get: () =>
		tabs.value.some((tab) => tab.key === route.query.tab) ? route.query.tab : "details",
	set: (tab) =>
		router.replace({ query: { ...route.query, tab }, state: preserveListNavigationState() }),
})
const actions = computed(() => merchLotActions(workspace.value, selectAction, acting.value))
const confirmationLabel = computed(
	() => workspace.value.capabilities?.[pendingCommand.value]?.label || "Confirm",
)
function openEditor(tab = activeTab.value) {
	return router.push({
		name: MERCH_ROUTES.lotEdit,
		params: { lotId: props.lotId },
		query: { tab: ["order-items", "order-details"].includes(tab) ? tab : "details" },
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
		load()
	},
	{ immediate: true },
)
onBeforeUnmount(() => {
	++sequence
})
</script>
