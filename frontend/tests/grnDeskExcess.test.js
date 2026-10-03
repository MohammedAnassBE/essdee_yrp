import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { fileURLToPath } from "node:url"

const scriptPath = fileURLToPath(
	new URL("../../essdee_yrp/public/js/goods_received_note.js", import.meta.url),
)
const source = fs.readFileSync(scriptPath, "utf8")

function loadDeskScript(actualDiaContext) {
	const essdee_yrp = {}
	const frappe = {
		ui: { form: { on() {} } },
		call({ callback }) {
			callback({ message: actualDiaContext })
		},
	}
	vm.runInNewContext(source, {
		frappe,
		essdee_yrp,
		__: (value) => value,
		flt: (value) => Number(value || 0),
		format_number: String,
		setTimeout: (callback) => callback(),
		console,
	})
	return essdee_yrp
}

test("standard Desk Work Order GRN enables excess entry without Actual Dia support", () => {
	const essdee_yrp = loadDeskScript({ enabled: false, dia_options: [] })
	let mounted = false
	essdee_yrp.mount_physical_grn_editor = () => { mounted = true }
	const frm = {
		doc: {
			against: "Work Order",
			against_id: "WO-DYE-1",
			docstatus: 0,
			is_return: 0,
			is_rework: 0,
			additional_grn: 0,
			includes_packing: 0,
		},
	}

	essdee_yrp.configure_actual_dia_button(frm)

	assert.equal(mounted, true)
})
