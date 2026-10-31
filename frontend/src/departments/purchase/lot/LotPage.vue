<template>
	<DepartmentPage
		title="Lot"
		back-to="/purchase/lots"
		back-label="Lots"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="purchase-lot-frame">
			<FabricDocumentWorkspace
				doctype="SD YRP Lot"
				title="Lot"
				:workspace="shellWorkspace"
				:loading="loading"
				:error="loadError"
				:acting="acting"
				:show-lifecycle-actions="false"
				:live-reload="refreshInBackground"
				@reload="load(true)"
			>
				<template #header="{ headingId }">
					<LotIdentity :name="workspace.name || lotId" :item="item" :delivery-date="deliveryDate" :status="workspace.status" :heading-id="headingId" />
				</template>
				<template #header-actions><DocumentActionStrip :actions="lotActions" /></template>
				<template #matrix>
					<Tabs v-model:value="activeTab" scrollable class="lot-tabs erp-tabs">
						<TabList ref="tabList" class="lot-tablist">
							<Tab v-for="tab in LOT_TABS" :key="tab.key" :value="tab.key">
								{{ tab.label }}
								<span v-if="lotTabCount(workspace, tab.key) !== null">{{ lotTabCount(workspace, tab.key) }}</span>
							</Tab>
						</TabList>
						<TabPanels ref="tabPanels" class="lot-panels">
							<TabPanel v-if="activeTab === 'lot'" value="lot">
								<LotViewMain v-model:expanded="expanded" :workspace="workspace" :scroll-to="scrollTo" />
							</TabPanel>
							<TabPanel v-else-if="activeTab === 'fabric'" value="fabric">
								<LotEmptyState
									v-if="!workspace.permissions?.can_write && !workspace.fabrics?.length && !workspace.other_conversions?.length"
									title="No cloth program yet"
									reason="No cloth routes are planned for this Lot."
								/>
								<LotFabricTab
									v-else
									:fabrics="workspace.fabrics || []"
									:lot="workspace.name" :modified="workspace.modified" :can-write="Boolean(workspace.permissions?.can_write)" @changed="load(true)"
									:other-conversions="workspace.other_conversions || []"
								/>
							</TabPanel>
							<TabPanel v-else-if="activeTab === 'bom'" value="bom">
								<LotBomPanel :workspace="workspace" />
							</TabPanel>
						</TabPanels>
					</Tabs>
				</template>
				<template #rail>
					<LotDocumentsRail
						ref="documentsRail"
						:documents="documents"
						:loading="documentsLoading"
						:error="documentsError"
						@retry="loadDocuments"
						@open="openDocument"
					/>
				</template>
			</FabricDocumentWorkspace>
		</section>
		<LotPurchaseOrderDialog v-model:visible="purchaseOrderVisible" :lot="lotId" :mode="purchaseOrderMode" @changed="load(true)" />
		<LotDocumentDialog
			v-model:visible="documentVisible"
			:lot="lotId"
			:doctype="selectedDocument.doctype"
			:name="selectedDocument.name"
			@hide="documentsRail?.restoreFocus()"
		/>
	</DepartmentPage>
</template>

<script setup>
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getLotDocuments, getLotWorkspace } from "../../../api/purchase.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import { useDuplicateAction } from "../../../composables/useDuplicateAction.js"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import LotIdentity from "./LotIdentity.vue"
import LotPurchaseOrderDialog from "./LotPurchaseOrderDialog.vue"
import { lotPurchaseSummaryRoute, purchaseLotActions } from "./lotPurchaseActions.js"
import { editTabFor } from "./lotEditor.js"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import { PURCHASE_ROUTES, isCurrentRecordRequest } from "../purchaseViews.js"
import LotBomPanel from "./LotBomPanel.vue"
import LotDocumentDialog from "./LotDocumentDialog.vue"
import LotDocumentsRail from "./LotDocumentsRail.vue"
import LotEmptyState from "./LotEmptyState.vue"
import LotFabricTab from "./LotFabricTab.vue"
import LotViewMain from "./LotViewMain.vue"
import { lotTabCount } from "./lotViews.js"
import { LOT_TABS } from "./lotLayout.js"
import { useLotLayout } from "./useLotLayout.js"
import "./lot.css"

