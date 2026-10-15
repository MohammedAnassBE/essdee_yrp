#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	getHomePath,
	getLockedDepartment,
	getLockedRedirect,
	isLockedExit,
} from "../frontend/src/router/departmentLock.js"

function boot(meta) {
	return { ui_config: { config: {}, meta } }
}

const registered = (key) => boot({ render_mode: "Registered Experience", experience_key: key })

assert.equal(getLockedDepartment(undefined), null)
assert.equal(getLockedDepartment({}), null)
assert.equal(getLockedDepartment(boot({ render_mode: "Configurable Layout", experience_key: "cutting" })), null)
assert.equal(getLockedDepartment(registered("cutting")).path, "/cutting")
assert.equal(getLockedDepartment(registered("hr")).path, "/hr")

const warnings = []
const originalWarn = console.warn
console.warn = (...args) => warnings.push(args.join(" "))
assert.equal(getLockedDepartment(registered("unknown-desk")), null)
console.warn = originalWarn
assert.equal(warnings.length, 1)
assert.match(warnings[0], /unknown-desk/)

const cutting = getLockedDepartment(registered("cutting"))

assert.equal(getLockedRedirect("/", null), undefined)
assert.equal(getLockedRedirect("/sales", null), undefined)
assert.deepEqual(getLockedRedirect("/", cutting), { path: "/cutting", replace: true })
assert.deepEqual(getLockedRedirect("/sales", cutting), { path: "/cutting", replace: true })
assert.deepEqual(getLockedRedirect("/sales/", cutting), { path: "/cutting", replace: true })
assert.deepEqual(getLockedRedirect("/SALES", cutting), { path: "/cutting", replace: true })
assert.deepEqual(getLockedRedirect("/Sales/", cutting), { path: "/cutting", replace: true })
assert.equal(getLockedRedirect("/Cutting", cutting), undefined)
assert.equal(getLockedRedirect("/cutting", cutting), undefined)
assert.equal(getLockedRedirect("/cutting/", cutting), undefined)
assert.equal(getLockedRedirect("/cutting/plans", cutting), undefined)
assert.equal(getLockedRedirect("/sales/production-orders/PO-0001", cutting), undefined)
assert.equal(getLockedRedirect("/document", cutting), undefined)

assert.equal(isLockedExit("/", null), false)
assert.equal(isLockedExit("/", cutting), true)
assert.equal(isLockedExit("/cutting", cutting), false)

assert.equal(getHomePath(null), "/")
assert.equal(getHomePath(cutting), "/cutting")

console.log("department lock tests passed")
