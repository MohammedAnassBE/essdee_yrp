<template>
	<DepartmentPage
		title="Product Release"
		back-to="/pd/product-releases"
		back-label="Product Releases"
		:show-title="false"
		flat
		full-width
		activity-doctype="SD YRP Product Release"
		:activity-name="record.name || ''"
		:activity-record="record"
	>
		<section class="pd-product-workspace" aria-label="Product Release workspace">
			<div v-if="loading" class="pd-product-workspace__loading" aria-label="Loading Product Release">
				<Skeleton height="5.5rem" />
				<Skeleton height="3.25rem" />
				<Skeleton height="22rem" />
			</div>
			<WorkspaceLoadError
				v-else-if="loadError"
				title="Product Release could not be loaded"
				:message="loadError"
				:loading="loading"
				@retry="load"
			/>
			<template v-else-if="hasWorkspace">
				<header class="pd-product-workspace__header">
					<div class="pd-product-workspace__identity">
						<span class="pd-product-workspace__eyebrow">Product Release · {{ record.name }}</span>
						<div class="pd-product-workspace__title-row">
							<h1>{{ record.item_name || record.style_no || "Product Release" }}</h1>
							<div class="pd-product-workspace__chips" aria-label="Product Release details">
								<span class="pd-product-workspace__chip">Tech Pack #{{ record.tech_pack_no || 0 }}</span>
							</div>
						</div>
					</div>
					<div class="pd-product-workspace__actions">
						<RouterLink
							v-if="productPath"
							:to="productPath"
							class="pd-release-product-link"
						>
							<i class="pi pi-arrow-up-right" aria-hidden="true" />
							<span>Open Product</span>
						</RouterLink>
						<DocumentActionStrip :actions="documentActions" />
						<CustomPrintButtons v-if="record?.name" doctype="SD YRP Product Release" :record="record" :permissions="permissions" :disabled="deleting" />
						<DocumentPrintButton
							v-if="permissions.can_print"
							doctype="SD YRP Product Release"
							:name="record.name"
							:formats="workspace.print_formats || []"
							:disabled="deleting"
						/>
					</div>
				</header>

				<Tabs v-model:value="activeTab" scrollable class="pd-product-tabs erp-tabs">
					<TabList>
						<Tab v-for="tab in tabs" :key="tab.key" :value="tab.key">{{ tab.label }}</Tab>
					</TabList>
					<TabPanels>
						<TabPanel value="basic">
							<div class="pd-product-tabs__panel">
								<figure v-if="record.front_image" class="pd-release-front-image erp-card">
									<figcaption>Product Image</figcaption>
									<img :src="record.front_image" :alt="record.item_name || record.style_no || 'Product image'" />
								</figure>
								<div v-for="group in PRODUCT_FIELD_GROUPS.basic" :key="group.label" class="pd-product-fields-group">
									<h2>{{ group.label }}</h2>
									<ProductFieldsPanel
										:fields="group.fields"
										:tables="group.tables || []"
										:form="record"
										:meta-by-name="metadataByName"
										disabled
									/>
									<ProductSizeChips
										v-if="group.key === 'sizes'"
										:rows="record.sizes || []"
										:labels="workspace.size_labels || {}"
										:has-size-range="Boolean(record.size_range)"
									/>
								</div>
							</div>
						</TabPanel>
						<TabPanel value="silhouette">
							<div class="pd-product-tabs__panel">
								<ProductSilhouette doctype="SD YRP Product Release" :record="record" readonly />
								<ProductImagePicker :model-value="images.placement" label="Placement" readonly />
							</div>
						</TabPanel>
						<TabPanel value="trims">
							<ProductImagePicker :model-value="images.trims" label="Trims" readonly />
						</TabPanel>
						<TabPanel value="colours">
							<div class="pd-product-tabs__panel">
								<ProductFieldsPanel
									:tables="colourTables"
									:form="record"
									:meta-by-name="metadataByName"
									disabled
								/>
								<ProductTrimCombination
									:model-value="images.combination"
									:colours="colours"
									:is-set-item="isSetItem"
									readonly
								/>
							</div>
						</TabPanel>
						<TabPanel value="graphics">
							<ProductGraphics :docname="record.name" :rows="record.product_designs || []" readonly />
						</TabPanel>
						<TabPanel value="accessories">
							<div class="pd-product-tabs__panel">
								<ProductGraphics
									:docname="record.name"
									:rows="record.product_box_details || []"
									is-box
									readonly
								/>
								<ProductImagePicker :model-value="images.accessories" label="Accessory" readonly />
							</div>
						</TabPanel>
						<TabPanel value="measurement">
							<div class="pd-product-tabs__panel">
								<ProductFieldsPanel
									:fields="PRODUCT_FIELD_GROUPS.measurement"
									:form="record"
									:meta-by-name="metadataByName"
									disabled
								/>
								<ProductMeasurementPanel :measurement="measurement" :is-set-item="isSetItem" readonly />
							</div>
						</TabPanel>
					</TabPanels>
				</Tabs>
			</template>
		</section>

		<DocumentConfirmationDialog
			v-model:visible="deleteVisible"
			title="Delete Product Release?"
			:message="`Delete ${record.name || 'this Product Release'}? This action cannot be undone.`"
			confirm-label="Delete Product Release"
			confirm-icon="pi pi-trash"
			:busy="deleting"
			@confirm="confirmDelete"
		/>
		<DocumentErrorDialog
			:message="actionError"
			title="Product Release action could not be completed"
			@dismiss="actionError = ''"
		/>
	</DepartmentPage>
