const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const scriptPath = path.join(__dirname, "ipd_attributes.js");

function loadHelpers(attributes) {
	const messages = [];
	const context = {
		__: (text, args = []) => text.replace(/\{(\d+)\}/g, (_match, index) => args[index]),
		essdee_yrp: {},
		frappe: {
			boot: { essdee_yrp_ipd_attributes: attributes },
			provide() {},
			throw(message) {
				messages.push(message);
				throw new Error(message);
			},
		},
	};
	vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });
	return { helpers: context.essdee_yrp, messages };
}

{
	const { helpers } = loadHelpers({ colour: "Shade", dia: "Width" });
	assert.equal(helpers.get_colour_attribute(), "Shade");
	assert.equal(helpers.get_dia_attribute(), "Width");
}

{
	const { helpers, messages } = loadHelpers({ colour: "Shade", dia: null });
	assert.throws(() => helpers.get_dia_attribute());
	assert.deepEqual(messages, ["Set Default Dia Attribute in SD YRP IPD Settings"]);
}

console.log("IPD attribute helper tests passed");
