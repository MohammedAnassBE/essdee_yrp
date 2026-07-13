<!--
  Generic workflow-action buttons for workflow-managed DocTypes (anything
  flagged `isWorkflow` via the WORKFLOW map in config/doctypes.js — the map
  is currently empty, so this component stays dormant until a workflow
  DocType enters the /web registry).

  Renders EXACTLY the transitions the server returns for the current user +
  workflow_state via frappe.model.workflow.get_transitions, and applies the
  chosen one via apply_workflow. The server is authoritative for role-gating —
  a button exists only if get_transitions returned that transition, so no
  client-side role logic is needed.

  Reject-type actions (Reject / Cancel / Reverse) open a required-reason dialog;
  the reason is recorded as a timeline comment on the document. All other
  actions go through a confirm dialog naming the action + resulting state.

  Mounted INLINE in the DocDetail header (view mode) for workflow doctypes,
  in place of the plain docstatus Submit/Cancel (which Frappe rejects for
  workflow docs anyway).

  Usage:
    <WorkflowActions :doc="doc" :doctype="doctype" @changed="reloadView" />
-->
<template>
	<span v-if="transitions.length" class="wf-actions">
		<Button
			v-for="t in transitions"
			:key="t.action"
			:label="t.action"
			:icon="iconFor(t.action)"
			size="small"
			:severity="isNegative(t.action) ? 'danger' : undefined"
			:outlined="isNegative(t.action)"
			:loading="acting === t.action"
			:disabled="acting !== null"
			@click="onAction(t)"
		/>

		<!-- Reject-style action: required reason, recorded as a comment -->
		<Dialog
			v-model:visible="rejectOpen"
			modal
			:header="`${pendingAction || 'Reject'} ${doctype}`"
			:style="{ width: '460px' }"
		>
			<p class="reject-help">
				A reason is required. It is recorded as a comment on
				<b class="esd-mono">{{ doc?.name }}</b>.
			</p>
			<Textarea
				v-model="rejectReason"
				rows="4"
				autoResize
				class="reject-input"
				placeholder="e.g. Rate doesn't match the approved quotation — revise and resubmit."
			/>
			<small v-if="rejectError" class="reject-error">{{ rejectError }}</small>
			<template #footer>
				<Button label="Cancel" text severity="secondary" :disabled="acting === pendingAction" @click="rejectOpen = false" />
				<Button
					:label="pendingAction || 'Reject'"
					icon="pi pi-times"
					severity="danger"
					:loading="acting === pendingAction"
					@click="doReject"
				/>
			</template>
		</Dialog>
	</span>
</template>

<script setup>
import { ref, watch } from "vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Textarea from "primevue/textarea"
import { getWorkflowTransitions, applyWorkflowAction, addComment } from "@/api/client"
import { useAppConfirm } from "@/composables/useConfirm"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	doc: { type: Object, required: true },
	doctype: { type: String, required: true },
})

const emit = defineEmits(["changed"])

const confirm = useAppConfirm()
const toast = useAppToast()

const transitions = ref([])
const acting = ref(null) // the action string currently running, or null
const rejectOpen = ref(false)
const rejectReason = ref("")
const rejectError = ref("")
const pendingAction = ref("") // the reject-style action awaiting a reason

// Reject-style actions get the reason dialog + danger styling.
function isNegative(action) {
	return /reject|cancel|reverse|decline/i.test(action || "")
}

function iconFor(action) {
	if (isNegative(action)) return "pi pi-times"
	if (/approve/i.test(action)) return "pi pi-check"
	if (/submit/i.test(action)) return "pi pi-arrow-right"
	return "pi pi-angle-right"
}

async function loadTransitions() {
	if (!props.doc?.name) {
		transitions.value = []
		return
	}
	try {
		transitions.value = await getWorkflowTransitions(props.doc)
	} catch (_) {
		// Non-workflow doc, or no permission — render nothing.
		transitions.value = []
	}
}

// Reload whenever the doc identity or its workflow_state changes (e.g. after the
// parent reloads the doc following an action).
watch(
	() => [props.doc?.name, props.doc?.workflow_state],
	loadTransitions,
	{ immediate: true },
)

async function applyAction(action, { emitChanged = true } = {}) {
	acting.value = action
	try {
		await applyWorkflowAction(props.doc, action)
		toast.success(action, `${props.doc.name} → ${nextStateFor(action)}`)
		await loadTransitions()
		if (emitChanged) emit("changed")
		return true
	} catch (e) {
		toast.error(`${action} failed`, e.message)
		return false
	} finally {
		acting.value = null
	}
}

function nextStateFor(action) {
	const t = transitions.value.find((x) => x.action === action)
	return t?.next_state || ""
}

function onAction(t) {
	if (isNegative(t.action)) {
		pendingAction.value = t.action
		rejectReason.value = ""
		rejectError.value = ""
		rejectOpen.value = true
		return
	}
	confirm.require({
		header: `${t.action} ${props.doctype}`,
		message: `${t.action} ${props.doc.name}? This moves it to “${t.next_state}”.`,
		acceptLabel: t.action,
		acceptClass: "p-button-primary",
		accept: () => applyAction(t.action),
	})
}

async function doReject() {
	const reason = rejectReason.value.trim()
	if (!reason) {
		rejectError.value = "A reason is required."
		return
	}
	const action = pendingAction.value
	// Suppress applyAction's own "changed" emit so the parent reloads exactly ONCE —
	// after the comment is recorded — instead of twice (transition, then comment).
	const ok = await applyAction(action, { emitChanged: false })
	if (!ok) return
	rejectOpen.value = false
	// Record the reason on the timeline (best-effort — the transition already applied).
	try {
		await addComment(props.doctype, props.doc.name, `${action}: ${reason}`)
	} catch (_) {
		toast.warn("Reason not saved", "The action applied, but the comment could not be recorded.")
	} finally {
		emit("changed") // single parent reload — reflects the transition (+ comment if saved)
	}
}

defineExpose({ reload: loadTransitions })
</script>

<style scoped>
.wf-actions {
	display: inline-flex;
	gap: 8px;
	align-items: center;
}
.reject-help {
	margin: 0 0 10px;
	font-size: 12.5px;
	color: var(--esd-muted);
}
.reject-input {
	width: 100%;
}
.reject-error {
	display: block;
	margin-top: 6px;
	color: var(--esd-danger);
	font-size: 12px;
}
</style>