const props = defineProps({ lotId: { type: String, required: true } })
const router = useRouter()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const acting = ref("")
const documents = ref({})
const documentsLoading = ref(true)
const documentsError = ref("")
const documentsRail = ref(null)
const tabList = ref(null)
const tabPanels = ref(null)
const documentVisible = ref(false)
const purchaseOrderVisible = ref(false)
const purchaseOrderMode = ref("link")
const selectedDocument = ref({ doctype: "", name: "" })
let loadSequence = 0
// Responses that land after leaving the page are dropped by the sequence checks.
onBeforeUnmount(() => { loadSequence += 1 })
let documentsSequence = 0
const shellWorkspace = computed(() =>
	loading.value || !workspace.value.name
		? {}
		: {
				...workspace.value,
				record: {
					doctype: "SD YRP Lot",
					name: workspace.value.name,
					status: workspace.value.status,
					modified: workspace.value.modified,
				},
			},
)
const headerValues = computed(
	() => new Map((workspace.value.header || []).map((field) => [field.fieldname, field.value])),
)
const item = computed(() => headerValues.value.get("item"))
const deliveryDate = computed(() => headerValues.value.get("expected_delivery_date"))
const { activeTab, expanded, scrollTo } = useLotLayout(LOT_TABS, useRoute(), router)

const duplicateAction = useDuplicateAction({
	canCreate: () => workspace.value.permissions?.can_create,
	newRouteName: PURCHASE_ROUTES.lotNew,
	name: () => workspace.value.name,
	busy: acting,
	router,
})
const lotActions = computed(() => [
	...purchaseLotActions(workspace.value, runLotAction, acting.value),
	...(duplicateAction.value ? [duplicateAction.value] : []),
])
function runLotAction(key) {
	if (key === "edit") return openEditor()
	if (key === "purchase_summary") return router.push(lotPurchaseSummaryRoute(props.lotId))
	purchaseOrderMode.value = key === "link_po" ? "link" : "unlink"
	purchaseOrderVisible.value = true
}
function openEditor() {
 return router.push({ name: PURCHASE_ROUTES.lotEdit, params: { lotId: props.lotId },
  query: { tab: editTabFor(activeTab.value) },
  state: preserveListNavigationState(props.lotId, workspace.value.modified) })
}

async function load(refresh = false) {
	const sequence = ++loadSequence
	const requestedName = props.lotId
	loading.value = true
	acting.value = refresh ? "reload" : ""
	loadError.value = ""
	workspace.value = {}
	loadDocuments()
	try {
		const payload = await getLotWorkspace(requestedName)
		if (isCurrentRecordRequest(requestedName, props.lotId, sequence, loadSequence))
			workspace.value = payload
	} catch (reason) {
		if (sequence === loadSequence)
			loadError.value = reason?.message || "Unable to load this Lot."
	} finally {
		if (sequence === loadSequence) {
			loading.value = false
			acting.value = ""
		}
	}
}

/** Live update: refetches the Lot in place, keeping the page, tab and scroll. */
async function refreshInBackground() {
	const sequence = ++loadSequence
	const requestedName = props.lotId
	const payload = await getLotWorkspace(requestedName)
	if (isCurrentRecordRequest(requestedName, props.lotId, sequence, loadSequence)) workspace.value = payload
}

async function loadDocuments() {
	const sequence = ++documentsSequence
	const requestedName = props.lotId
	documentsLoading.value = true
	documentsError.value = ""
	documents.value = {}
	try {
		const payload = await getLotDocuments(requestedName)
		if (isCurrentRecordRequest(requestedName, props.lotId, sequence, documentsSequence))
			documents.value = payload
	} catch (reason) {
		if (sequence === documentsSequence)
			documentsError.value = reason?.message || "Unable to load linked Purchase documents."
	} finally {
		if (sequence === documentsSequence) documentsLoading.value = false
	}
}

function openDocument(document) {
	selectedDocument.value = document
	documentVisible.value = true
}
watch(activeTab, async () => {
	await nextTick()
	if (tabPanels.value?.$el) tabPanels.value.$el.scrollTop = 0
	const tabListElement = tabList.value?.$el
	if (
		window.matchMedia("(max-width: 900px)").matches &&
		tabListElement?.getBoundingClientRect().top < 0
	) {
		tabListElement.scrollIntoView({ block: "nearest" })
	}
})
watch(
	() => props.lotId,
	() => {
		documentVisible.value = false
		purchaseOrderVisible.value = false
		load()
	},
	{ immediate: true },
)
</script>