</template>

<script setup>
import CustomPrintButtons from "../../components/documents/CustomPrintButtons.vue"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { deleteProductRelease, getProductReleaseWorkspace } from "../../api/pd.js"
import { getMeta } from "../../api/frappe.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import ProductFieldsPanel from "./components/ProductFieldsPanel.vue"
import ProductGraphics from "./components/ProductGraphics.vue"
import ProductImagePicker from "./components/ProductImagePicker.vue"
import ProductMeasurementPanel from "./components/ProductMeasurementPanel.vue"
import ProductSizeChips from "./components/ProductSizeChips.vue"
import ProductSilhouette from "./components/ProductSilhouette.vue"
import ProductTrimCombination from "./components/ProductTrimCombination.vue"
import { PD_ROUTES, PRODUCT_FIELD_GROUPS, pdRecordPath, releaseTabs } from "./pdViews.js"
import "./components/pd.css"

const RELEASE_DOCTYPE = "SD YRP Product Release"
const PRODUCT_DOCTYPE = "SD YRP Product"
const props = defineProps({ releaseId: { type: String, default: "" } })
const router = useRouter()
const workspace = ref({})
const metadataByName = ref({})
const activeTab = ref("basic")
const loading = ref(true)
const deleting = ref(false)
const deleteVisible = ref(false)
const loadError = ref("")
const actionError = ref("")
const tabs = releaseTabs()
let loadSequence = 0
let isUnmounted = false
let deletingReleaseId = ""

const record = computed(() => workspace.value.record || {})
const permissions = computed(() => workspace.value.permissions || {})
const images = computed(() => workspace.value.images || emptyImages())
const measurement = computed(() => workspace.value.measurement || { groups: {}, images: [] })
const colours = computed(() => workspace.value.colours || { is_set_item: false, top: [], bottom: [], all: [] })
const isSetItem = computed(() => Boolean(Number(record.value.is_set_item)))
const colourTables = computed(() => isSetItem.value ? ["product_set_colours"] : ["product_colours"])
const hasWorkspace = computed(() => Boolean(record.value.name))
const productPath = computed(() => workspace.value.product
	? pdRecordPath("product", workspace.value.product).replace(/^\/web/, "")
	: "")
