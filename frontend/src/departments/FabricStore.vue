<template>
	<DepartmentPage :title="storeName" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			:title="storeName"
			:items="visibleWorkspaces"
			:loading="loading"
			:empty-text="`No permitted ${storeName} workspaces`"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getCutPanelStoreCapabilities } from "../api/cutPanelStore.js"
import { getFabricStoreCapabilities } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { storeWorkspaces } from "./fabric-store/storeWorkspaces.js"

const props = defineProps({
	storeName: { type: String, default: "Fabric Store" },
	basePath: { type: String, default: "/fabric-store" },
	workspaceKeys: {
		type: Array,
		default: () => ["work_orders", "purchase_orders", "stock_transfers", "reports"],
	},
	reportKeys: { type: Array, default: () => ["stock_balance"] },
	extraWorkspaces: { type: Array, default: () => [] },
	extraCapabilitiesLoader: { type: Function, default: null },
})
const loading = ref(true)
const error = ref("")
const sections = ref({})
const workspaces = computed(() => [...props.extraWorkspaces, ...storeWorkspaces(props.basePath, props.reportKeys)])
const visibleWorkspaceKeys = computed(() => new Set([
	...props.extraWorkspaces.map((workspace) => workspace.key),
	...props.workspaceKeys,
]))
const visibleWorkspaces = computed(() => workspaces.value.filter((workspace) => (
	visibleWorkspaceKeys.value.has(workspace.key)
		&& sections.value[workspace.key]
		&& (workspace.key !== "reports" || props.reportKeys.some((key) => sections.value.reports?.reports?.[key]?.can_read))
)))

async function load() {
	loading.value = true
	error.value = ""
	try {
		const includesBoxStickers = props.workspaceKeys.includes("box_stickers")
		const [payload, cutPanelPayload, extraPayload] = await Promise.all([
			getFabricStoreCapabilities(),
			includesBoxStickers ? getCutPanelStoreCapabilities() : null,
			props.extraCapabilitiesLoader ? props.extraCapabilitiesLoader() : null,
		])
		sections.value = { ...payload?.sections, ...extraPayload?.sections }
		if (cutPanelPayload?.sections?.box_stickers) sections.value.box_stickers = cutPanelPayload.sections.box_stickers
	} catch (reason) {
		error.value = reason?.message || `Unable to load the ${props.storeName} workspace.`
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
