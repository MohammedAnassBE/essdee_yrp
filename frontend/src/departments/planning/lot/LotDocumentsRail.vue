<template>
	<aside class="lot-documents-rail" aria-label="Lot documents">
		<template v-if="loading">
			<section v-for="section in 4" :key="section" class="lot-documents-section">
				<div class="lot-section__body">
					<Skeleton v-for="row in 3" :key="row" height="2.4rem" />
				</div>
			</section>
		</template>
		<WorkspaceLoadError
			v-else-if="error"
			:message="error"
			:loading="loading"
			@retry="emit('retry')"
		/>
		<template v-else>
			<section v-for="section in sections" :key="section.key" class="lot-documents-section">
				<header>
					<div>
						<h2 :title="section.label">{{ section.label }}</h2>
						<span :aria-label="countLabel(section.count, section.title, section.label)">
							{{ section.count }}
						</span>
					</div>
				</header>
				<div
					v-for="row in section.visibleRows"
					:key="row.name"
					:ref="(element) => setCard(section.doctype, row.name, element)"
					role="button"
					tabindex="0"
					@keydown.enter.self.prevent="open(section.doctype, row.name)"
					@keydown.space.self.prevent="open(section.doctype, row.name)"
					class="lot-documents-card"
					aria-haspopup="dialog"
					@click="open(section.doctype, row.name)"
				>
					<div class="lot-documents-card__top">
						<strong>{{ row.name }}</strong>
						<DocumentStatusBadge :docstatus="row.docstatus" :label="row.status" />
					</div>
					<span class="lot-documents-card__context">
						<LotDocumentContext :doctype="section.doctype" :row="row" />
					</span>
					<div class="lot-documents-card__meta">
						<span>
							<i class="pi pi-calendar" />
							{{ formatDisplayDate(row[section.dateField]) }}
						</span>
						<span>
							<i class="pi pi-box" />
							{{ lotDocumentQuantityLine(section.doctype, row) }}
						</span>
					</div>
					<i class="pi pi-chevron-right lot-documents-card__chevron" />
				</div>
				<div v-if="!section.rows.length" class="lot-documents-empty">
					<i class="pi pi-inbox" />
					<span>No {{ section.label }}</span>
				</div>
				<Button
					v-if="section.hasMore"
					class="lot-documents-toggle"
					severity="secondary"
					text
					:icon="expanded[section.key] ? 'pi pi-chevron-up' : 'pi pi-chevron-down'"
					:label="
						expanded[section.key] ? 'Show fewer' : `Show all ${section.rows.length}`
					"
					:aria-expanded="Boolean(expanded[section.key])"
					@click="expanded[section.key] = !expanded[section.key]"
				/>
				<div v-if="section.count > section.rows.length" class="lot-documents-limit">
					Showing {{ section.rows.length }} of {{ section.count }}
				</div>
			</section>
		</template>
	</aside>
</template>

<script setup>
import Button from "primevue/button"
import LotDocumentContext from "../../purchase/lot/LotDocumentContext.vue"
import Skeleton from "primevue/skeleton"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import {
	countLabel,
	lotDocumentQuantityLine,
	lotDocumentSections,
} from "./lotViews.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"

const props = defineProps({
	documents: { type: Object, default: () => ({}) },
	loading: Boolean,
	error: { type: String, default: "" },
})
const emit = defineEmits(["open", "retry"])
const expanded = ref({})
const previewLimit = ref(5)
const cards = new Map()
let origin = ""
const sections = computed(() =>
	lotDocumentSections(props.documents, expanded.value, previewLimit.value),
)
const mediaQuery = window.matchMedia("(max-width: 620px)")
function updatePreview() {
	previewLimit.value = mediaQuery.matches ? 3 : 5
}
function setCard(doctype, name, element) {
	const key = `${doctype}:${name}`
	if (element) cards.set(key, element)
	else cards.delete(key)
}
function open(doctype, name) {
	origin = `${doctype}:${name}`
	emit("open", { doctype, name })
}
function restoreFocus() {
	nextTick(() => cards.get(origin)?.focus())
}
watch(
	() => props.documents,
	() => {
		expanded.value = {}
	},
)
onMounted(() => {
	updatePreview()
	mediaQuery.addEventListener("change", updatePreview)
})
onBeforeUnmount(() => mediaQuery.removeEventListener("change", updatePreview))
defineExpose({ restoreFocus })
</script>
