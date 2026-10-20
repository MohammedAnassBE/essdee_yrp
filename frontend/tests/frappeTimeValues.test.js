import assert from "node:assert/strict"
import test from "node:test"

import { normaliseFrappeTime } from "../src/utils/documentValues.js"

test("Frappe time values with single-digit fractional seconds still display", () => {
	assert.equal(normaliseFrappeTime("22:26:0.947516"), "22:26:00")
	assert.equal(normaliseFrappeTime("22:47:6.80532"), "22:47:06")
	assert.equal(normaliseFrappeTime("9:05:07"), "09:05:07")
	assert.equal(normaliseFrappeTime("22:26:00.947516"), "22:26:00")
	assert.equal(normaliseFrappeTime("22:26"), "22:26:00")
	assert.equal(normaliseFrappeTime("22:26:60"), "")
	assert.equal(normaliseFrappeTime("22:2:00"), "")
})
