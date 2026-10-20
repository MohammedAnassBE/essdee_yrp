import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { computed, ref } from "vue"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
function declaration(source, name) {
	const start = source.search(new RegExp(`^(?:async )?function ${name}\\(`, "m"))
	assert.ok(start >= 0, name)
	const rest = source.slice(start)
	const line = rest.split("\n")[0]
	return line.endsWith("}") ? line : rest.slice(0, rest.indexOf("\n}") + 2)
}
function workspace(path, isWorkOrder) {
	const source = read(path), calls = []
	const script = source.split("<script setup>")[1].split("</script>")[0]
	const declarations = script.split("\n").filter(line => /^const lifecycleConfirm(Title|Label|Message) =/.test(line)).join("\n")
	const functions = ["runWorkspaceAction", "requestLifecycleAction", "confirmLifecycleAction"].map(name => declaration(script, name)).join("\n")
	const api = new Function("computed", "ref", "calls", `
		const workspace = ref({ record: { name: "WO-1" } }), currentName = ref("DC-1")
		const pendingLifecycleCommand = ref(""), lifecycleConfirmVisible = ref(false)
		const runLifecycleAction = async command => calls.push(command)
		const runCommand = async command => calls.push(command)
		const save = async submit => calls.push({ submit })
		const editWorkOrder = () => {}, openAction = () => {}
		${declarations}\n${functions}
		return { runWorkspaceAction, confirmLifecycleAction, lifecycleConfirmVisible, lifecycleConfirmTitle, lifecycleConfirmLabel, lifecycleConfirmMessage, requestLifecycleAction }
	`)(computed, ref, calls)
	if (isWorkOrder) {
		const submitAction = source.split("\n").find(line => line.includes('add("submit",'))
		new Function("add", "requestLifecycleAction", submitAction)((_key, _label, _icon, command) => command(), api.requestLifecycleAction)
		assert.equal(api.lifecycleConfirmVisible.value, true)
		assert.deepEqual(calls, [])
		api.lifecycleConfirmVisible.value = false
	}
	return { ...api, calls }
}

for (const [label, path, isWorkOrder, name, cancelMessage] of [
	["Work Order", "departments/FabricWorkOrder.vue", true, "WO-1", "Cancel WO-1? This keeps the document for audit but stops further processing."],
	["Delivery Challan", "departments/fabric-store/DeliveryChallanWorkspace.vue", false, "DC-1", "Cancel DC-1? This keeps the document for audit and reverses its submitted effect."],
]) {
	test(`${label} Submit waits for lifecycle confirmation; Cancel and Amend keep their wording`, async () => {
		const state = workspace(path, isWorkOrder)
		await state.runWorkspaceAction("submit")
		assert.equal(state.lifecycleConfirmVisible.value, true)
		assert.equal(state.lifecycleConfirmTitle.value, `Submit ${label}?`)
		assert.equal(state.lifecycleConfirmMessage.value, `Permanently submit ${name}?`)
		assert.equal(state.lifecycleConfirmLabel.value, "Submit")
		assert.deepEqual(state.calls, [])
		state.lifecycleConfirmVisible.value = false
		assert.deepEqual(state.calls, [])
		await state.runWorkspaceAction("submit")
		await state.confirmLifecycleAction()
		assert.deepEqual(state.calls, [isWorkOrder ? "submit" : { submit: true }])
		assert.equal(state.lifecycleConfirmVisible.value, false)
		await state.confirmLifecycleAction()
		assert.equal(state.calls.length, 1)
		await state.runWorkspaceAction("cancel")
		assert.equal(state.lifecycleConfirmTitle.value, `Cancel ${label}?`)
		assert.equal(state.lifecycleConfirmLabel.value, `Cancel ${label}`)
		assert.equal(state.lifecycleConfirmMessage.value, cancelMessage)
		await state.runWorkspaceAction("amend")
		assert.equal(state.lifecycleConfirmTitle.value, `Amend ${label}?`)
		assert.equal(state.lifecycleConfirmMessage.value, `Create a new draft amendment from ${name}?`)
		assert.equal(state.lifecycleConfirmLabel.value, "Create Amendment")
	})
}

test("CPM transaction Submit confirms identity and only submits on accept", async () => {
	const source = read("departments/cutting/CpmTransactionDialog.vue").split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
	const confirmations = [], calls = []
	const state = new Function("ref", "watch", "defineProps", "defineEmits", "useActionConfirmation", "changeLinkedTransactionStatus", `${source}\nreturn { record, changeStatus }`)(
		ref, () => {}, () => ({ cuttingPlan: "CP-1" }), () => () => {}, () => options => confirmations.push(options),
		async (...args) => { calls.push(args); return { doctype: "YRP Stock Entry", name: "STE-1" } },
	)
	state.record.value = { doctype: "YRP Stock Entry", name: "STE-1" }
	await state.changeStatus("submit")
	assert.equal(confirmations[0].header, "Submit YRP Stock Entry?")
	assert.equal(confirmations[0].message, "Permanently submit YRP Stock Entry STE-1?")
	assert.equal(confirmations[0].acceptLabel, "Submit")
	assert.equal(confirmations[0].acceptIcon, "pi pi-check")
	assert.deepEqual(calls, [])
	await confirmations[0].accept()
	assert.deepEqual(calls, [["CP-1", "YRP Stock Entry", "STE-1", "submit"]])
	await state.changeStatus("cancel")
	assert.equal(confirmations[1].acceptLabel, "Cancel Document")
	assert.equal(calls.length, 1)
})
