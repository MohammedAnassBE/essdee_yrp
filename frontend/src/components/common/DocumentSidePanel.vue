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
				label="Open in Desk"
				icon="pi pi-external-link"
				severity="secondary"
				outlined
				fluid
				@click="openInDesk"
			/>
		</section>

		<slot :doc="doc" />
	</aside>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed } from "vue"

const props = defineProps({
	doctype: { type: String, required: true },
	doc: { type: Object, default: null },
	items: { type: Array, default: () => [] },
	loading: { type: Boolean, default: false },
	showDeskButton: { type: Boolean, default: true },
})

const visibleItems = computed(() => props.items.filter((item) => item.fieldname))

function display(item) {
	const value = props.doc?.[item.fieldname]
	if (item.formatter) return item.formatter(value, props.doc)
	if (value === null || value === undefined || value === "") return "—"
	if (item.fieldtype === "Check") return Number(value) ? "Yes" : "No"
	return value
}

function openInDesk() {
	const slug = props.doctype.toLowerCase().replaceAll(" ", "-")
	window.open(`/app/${encodeURIComponent(slug)}/${encodeURIComponent(props.doc.name)}`, "_blank", "noopener")
}
</script>

<style scoped>
.document-side-panel {
	display: grid;
	align-content: start;
	gap: 14px;
	position: sticky;
	top: 10px;
}

.side-panel-card {
	overflow: hidden;
	background: #fff;
	border: 1px solid #e1e7e3;
	border-radius: 14px;
	box-shadow: 0 8px 24px rgb(24 53 39 / 5%);
}

.side-panel-card > header {
	padding: 13px 15px;
	color: #2f684b;
	font-size: 0.76rem;
	font-weight: 800;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	background: #f2f8f4;
	border-bottom: 1px solid #e1e7e3;
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
	padding: 10px 0;
	border-bottom: 1px solid #edf0ee;
}

.side-panel-row:last-child {
	border-bottom: 0;
}

.side-panel-row span {
	color: #77827c;
	font-size: 0.7rem;
}

.side-panel-row strong {
	overflow-wrap: anywhere;
	font-size: 0.82rem;
	font-weight: 650;
}

.side-panel-card > :deep(.p-button) {
	margin: 0 15px 15px;
	width: calc(100% - 30px);
}

.side-panel-empty {
	margin: 10px 0;
	color: #77827c;
	font-size: 0.8rem;
}

@media (max-width: 900px) {
	.document-side-panel {
		position: static;
	}
}
</style>
