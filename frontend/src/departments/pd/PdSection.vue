<template>
	<DepartmentPage
		:title="sectionTitle"
		back-to="/pd"
		back-label="PD"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="pd-section erp-workspace" :aria-label="sectionTitle">
			<div v-if="loading" class="pd-section__loading">
				<Skeleton height="76px" />
				<Skeleton height="420px" />
			</div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<Message v-else-if="!capability?.can_read" severity="warn" :closable="false">
				You do not have permission to view {{ sectionTitle }}.
			</Message>
			<Products v-else-if="section === 'products'" :capability="capability" />
			<ProductReleases v-else-if="section === 'product_releases'" :capability="capability" />
			<LotwiseItemProfits v-else :capability="capability" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, ref } from "vue"

import { getPdCapabilities } from "../../api/pd.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import LotwiseItemProfits from "./LotwiseItemProfits.vue"
import ProductReleases from "./ProductReleases.vue"
import Products from "./Products.vue"

const props = defineProps({
	section: { type: String, required: true },
})

const sectionTitles = {
	products: "Products",
	product_releases: "Product Releases",
	lotwise_item_profits: "Lotwise Item Profit",
}
const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const sectionTitle = computed(() => sectionTitles[props.section] || "PD")
const capability = computed(() => sections.value[props.section] || null)

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getPdCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || `Unable to load ${sectionTitle.value}.`
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.pd-section {
	width: 100%;
	max-width: 1800px;
	min-width: 0;
	margin: 0 auto;
	padding: 2px 0 var(--erp-space-5);
}

.pd-section__loading { display: grid; gap: var(--erp-space-3); padding-top: 2px; }
.pd-section__loading :deep(.p-skeleton) { border-radius: var(--erp-panel-radius); }
</style>
