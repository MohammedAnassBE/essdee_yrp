#!/usr/bin/env node

import assert from "node:assert/strict"

import { extractServerMessage } from "../frontend/src/api/errorMessages.js"
import { normaliseFrappeTime, plainTextFromHtml } from "../frontend/src/utils/documentValues.js"

assert.equal(
	extractServerMessage({
		_server_messages: JSON.stringify([
			JSON.stringify({ message: "The Purchase Order could not be saved." }),
		]),
	}, "fallback"),
	"The Purchase Order could not be saved.",
)
assert.equal(
	extractServerMessage({ _error_message: "Company is required." }, "fallback"),
	"Company is required.",
)
assert.equal(
	extractServerMessage({ exception: "frappe.exceptions.ValidationError: Delivery warehouse is required." }, "fallback"),
	"Delivery warehouse is required.",
)
assert.equal(
	extractServerMessage({ errors: [{ message: "Rate is missing." }], messages: ["Rate is missing.", "Check the Item Price."] }, "fallback"),
	"Rate is missing.\nCheck the Item Price.",
)
assert.equal(
	extractServerMessage({ exc: JSON.stringify(["Traceback (most recent call last):\nfrappe.exceptions.ValidationError: Stock is unavailable."]) }, "fallback"),
	"Stock is unavailable.",
)
assert.equal(extractServerMessage({}, "Request failed with status 500"), "Request failed with status 500")

assert.equal(
	plainTextFromHtml("D No 15, Om Sakthi Nagar,<br>Tiruppur &amp; Tamil Nadu<br/>641601"),
	"D No 15, Om Sakthi Nagar,\nTiruppur & Tamil Nadu\n641601",
)
assert.equal(plainTextFromHtml("<div>Line one</div><div>Line two&nbsp;</div>"), "Line one\nLine two")
assert.equal(plainTextFromHtml("Plain address"), "Plain address")
assert.equal(plainTextFromHtml("Tolerance < 5 > 2"), "Tolerance < 5 > 2")

assert.equal(normaliseFrappeTime("15:13:51.497322"), "15:13:51")
assert.equal(normaliseFrappeTime("09:05:07"), "09:05:07")
assert.equal(normaliseFrappeTime("9:05"), "09:05:00")
assert.equal(normaliseFrappeTime("Now"), "")

console.log(JSON.stringify({ passed: true, tests: 14 }))
