<template>
	<Dialog :visible="visible" modal header="Paste lots or items" :style="{ width: '32rem', maxWidth: 'calc(100vw - 24px)' }" @update:visible="$emit('update:visible', $event)">
		<div class="paste-list">
			<label for="wip-paste-target">Paste into</label>
			<Select input-id="wip-paste-target" v-model="target" :options="targets" option-label="label" option-value="value" fluid />
			<label for="wip-paste-values">Names, one per line or separated by tabs</label>
			<Textarea id="wip-paste-values" v-model="text" rows="9" fluid autofocus />
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
import { parsePastedNames } from "./workInProgress.js"

const props = defineProps({ visible: Boolean })
const emit = defineEmits(["update:visible", "apply"])
const targets = [{ label: "Lot", value: "lot" }, { label: "Item", value: "item" }]
const target = ref("lot")
const text = ref("")
const names = computed(() => parsePastedNames(text.value))
watch(() => props.visible, (visible) => { if (visible) text.value = "" })
function apply() {
	emit("apply", { target: target.value, names: names.value })
	emit("update:visible", false)
}
</script>

<style scoped>
.paste-list { display: grid; gap: 8px; }
</style>
