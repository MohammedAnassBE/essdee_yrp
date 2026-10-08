#!/usr/bin/env node

import { existsSync, readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, resolve } from "node:path"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const dialogPath = resolve(root, "frontend/src/components/documents/RelatedRecordsDialog.vue")
const listPath = resolve(root, "frontend/src/components/common/ListView.vue")

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

assert(existsSync(dialogPath), "RelatedRecordsDialog.vue is missing")

const dialog = readFileSync(dialogPath, "utf8")
const list = readFileSync(listPath, "utf8")

for (const contract of [
	'v-model:visible',
	':initial-advanced-filters="filters"',
	':navigation-enabled="false"',
	':allow-bulk-actions="false"',
	'@row-click="openRow"',
]) {
	assert(dialog.includes(contract), `RelatedRecordsDialog omits ${contract}`)
}

assert(list.includes('initialAdvancedFilters'), "ListView has no controlled advanced-filter input")
assert(list.includes('update:advancedFilters'), "ListView does not emit applied advanced filters")
assert(list.includes('v-if="navigationEnabled"'), "ListView cannot suppress page navigation inside a dialog")

console.log("Related records dialog contract verified.")
