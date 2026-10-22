<template>
	<Dialog :visible="visible" modal header="Paste lots or items" :style="{ width: '32rem', maxWidth: 'calc(100vw - 24px)' }" @update:visible="$emit('update:visible', $event)">
		<div class="paste-list">
			<label for="paste-list-target">Paste into</label>
			<Select input-id="paste-list-target" v-model="target" :options="targets" option-label="label" option-value="value" fluid />
			<label for="paste-list-format">Format</label>
			<Select input-id="paste-list-format" v-model="format" :options="PASTE_FORMATS" option-label="label" option-value="value" fluid />
			<label for="paste-list-values">Values</label>
			<Textarea id="paste-list-values" v-model="text" rows="9" fluid autofocus />
			<small>{{ names.length }} unique names</small>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" outlined @click="$emit('update:visible', false)" />
			<Button label="Add names" :disabled="!names.length" @click="apply" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import { computed, ref, watch } from "vue"
import { PASTE_FORMATS, parsePastedNames } from "./pasteValues.js"

const props = defineProps({ visible: Boolean })
const emit = defineEmits(["update:visible", "apply"])
const targets = [{ label: "Lot", value: "lot" }, { label: "Item", value: "item" }]
const target = ref("lot")
const format = ref("list")
const text = ref("")
const names = computed(() => parsePastedNames(text.value, format.value))
watch(() => props.visible, (visible) => { if (visible) text.value = "" })
function apply() {
	emit("apply", { target: target.value, names: names.value })
	emit("update:visible", false)
}
</script>

<style scoped>
.paste-list { display: grid; gap: 8px; }
</style>