const documentActions = computed(() => permissions.value.can_delete ? [{
	key: "delete",
	label: "Delete",
	icon: "pi pi-trash",
	disabled: deleting.value,
	command: () => { deleteVisible.value = true },
}] : [])

function emptyImages() {
	return { placement: [], trims: [], combination: [], accessories: [] }
}

function indexMetadata(metadata) {
	const indexed = Object.fromEntries(metadata.filter((item) => item?.name).map((item) => [item.name, item]))
	if (indexed[RELEASE_DOCTYPE]) indexed[PRODUCT_DOCTYPE] = indexed[RELEASE_DOCTYPE]
	return indexed
}

async function load(releaseId = props.releaseId, previousReleaseId = releaseId) {
	const routeChanged = previousReleaseId !== undefined && releaseId !== previousReleaseId
	if (!releaseId || (!routeChanged && deletingReleaseId === releaseId)) return
	const sequence = ++loadSequence
	loading.value = true
	deleting.value = false
	loadError.value = ""
	actionError.value = ""
	deleteVisible.value = false
	try {
		const [payload, metadata] = await Promise.all([
			getProductReleaseWorkspace(releaseId),
			getMeta(RELEASE_DOCTYPE),
		])
		if (!isCurrentLoad(sequence)) return
		workspace.value = payload || {}
		metadataByName.value = indexMetadata(metadata)
	} catch (reason) {
		if (!isCurrentLoad(sequence)) return
		workspace.value = {}
		metadataByName.value = {}
		loadError.value = reason?.message || "Unable to load the Product Release."
	} finally {
		if (isCurrentLoad(sequence)) loading.value = false
	}
}

function isCurrentLoad(sequence) {
	return !isUnmounted && sequence === loadSequence
}

function isCurrentRelease(sequence, releaseId, name) {
	return isCurrentLoad(sequence) && props.releaseId === releaseId && record.value.name === name
}

async function confirmDelete() {
	const name = record.value.name
	if (!name || !permissions.value.can_delete || deleting.value) return
	const releaseId = props.releaseId
	const sequence = loadSequence
	deleting.value = true
	deletingReleaseId = releaseId
	actionError.value = ""
	try {
		await deleteProductRelease(name)
		if (!isCurrentRelease(sequence, releaseId, name)) return
		deleteVisible.value = false
		await router.push({ name: PD_ROUTES.releases })
	} catch (reason) {
		if (isCurrentRelease(sequence, releaseId, name)) {
			actionError.value = reason?.message || "Unable to delete the Product Release."
		}
	} finally {
		if (deletingReleaseId === releaseId) deletingReleaseId = ""
		if (isCurrentRelease(sequence, releaseId, name)) deleting.value = false
	}
}

watch(() => props.releaseId, (releaseId, previousReleaseId) => load(releaseId, previousReleaseId), { immediate: true })
onBeforeUnmount(() => {
	isUnmounted = true
	++loadSequence
})
</script>

<style scoped>
.pd-release-product-link { display: inline-flex; align-items: center; min-height: var(--erp-control-height); gap: 7px; padding: 0 13px; color: var(--erp-text); border: 1px solid var(--erp-border-strong); border-radius: var(--erp-control-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); font-size: var(--erp-font-size-caption); font-weight: 680; text-decoration: none; }
.pd-release-product-link:hover { color: var(--erp-accent-hover); border-color: color-mix(in srgb, var(--erp-accent) 28%, var(--erp-border)); background: var(--erp-accent-soft); }
.pd-release-product-link:focus-visible { outline: 3px solid color-mix(in srgb, var(--erp-accent) 16%, transparent); outline-offset: 1px; }
.pd-release-front-image { display: grid; width: min(100%, 420px); gap: 10px; margin: 0; padding: var(--erp-space-3); border: 1px solid var(--erp-border); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); }
.pd-release-front-image figcaption { color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 760; }
.pd-release-front-image img { width: 100%; height: 300px; border-radius: var(--erp-control-radius); background: white; object-fit: contain; }
</style>
