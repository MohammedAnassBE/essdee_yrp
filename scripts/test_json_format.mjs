import test from "node:test";
import assert from "node:assert/strict";
import { format_json_as_code, install_json_formatter } from "../essdee_yrp/public/js/json_format.js";

const code = (text) => "<pre>" + text.replace(/[&<>]/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;"}[char])) + "</pre>";

test("historical JSON markup stays literal text", () => {
    const value = '{"html":"<style>@import url(/files/archive.css)</style><img src=x onerror=alert(1)><script>alert(2)</script>"}';
    const rendered = format_json_as_code(value, code);
    assert.equal(rendered, code(value));
    assert.ok(!/<(?:style|script|img|link)\b/i.test(rendered));
    assert.ok(rendered.includes("&lt;style&gt;"));
});

test("objects are serialized without mutation and existing strings stay exact", () => {
    const value = {html:"<b>literal</b>", values:[0, false, null]};
    const before = JSON.stringify(value);
    assert.equal(format_json_as_code(value, code), code(JSON.stringify(value, null, 2)));
    assert.equal(JSON.stringify(value), before);
    assert.equal(format_json_as_code("  {\n  }\n", code), code("  {\n  }\n"));
});

test("null and undefined display empty without becoming executable content", () => {
    assert.equal(format_json_as_code(null, code), "<pre></pre>");
    assert.equal(format_json_as_code(undefined, code), "<pre></pre>");
});

test("fallback is installed once and existing upstream JSON formatter is preserved", () => {
    const formatters = {Code:code};
    install_json_formatter(formatters);
    const installed = formatters.JSON;
    assert.equal(installed('<style>test</style>'), code('<style>test</style>'));
    install_json_formatter(formatters);
    assert.equal(formatters.JSON, installed);
    const upstream = () => "upstream";
    const existing = {Code:code, JSON:upstream};
    install_json_formatter(existing);
    assert.equal(existing.JSON, upstream);
});
