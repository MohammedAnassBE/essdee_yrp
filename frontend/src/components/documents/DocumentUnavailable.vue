<template>
	<DepartmentPage title="Page unavailable" :back-to="getHomePath()" :back-label="lockedDepartment?.label || 'Workspaces'" :show-title="false" flat full-width>
		<section class="document-unavailable erp-card" role="status">
			<span class="document-unavailable__mark"><i class="pi pi-file-excel" /></span>
			<div>
				<small>WEB PAGE NOT AVAILABLE</small>
				<h1>{{ doctype || "Document" }}</h1>
				<strong v-if="name">{{ name }}</strong>
				<p>This document does not have a page in the web workspace yet. You have not been redirected to Desk.</p>
			</div>
			<Button label="Go Back" icon="pi pi-arrow-left" severity="secondary" outlined @click="goBack" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../DepartmentPage.vue"
import { getHomePath, lockedDepartment } from "../../router/departmentLock.js"

const route = useRoute()
const router = useRouter()
const doctype = computed(() => String(route.query.doctype || ""))
const name = computed(() => String(route.query.name || ""))

function goBack() {
	if (window.history.length > 1) router.back()
	else router.push(getHomePath())
}
</script>

<style scoped>
.document-unavailable { display: flex; width: min(720px, 100%); min-height: 260px; align-items: center; gap: var(--erp-space-4); margin: 6vh auto 0; padding: clamp(24px, 5vw, 44px); background: var(--erp-surface); border: 1px solid var(--erp-border); box-shadow: var(--erp-shadow-md); }
.document-unavailable__mark { display: grid; width: 58px; height: 58px; flex: 0 0 auto; place-items: center; color: var(--erp-accent); background: var(--erp-accent-soft); border: 1px solid color-mix(in srgb, var(--erp-accent) 18%, white); border-radius: var(--erp-panel-radius); }
.document-unavailable__mark i { font-size: 24px; }
.document-unavailable > div { display: grid; min-width: 0; flex: 1; gap: 6px; }
.document-unavailable small { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .07em; }
.document-unavailable h1 { margin: 0; color: var(--erp-text); font-size: clamp(24px, 4vw, 34px); letter-spacing: -.035em; }
.document-unavailable strong { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.document-unavailable p { max-width: 52ch; margin: 8px 0 0; color: var(--erp-text-muted); line-height: 1.55; }
@media (max-width: 620px) { .document-unavailable { align-items: flex-start; flex-direction: column; margin-top: var(--erp-space-3); } }
</style>
