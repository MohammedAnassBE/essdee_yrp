import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'

const planningPage = new URL('../frontend/src/departments/planning/lot/LotPage.vue', import.meta.url)
const source = readFileSync(planningPage, 'utf8')
const sharedPath = source.match(/import LotFabricTab from "([^"]+)"/)?.[1]
assert.equal(sharedPath, '../../purchase/lot/LotFabricTab.vue')
assert.equal(existsSync(new URL('./LotFabricTab.vue', planningPage)), false, 'remove the duplicate Planning component')

const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
for (const file of [planningPage, new URL(sharedPath, planningPage)]) {
	const filename = file.pathname
	const parsed = parse(readFileSync(file, 'utf8'), { filename })
	assert.deepEqual(parsed.errors, [], filename)
	const script = compileScript(parsed.descriptor, { id: filename })
	const template = compileTemplate({
		source: parsed.descriptor.template.content,
		filename,
		id: filename,
		compilerOptions: { bindingMetadata: script.bindings },
	})
	assert.deepEqual(template.errors, [], filename)
}
console.log('Planning Lot shared fabric view and Vue compilation OK')
