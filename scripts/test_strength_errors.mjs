import assert from "node:assert/strict"

import { extractServerMessage } from "../frontend/src/api/errorMessages.js"
import { getAttendanceStrength } from "../frontend/src/api/sewing.js"
import { Vue, findNodes, loadComponent, mountComponent } from "./helpers/vue_renderer.mjs"

const { h, nextTick } = Vue
const message = "HR API secret is not configured in SD YRP MRP Settings"
const payload = {
	_server_messages: JSON.stringify([JSON.stringify({ message, title: "HR configuration required" })]),
	exception: `frappe.exceptions.ValidationError: ${message}`,
}
globalThis.window = {}
globalThis.fetch = async () => ({ status: 417, ok: false, json: async () => payload })
await assert.rejects(getAttendanceStrength("2026-10-08", "08:00:00", "17:00:00"), { message })

const field = {
	props: ["modelValue", "label"], emits: ["update:modelValue"],
	setup(props, { emit }) {
		return () => h("input", { label: props.label, onInput: value => emit("update:modelValue", value) })
	},
}
const page = loadComponent("frontend/src/components/reports/AttendanceStrengthReport.vue", {
	"primevue/button": {},
	"../../api/sewing.js": { getAttendanceStrength },
	"../common/DateField.vue": field, "../common/TimeField.vue": field,
	"../documents/DocumentErrorDialog.vue": (_, { attrs }) => h("error", attrs),
	"./ReportShell.vue": (_, { attrs, slots }) => h("report", { onGenerate: attrs.onGenerate }, slots.filters()),
	"./reportUtils.js": { todayIso: () => "2026-10-08", stockCellValue: value => value },
})
const root = mountComponent(page, {})
for (const [label, time] of [["From Time", "08:00:00"], ["To Time", "17:00:00"]]) {
	findNodes(root, node => node.type === "input" && node.props.label === label)[0].props.onInput(time)
}
await nextTick()
await findNodes(root, node => node.type === "report")[0].props.onGenerate()
await nextTick()
assert.equal(findNodes(root, node => node.type === "error")[0].props.message, message)

// Desk gets the same 417 payload, sometimes wrapped in an XHR response.
const controls = new Map()
let errorPayload = payload
globalThis.$ = value => value
globalThis.frappe = {
	datetime: { now_date: () => "2026-10-08" },
	call: options => options.error(errorPayload),
	ui: { form: { make_control({ df }) {
		const control = {
			value: "", get_value() { return this.value },
			set_value(value) { this.value = value; df.change() },
		}
		controls.set(df.fieldname, control)
		return control
	} } },
}
const desk = loadComponent("essdee_yrp/public/js/SewingPlan/components/StrengthReportTab.vue", {
	xlsx: {},
	"../../../../../frontend/src/api/errorMessages.js": { extractServerMessage },
})
const deskRoot = mountComponent(desk, {})
controls.get("strength_report_from_time").set_value("08:00:00")
controls.get("strength_report_to_time").set_value("17:00:00")
await nextTick()
for (const response of [payload, { responseJSON: payload }]) {
	errorPayload = response
	findNodes(deskRoot, node => node.type === "button" && node.props.onClick)[0].props.onClick()
	await nextTick()
	assert.ok(findNodes(deskRoot, node => node.type === "p" && node.text === message).length)
}

console.log("Attendance API, /web and Desk show the exact HR configuration message")
