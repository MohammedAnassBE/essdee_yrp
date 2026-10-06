<template>
	<aside class="document-side-panel">
		<section class="side-panel-card">
			<header>
				<span>Quick Info</span>
			</header>
			<div v-if="loading" class="side-panel-loading">
				<Skeleton v-for="index in 4" :key="index" height="2.4rem" />
			</div>
			<div v-else-if="doc" class="side-panel-rows">
				<div v-for="item in visibleItems" :key="item.fieldname" class="side-panel-row">
					<span>{{ item.label }}</span>
					<strong>{{ display(item) }}</strong>
				</div>
				<p v-if="!visibleItems.length" class="side-panel-empty">No summary fields.</p>
			</div>
		</section>

		<section v-if="doc" class="side-panel-card">
			<header>
				<span>Document</span>
			</header>
			<div class="side-panel-rows">
				<div class="side-panel-row">
					<span>ID</span>
					<strong>{{ doc.name }}</strong>
				</div>
				<div v-if="doc.owner" class="side-panel-row">
					<span>Created by</span>
					<strong>{{ doc.owner }}</strong>
				</div>
				<div v-if="doc.modified" class="side-panel-row">
					<span>Last updated</span>
					<strong>{{ doc.modified }}</strong>
				</div>
			</div>
			<Button
				v-if="showDeskButton"
				label="Open document"
				icon="pi pi-external-link"
				severity="secondary"
				outlined
				fluid
				@click="openDocument"
			/>
		</section>

		<slot :doc="doc" />
	</aside>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed } from "vue"
import { useRouter } from "vue-router"

import { webDocumentPath } from "../../router/webDocumentRoutes.js"

const props = defineProps({
	doctype: { type: String, required: true },
	doc: { type: Object, default: null },
	items: { type: Array, default: () => [] },
	loading: { type: Boolean, default: false },
	showDeskButton: { type: Boolean, default: true },
})
const router = useRouter()

const visibleItems = computed(() => props.items.filter((item) => item.fieldname))

function display(item) {
	const value = props.doc?.[item.fieldname]
	if (item.formatter) return item.formatter(value, props.doc)
	if (value === null || value === undefined || value === "") return "—"
	if (item.fieldtype === "Check") return Number(value) ? "Yes" : "No"
	return value
}

function openDocument() { router.push(webDocumentPath(props.doctype, props.doc.name).replace(/^\/web(?=\/)/, "")) }
</script>

<style scoped>
.document-side-panel {
	display: grid;
	align-content: start;
	gap: 12px;
	position: sticky;
	top: 10px;
}

.side-panel-card {
	overflow: hidden;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: 0 1px 2px rgb(24 53 39 / 4%), 0 8px 22px rgb(24 53 39 / 3%);
}

.side-panel-card > header {
	padding: 11px 14px;
	color: var(--erp-accent-hover);
	font-size: 0.76rem;
	font-weight: 800;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	background: #f8faf9;
	border-bottom: 1px solid var(--erp-border);
}

.side-panel-loading,
.side-panel-rows {
	display: grid;
	gap: 0;
	padding: 8px 15px;
}

.side-panel-loading {
	gap: 8px;
	padding-block: 15px;
}

.side-panel-row {
	display: grid;
	gap: 3px;
	padding: 9px 0;
	border-bottom: 1px solid #edf0ee;
}

.side-panel-row:last-child {
	border-bottom: 0;
}

.side-panel-row span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.side-panel-row strong {
	overflow-wrap: anywhere;
	font-size: 0.82rem;
	color: var(--erp-text);
	font-weight: 680;
	font-variant-numeric: tabular-nums;
}

.side-panel-card > :deep(.p-button) {
	margin: 0 15px 15px;
	width: calc(100% - 30px);
}

.side-panel-empty {
	margin: 8px 0;
	padding: 14px 10px;
	color: var(--erp-text-muted);
	font-size: 0.8rem;
	text-align: center;
	background: #fafcfb;
	border: 1px dashed var(--erp-border-strong);
	border-radius: var(--erp-control-radius);
}

@media (max-width: 900px) {
	.document-side-panel {
		position: static;
	}
}
</style>
