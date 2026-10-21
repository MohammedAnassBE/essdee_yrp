<template>
	<DepartmentPage :title="isPermissionDenied ? 'No permission' : isLayoutUnavailable ? 'Not in your layout' : 'Page unavailable'" :back-to="getHomePath()" :back-label="lockedDepartment?.label || 'Workspaces'" :show-title="false" flat full-width>
		<section class="document-unavailable erp-card" role="status">
			<span class="document-unavailable__mark"><i :class="isLayoutUnavailable || isPermissionDenied ? 'pi pi-lock' : 'pi pi-file-excel'" /></span>
			<div>
				<template v-if="isPermissionDenied">
					<small>NO PERMISSION</small>
					<h1>You don't have permission to view {{ doctype }}</h1>
					<strong v-if="from">{{ from }}</strong>
					<p>Ask an administrator for read access to {{ doctype }} if you need this list.</p>
				</template>
				<template v-else-if="isLayoutUnavailable">
					<small>NOT IN YOUR LAYOUT</small>
					<h1>{{ pageLabel }}</h1>
					<strong v-if="from">{{ from }}</strong>
					<p>This page is not part of your {{ lockedDepartment?.label }} layout, so it was not opened. Ask an administrator to change your YRP UI Layout if you need it.</p>
				</template>
				<template v-else>
					<small>WEB PAGE NOT AVAILABLE</small>
					<h1>{{ doctype || "Document" }}</h1>
					<strong v-if="name">{{ name }}</strong>
					<p>This document does not have a page in the web workspace yet. You have not been redirected to Desk.</p>
				</template>
			</div>
			<Button v-if="isLayoutUnavailable" :label="`Go to ${lockedDepartment?.label}`" icon="pi pi-arrow-left" severity="secondary" outlined @click="router.replace(getHomePath())" />
			<Button v-else label="Go Back" icon="pi pi-arrow-left" severity="secondary" outlined @click="goBack" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../DepartmentPage.vue"
import { departments } from "../../departments/registry.js"
import { getHomePath, lockedDepartment } from "../../router/departmentLock.js"

const route = useRoute()
const router = useRouter()
const doctype = computed(() => String(route.query.doctype || ""))
const name = computed(() => String(route.query.name || ""))
const isLayoutUnavailable = computed(() => Boolean(route.meta.layoutUnavailable))
const isPermissionDenied = computed(() => Boolean(route.meta.permissionDenied))
const from = computed(() => String(route.query.from || ""))
const pageLabel = computed(() => departments.find((item) => `${from.value.toLowerCase().split(/[?#]/)[0]}/`.startsWith(`${item.path}/`))?.label || "Page")

function goBack() {
	if (window.history.length > 1) router.back()
	else router.push(getHomePath())
}
</script>

<style scoped>
.document-unavailable { display: flex; width: min(720px, 100%); min-height: 260px; align-items: center; gap: var(--erp-space-4); margin: 6vh auto 0; padding: clamp(24px, 5vw, 44px); background: var(--erp-surface); border: 1px solid var(--erp-border); box-shadow: var(--erp-shadow-md); }
.document-unavailable__mark { display: grid; width: 58px; height: 58px; flex: 0 0 auto; place-items: center; color: var(--erp-accent); background: var(--erp-accent-soft); border: 1px solid color-mix(in srgb, var(--erp-accent) 18%, var(--erp-surface)); border-radius: var(--erp-panel-radius); }
.document-unavailable__mark i { font-size: 24px; }
.document-unavailable > div { display: grid; min-width: 0; flex: 1; gap: 6px; }
.document-unavailable small { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .07em; }
.document-unavailable h1 { margin: 0; color: var(--erp-text); font-size: clamp(24px, 4vw, 34px); letter-spacing: -.035em; }
.document-unavailable strong { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.document-unavailable p { max-width: 52ch; margin: 8px 0 0; color: var(--erp-text-muted); line-height: 1.55; }
@media (max-width: 620px) { .document-unavailable { align-items: flex-start; flex-direction: column; margin-top: var(--erp-space-3); } }
</style>
