import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	currentFrappeTime,
	formatTimeDisplay,
	parseTimeInput,
	setTimePart,
	usesTwelveHourClock,
} from "../src/utils/timeInput.js"

const now = new Date(2026, 9, 24, 9, 5, 7)

test("typed times parse to Frappe HH:mm:ss", () => {
	assert.equal(parseTimeInput("14:30"), "14:30:00")
	assert.equal(parseTimeInput("1430"), "14:30:00")
	assert.equal(parseTimeInput("930"), "09:30:00")
	assert.equal(parseTimeInput("9"), "09:00:00")
	assert.equal(parseTimeInput("14.30"), "14:30:00")
	assert.equal(parseTimeInput("14:30:15"), "14:30:15")
	assert.equal(parseTimeInput("143015"), "14:30:15")
	assert.equal(parseTimeInput(" 7:5 "), "07:05:00")
})

test("12-hour input with am/pm parses", () => {
	assert.equal(parseTimeInput("2:30 pm"), "14:30:00")
	assert.equal(parseTimeInput("2:30PM"), "14:30:00")
	assert.equal(parseTimeInput("2pm"), "14:00:00")
	assert.equal(parseTimeInput("12 am"), "00:00:00")
	assert.equal(parseTimeInput("12:15 p.m."), "12:15:00")
	assert.equal(parseTimeInput("11:59 a"), "11:59:00")
})

test("empty input clears and invalid input is rejected", () => {
	assert.equal(parseTimeInput(""), "")
	assert.equal(parseTimeInput("   "), "")
	for (const text of ["24:00", "12:60", "13 pm", "0 am", "abc", "12345", "1:2:3:4", "14:30:60"]) {
		assert.equal(parseTimeInput(text), null, text)
	}
})

test("Now uses the current local time with seconds", () => {
	assert.equal(currentFrappeTime(now), "09:05:07")
	assert.equal(parseTimeInput("now", now), "09:05:07")
	assert.equal(parseTimeInput("n", now), "09:05:07")
	assert.match(currentFrappeTime(), /^\d{2}:\d{2}:\d{2}$/)
})

test("display hides zero seconds and follows the clock format", () => {
	assert.equal(formatTimeDisplay("14:30:00"), "14:30")
	assert.equal(formatTimeDisplay("14:30:15"), "14:30:15")
	assert.equal(formatTimeDisplay("9:05:00.123456"), "09:05")
	assert.equal(formatTimeDisplay(""), "")
	assert.equal(formatTimeDisplay("14:30:00", { twelveHour: true }), "2:30 PM")
	assert.equal(formatTimeDisplay("00:05:09", { twelveHour: true }), "12:05:09 AM")
})

test("12-hour clock follows System Settings time_format", () => {
	assert.equal(usesTwelveHourClock({ sysdefaults: { time_format: "hh:mm a" } }), true)
	assert.equal(usesTwelveHourClock({ sysdefaults: { time_format: "HH:mm:ss" } }), false)
	assert.equal(usesTwelveHourClock({}), false)
	assert.equal(usesTwelveHourClock(undefined), false)
})

test("picking an hour or minute keeps the other part", () => {
	assert.equal(setTimePart("14:30:15", "hour", 9), "09:30:00")
	assert.equal(setTimePart("14:30:15", "minute", 45), "14:45:00")
	assert.equal(setTimePart("", "minute", 5), "00:05:00")
})

test("TimeField is a typed input with Now, a clock panel and conditional Clear", () => {
	const source = readFileSync(new URL("../src/components/common/TimeField.vue", import.meta.url), "utf8")
	assert.match(source, /import Popover from "primevue\/popover"/)
	assert.match(source, /parseTimeInput\(draft\.value\)/)
	assert.match(source, /function setNow\(\) \{\n\tcommit\(currentFrappeTime\(\)\)/)
	assert.match(source, /canClear = computed\(\(\) => props\.showClear \|\| !\(props\.required/)
	assert.match(source, /<template v-if="isEditable">/)
	assert.doesNotMatch(source, /TemporalFieldBase/)
})
