<template>
	<div class="finishing-stack">
		<p v-if="status !== 'OCR Completed'" class="finishing-empty">P &amp; L uploads are available only when FP Status is <strong>OCR Completed</strong>. Current status: <strong>{{ status || "Planned" }}</strong>.</p>
		<template v-else>
			<div class="profit-loss__toolbar">
				<h3 class="finishing-section__title">P &amp; L Documents</h3>
				<Button v-if="canManage" label="Upload File" icon="pi pi-upload" size="small" :disabled="busy" @click="dialogOpen = true" />
			</div>
			<p v-if="!documents.length" class="finishing-empty">No P&amp;L documents uploaded yet.</p>
			<ol v-else class="profit-loss__list">
				<li v-for="document in documents" :key="document.name" class="profit-loss__item">
					<div class="profit-loss__body">
						<a :href="document.file" target="_blank" rel="noopener">{{ fileName(document.file) }}</a>
						<small>{{ document.modified }} · {{ document.owner }}</small>
						<p v-if="document.comments">{{ document.comments }}</p>
					</div>
					<Button v-if="canManage" icon="pi pi-trash" severity="danger" text size="small" :aria-label="`Delete ${fileName(document.file)}`" :disabled="busy" @click="emit('delete', document)" />
				</li>
			</ol>
		</template>

		<Dialog v-model:visible="dialogOpen" modal header="Upload P & L Document" class="erp-dialog--sm">
			<form class="profit-loss__form" @submit.prevent="submit">
				<label class="common-field"><span>File</span><input type="file" required :disabled="busy" @change="file = $event.target.files?.[0] || null" /></label>
				<label class="common-field"><span>Comments</span><Textarea v-model="comments" rows="3" auto-resize :disabled="busy" /></label>
			</form>
			<template #footer>
				<Button label="Close" severity="secondary" text :disabled="busy" @click="dialogOpen = false" />
				<Button label="Save" icon="pi pi-check" :loading="busy" :disabled="!file" @click="submit" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Textarea from "primevue/textarea"
import { ref, watch } from "vue"

const props = defineProps({
	documents: { type: Array, default: () => [] },
	status: { type: String, default: "" },
	canManage: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["upload", "delete"])
const dialogOpen = ref(false)
const file = ref(null)
const comments = ref("")

function fileName(url) {
	return String(url || "").split("/").pop()
}

function submit() {
	if (!file.value || props.busy) return
	emit("upload", { file: file.value, comments: comments.value })
}

watch(() => props.documents, () => {
	dialogOpen.value = false
	file.value = null
	comments.value = ""
})
</script>

<style scoped>
.profit-loss__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.profit-loss__list { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.profit-loss__item { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.profit-loss__body { display: grid; gap: 2px; min-width: 0; }
.profit-loss__body a { overflow: hidden; color: var(--erp-accent-dark); font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.profit-loss__body small, .profit-loss__body p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.profit-loss__form { display: grid; gap: 12px; }
</style>
