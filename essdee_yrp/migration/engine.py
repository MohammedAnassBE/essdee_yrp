"""Pure, strict, resumable data-migration engine.

There are no Frappe imports in this module.  Live source and target adapters are
added only after this contract passes with in-memory documents.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, MutableMapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


SYSTEM_FIELDS = frozenset(
	{
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"parent",
		"parentfield",
		"parenttype",
	}
)
LAYOUT_FIELD_TYPES = frozenset(
	{"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold"}
)
NUMERIC_FIELD_TYPES = frozenset({"Check", "Int", "Float", "Currency", "Percent"})
TEXT_FIELD_TYPES = frozenset({"Data", "Small Text", "Text", "Long Text", "Code", "JSON", "Read Only"})


class MigrationError(RuntimeError):
	"""Raised before any write when a migration contract is incomplete."""


@dataclass(frozen=True)
class DocTypeRule:
	target: str | None = None
	field_map: Mapping[str, str] = field(default_factory=dict)
	table_option_map: Mapping[str, str] = field(default_factory=dict)
	ignored_fields: Mapping[str, str] = field(default_factory=dict)
	allowed_type_changes: frozenset[tuple[str, str]] = field(default_factory=frozenset)
	value_transformers: Mapping[str, str] = field(default_factory=dict)
	custom_transformer: str | None = None
	post_transformer: str | None = None


@dataclass(frozen=True)
class MigrationSpec:
	source: str
	target: str
	kind: str
	field_map: Mapping[str, str]
	table_option_map: Mapping[str, str]
	ignored_fields: Mapping[str, str]
	value_transformers: Mapping[str, str]
	source_schema: Mapping[str, Any]
	target_schema: Mapping[str, Any]
	dependencies: tuple[str, ...]
	issues: tuple[str, ...]
	custom_transformer: str | None = None
	post_transformer: str | None = None

	@property
	def is_child(self) -> bool:
		return bool(self.source_schema.get("istable"))

	@property
	def ready(self) -> bool:
		return not self.issues


@dataclass(frozen=True)
class MigrationPlan:
	specs: Mapping[str, MigrationSpec]
	dependency_groups: tuple[tuple[str, ...], ...]
	issues: tuple[str, ...]
	transformers: Mapping[str, "Transformer"] = field(default_factory=dict, repr=False)
	value_transformers: Mapping[str, "ValueTransformer"] = field(default_factory=dict, repr=False)
	post_transformers: Mapping[str, "PostTransformer"] = field(default_factory=dict, repr=False)
	target_schemas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict, repr=False)

	@property
	def ready(self) -> bool:
		return not self.issues

	@property
	def parent_doctypes(self) -> tuple[str, ...]:
		return tuple(
			doctype
			for group in self.dependency_groups
			for doctype in group
			if not self.specs[doctype].is_child
		)


@dataclass
class Checkpoint:
	"""Resume marker keyed by source identity and document content hash."""

	completed: dict[str, str] = field(default_factory=dict)
	failures: dict[str, str] = field(default_factory=dict)

	@staticmethod
	def key(source_doctype: str, source_name: str) -> str:
		return f"{source_doctype}:{source_name}"

	def is_current(self, source_doctype: str, source_name: str, digest: str) -> bool:
		return self.completed.get(self.key(source_doctype, source_name)) == digest

	def mark_complete(self, source_doctype: str, source_name: str, digest: str) -> None:
		key = self.key(source_doctype, source_name)
		self.completed[key] = digest
		self.failures.pop(key, None)

	def mark_failed(self, source_doctype: str, source_name: str, error: str) -> None:
		self.failures[self.key(source_doctype, source_name)] = error

	def as_dict(self) -> dict[str, dict[str, str]]:
		return {
			"completed": dict(sorted(self.completed.items())),
			"failures": dict(sorted(self.failures.items())),
		}

	@classmethod
	def from_dict(cls, value: Mapping[str, Any]) -> "Checkpoint":
		return cls(
			completed=dict(value.get("completed") or {}),
			failures=dict(value.get("failures") or {}),
		)


class Source(Protocol):
	def iter_documents(self, doctype: str) -> Iterable[Mapping[str, Any]]: ...


class Target(Protocol):
	def store(self, document: Mapping[str, Any]) -> None: ...


@dataclass
class MemorySource:
	documents: Mapping[str, Iterable[Mapping[str, Any]]]

	def iter_documents(self, doctype: str) -> Iterable[Mapping[str, Any]]:
		for document in self.documents.get(doctype, ()):
			yield deepcopy(document)


@dataclass
class MemoryTarget:
	documents: MutableMapping[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
	store_calls: int = 0

	def store(self, document: Mapping[str, Any]) -> None:
		key = (str(document["doctype"]), str(document["name"]))
		self.documents[key] = deepcopy(dict(document))
		self.store_calls += 1


@dataclass(frozen=True)
class MigrationResult:
	seen: int
	transformed: int
	stored: int
	skipped: int
	failures: tuple[str, ...]
	dry_run: bool


Transformer = Callable[
	[Mapping[str, Any], MigrationSpec, MigrationPlan],
	Mapping[str, Any],
]
ValueTransformer = Callable[[Any, Mapping[str, Any], MigrationSpec, str], Any]
PostTransformer = Callable[
	[
		Mapping[str, Any],
		Mapping[str, Any],
		MigrationSpec,
		MigrationPlan,
		Mapping[str, Any] | None,
	],
	Mapping[str, Any],
]


def _fields(schema: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
	return {
		str(row["fieldname"]): row
		for row in schema.get("fields") or ()
		if row.get("fieldname") and row.get("fieldtype") not in LAYOUT_FIELD_TYPES
	}


def _compatible_types(source_type: str, target_type: str, rule: DocTypeRule) -> bool:
	if source_type == target_type or (source_type, target_type) in rule.allowed_type_changes:
		return True
	if source_type in NUMERIC_FIELD_TYPES and target_type in NUMERIC_FIELD_TYPES:
		return True
	return source_type in TEXT_FIELD_TYPES and target_type in TEXT_FIELD_TYPES


def _mapped_option(option: Any, doctype_map: Mapping[str, str]) -> Any:
	return doctype_map.get(option, option) if isinstance(option, str) else option


def _build_spec(
	source_name: str,
	source_schema: Mapping[str, Any],
	target_schemas: Mapping[str, Mapping[str, Any]],
	doctype_map: Mapping[str, str],
	rule: DocTypeRule,
	available_transformers: frozenset[str],
	available_value_transformers: frozenset[str],
	available_post_transformers: frozenset[str],
) -> MigrationSpec:
	target_name = rule.target or doctype_map.get(source_name, source_name)
	target_schema = target_schemas.get(target_name)
	if not target_schema:
		return MigrationSpec(
			source=source_name,
			target=target_name,
			kind="blocked",
			field_map=dict(rule.field_map),
			table_option_map=dict(rule.table_option_map),
			ignored_fields=dict(rule.ignored_fields),
			value_transformers=dict(rule.value_transformers),
			source_schema=source_schema,
			target_schema={},
			dependencies=(),
			issues=(f"target DocType {target_name!r} does not exist",),
			custom_transformer=rule.custom_transformer,
			post_transformer=rule.post_transformer,
		)

	source_fields = _fields(source_schema)
	target_fields = _fields(target_schema)
	field_map = {fieldname: rule.field_map.get(fieldname, fieldname) for fieldname in source_fields}
	issues: list[str] = []
	dependencies: set[str] = set()
	mapped = bool(
		target_name != source_name
		or rule.field_map
		or rule.table_option_map
		or rule.post_transformer
	)
	if rule.post_transformer and rule.post_transformer not in available_post_transformers:
		issues.append(f"post transformer {rule.post_transformer!r} is required")
	if rule.custom_transformer:
		for source_field in source_fields.values():
			if source_field.get("fieldtype") == "Link" and isinstance(source_field.get("options"), str):
				dependency = str(source_field["options"])
				if dependency != source_name:
					dependencies.add(dependency)
		if rule.custom_transformer not in available_transformers:
			issues.append(f"custom transformer {rule.custom_transformer!r} is required")
		return MigrationSpec(
			source=source_name,
			target=target_name,
			kind="custom",
			field_map=field_map,
			table_option_map=dict(rule.table_option_map),
			ignored_fields=dict(rule.ignored_fields),
			value_transformers=dict(rule.value_transformers),
			source_schema=source_schema,
			target_schema=target_schema,
			dependencies=tuple(sorted(dependencies)),
			issues=tuple(issues),
			custom_transformer=rule.custom_transformer,
			post_transformer=rule.post_transformer,
		)

	for source_fieldname, source_field in source_fields.items():
		if source_fieldname in rule.ignored_fields:
			mapped = True
			continue
		target_fieldname = field_map[source_fieldname]
		target_field = target_fields.get(target_fieldname)
		if not target_field:
			issues.append(f"{source_fieldname}: target field {target_fieldname!r} does not exist")
			continue

		source_type = str(source_field.get("fieldtype") or "")
		target_type = str(target_field.get("fieldtype") or "")
		value_transformer = rule.value_transformers.get(source_fieldname)
		if value_transformer and value_transformer not in available_value_transformers:
			issues.append(
				f"{source_fieldname}: value transformer {value_transformer!r} is required"
			)
		if not _compatible_types(source_type, target_type, rule):
			issues.append(f"{source_fieldname}: incompatible type {source_type!r} -> {target_type!r}")
		if source_type != target_type:
			mapped = True

		if source_type in {"Link", "Table", "Table MultiSelect"}:
			expected = rule.table_option_map.get(
				source_fieldname,
				_mapped_option(source_field.get("options"), doctype_map),
			)
			actual = target_field.get("options")
			if expected != actual and not value_transformer:
				issues.append(
					f"{source_fieldname}: target option {actual!r} does not match mapped source option {expected!r}"
				)
			if source_type == "Link" and isinstance(source_field.get("options"), str):
				dependency = str(source_field["options"])
				if dependency != source_name:
					dependencies.add(dependency)

	kind = "mapped" if mapped else "identity"
	return MigrationSpec(
		source=source_name,
		target=target_name,
		kind=kind,
		field_map=field_map,
		table_option_map=dict(rule.table_option_map),
		ignored_fields=dict(rule.ignored_fields),
		value_transformers=dict(rule.value_transformers),
		source_schema=source_schema,
		target_schema=target_schema,
		dependencies=tuple(sorted(dependencies)),
		issues=tuple(issues),
		custom_transformer=rule.custom_transformer,
		post_transformer=rule.post_transformer,
	)


def _dependency_groups(specs: Mapping[str, MigrationSpec]) -> tuple[tuple[str, ...], ...]:
	"""Return deterministic topological groups, collapsing cyclic Link graphs."""

	nodes = tuple(sorted(specs))
	edges = {name: {dep for dep in specs[name].dependencies if dep in specs} for name in nodes}
	index = 0
	stack: list[str] = []
	indices: dict[str, int] = {}
	lowlinks: dict[str, int] = {}
	on_stack: set[str] = set()
	components: list[tuple[str, ...]] = []

	def visit(node: str) -> None:
		nonlocal index
		indices[node] = index
		lowlinks[node] = index
		index += 1
		stack.append(node)
		on_stack.add(node)
		for dependency in sorted(edges[node]):
			if dependency not in indices:
				visit(dependency)
				lowlinks[node] = min(lowlinks[node], lowlinks[dependency])
			elif dependency in on_stack:
				lowlinks[node] = min(lowlinks[node], indices[dependency])
		if lowlinks[node] == indices[node]:
			component: list[str] = []
			while True:
				member = stack.pop()
				on_stack.remove(member)
				component.append(member)
				if member == node:
					break
			components.append(tuple(sorted(component)))

	for node in nodes:
		if node not in indices:
			visit(node)

	component_for = {node: idx for idx, component in enumerate(components) for node in component}
	dependencies = {idx: set() for idx in range(len(components))}
	for node, node_edges in edges.items():
		for dependency in node_edges:
			source_component = component_for[node]
			target_component = component_for[dependency]
			if source_component != target_component:
				dependencies[source_component].add(target_component)

	ordered: list[tuple[str, ...]] = []
	remaining = set(dependencies)
	while remaining:
		ready = sorted(
			(idx for idx in remaining if not (dependencies[idx] & remaining)),
			key=lambda idx: components[idx],
		)
		if not ready:
			raise MigrationError("could not resolve DocType dependency graph")
		for idx in ready:
			ordered.append(components[idx])
			remaining.remove(idx)
	return tuple(ordered)


def build_plan(
	source_schemas: Mapping[str, Mapping[str, Any]],
	target_schemas: Mapping[str, Mapping[str, Any]],
	*,
	rules: Mapping[str, DocTypeRule] | None = None,
	doctype_map: Mapping[str, str] | None = None,
	transformers: Mapping[str, Transformer] | None = None,
	value_transformers: Mapping[str, ValueTransformer] | None = None,
	post_transformers: Mapping[str, PostTransformer] | None = None,
) -> MigrationPlan:
	"""Build a strict plan. Every unmapped field becomes a visible blocker."""

	rules = rules or {}
	doctype_map = doctype_map or {}
	transformers = transformers or {}
	value_transformers = value_transformers or {}
	post_transformers = post_transformers or {}
	specs = {
		name: _build_spec(
			name,
			schema,
			target_schemas,
			doctype_map,
			rules.get(name, DocTypeRule(target=doctype_map.get(name, name))),
			frozenset(transformers),
			frozenset(value_transformers),
			frozenset(post_transformers),
		)
		for name, schema in sorted(source_schemas.items())
	}
	issues = tuple(
		f"{name}: {issue}"
		for name, spec in sorted(specs.items())
		for issue in spec.issues
	)
	return MigrationPlan(
		specs=specs,
		dependency_groups=_dependency_groups(specs),
		issues=issues,
		transformers=transformers,
		value_transformers=value_transformers,
		post_transformers=post_transformers,
		target_schemas=target_schemas,
	)


def _doctype_controller_fields(schema: Mapping[str, Any]) -> set[str]:
	controllers = {
		str(field.get("options"))
		for field in schema.get("fields") or ()
		if field.get("fieldtype") == "Dynamic Link" and field.get("options")
	}
	controllers.update(
		str(field.get("fieldname"))
		for field in schema.get("fields") or ()
		if field.get("fieldtype") == "Link"
		and field.get("options") == "DocType"
		and field.get("fieldname")
	)
	return controllers


def transform_document(
	document: Mapping[str, Any],
	plan: MigrationPlan,
	*,
	strict: bool = True,
	parent_document: Mapping[str, Any] | None = None,
	_spec_override: MigrationSpec | None = None,
) -> dict[str, Any]:
	"""Transform one parent or child document according to a verified plan."""

	source_doctype = str(document.get("doctype") or "")
	spec = _spec_override or plan.specs.get(source_doctype)
	if not spec:
		raise MigrationError(f"no migration spec for source DocType {source_doctype!r}")
	if strict and spec.issues:
		raise MigrationError(f"{source_doctype} is blocked: {'; '.join(spec.issues)}")
	if spec.custom_transformer:
		transformer = plan.transformers.get(spec.custom_transformer)
		if not transformer:
			raise MigrationError(
				f"{source_doctype} requires custom transformer {spec.custom_transformer!r}"
			)
		output = dict(transformer(deepcopy(document), spec, plan))
		if output.get("doctype") != spec.target:
			raise MigrationError(
				f"{spec.custom_transformer} returned DocType {output.get('doctype')!r}; expected {spec.target!r}"
			)
		expected_name = spec.target if spec.target_schema.get("issingle") else document.get("name")
		if expected_name and output.get("name") != expected_name:
			raise MigrationError(f"{spec.custom_transformer} did not preserve document name")
		_copy_migration_secrets(document, output)
		return _apply_post_transformer(output, document, spec, plan, parent_document)

	source_fields = _fields(spec.source_schema)
	target_fields = _fields(spec.target_schema)
	doctype_controllers = _doctype_controller_fields(spec.source_schema)
	output: dict[str, Any] = {"doctype": spec.target}
	_copy_migration_secrets(document, output)

	for fieldname in SYSTEM_FIELDS:
		if fieldname in document:
			output[fieldname] = deepcopy(document[fieldname])
	if spec.target_schema.get("issingle"):
		output["name"] = spec.target
	if "parenttype" in output:
		parent_spec = plan.specs.get(str(output["parenttype"]))
		if parent_spec:
			output["parenttype"] = parent_spec.target
	if "parentfield" in output and document.get("parenttype") in plan.specs:
		parent_spec = plan.specs[str(document["parenttype"])]
		output["parentfield"] = parent_spec.field_map.get(str(output["parentfield"]), output["parentfield"])

	for source_fieldname, source_field in source_fields.items():
		if source_fieldname not in document or source_fieldname in spec.ignored_fields:
			continue
		target_fieldname = spec.field_map.get(source_fieldname, source_fieldname)
		if target_fieldname not in target_fields:
			if strict:
				raise MigrationError(
					f"{source_doctype}.{source_fieldname} has no target field {target_fieldname!r}"
				)
			continue
		value = deepcopy(document[source_fieldname])
		if source_field.get("fieldtype") in {"Table", "Table MultiSelect"} and value:
			target_child_doctype = spec.table_option_map.get(source_fieldname)
			value = [
				transform_document(
					row,
					plan,
					strict=strict,
					parent_document=document,
					_spec_override=_contextual_child_spec(row, plan, target_child_doctype)
					if target_child_doctype
					else None,
				)
				for row in value
			]
		elif source_fieldname in doctype_controllers and isinstance(value, str):
			value = plan.specs[value].target if value in plan.specs else value
		value_transformer = spec.value_transformers.get(source_fieldname)
		if value_transformer:
			transformer = plan.value_transformers.get(value_transformer)
			if not transformer:
				raise MigrationError(
					f"{source_doctype}.{source_fieldname} requires value transformer {value_transformer!r}"
				)
			value = transformer(value, document, spec, source_fieldname)
		output[target_fieldname] = value

	return _apply_post_transformer(output, document, spec, plan, parent_document)


def _copy_migration_secrets(
	source: Mapping[str, Any],
	target: MutableMapping[str, Any],
) -> None:
	"""Carry decrypted source secrets only inside the in-memory migration payload.

	The live target adapter immediately re-encrypts these values with the target
	site key. They are never written to the checkpoint or report.
	"""

	passwords = source.get("__migration_passwords")
	if passwords:
		target["__migration_passwords"] = deepcopy(passwords)


def _contextual_child_spec(
	document: Mapping[str, Any],
	plan: MigrationPlan,
	target_doctype: str,
) -> MigrationSpec:
	source_doctype = str(document.get("doctype") or "")
	source_spec = plan.specs.get(source_doctype)
	target_schema = plan.target_schemas.get(target_doctype)
	if not source_spec or not target_schema:
		raise MigrationError(
			f"cannot map contextual child {source_doctype!r} to {target_doctype!r}"
		)
	return MigrationSpec(
		source=source_spec.source,
		target=target_doctype,
		kind="mapped",
		field_map=source_spec.field_map,
		table_option_map=source_spec.table_option_map,
		ignored_fields=source_spec.ignored_fields,
		value_transformers=source_spec.value_transformers,
		source_schema=source_spec.source_schema,
		target_schema=target_schema,
		dependencies=source_spec.dependencies,
		issues=(),
		custom_transformer=None,
		post_transformer=source_spec.post_transformer,
	)


def _apply_post_transformer(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent_document: Mapping[str, Any] | None,
) -> dict[str, Any]:
	if not spec.post_transformer:
		return dict(output)
	transformer = plan.post_transformers.get(spec.post_transformer)
	if not transformer:
		raise MigrationError(
			f"{spec.source} requires post transformer {spec.post_transformer!r}"
		)
	result = dict(transformer(output, source, spec, plan, parent_document))
	if result.get("doctype") != spec.target:
		raise MigrationError(
			f"{spec.post_transformer} returned DocType {result.get('doctype')!r}; "
			f"expected {spec.target!r}"
		)
	return result


def document_digest(document: Mapping[str, Any]) -> str:
	payload = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(payload.encode()).hexdigest()


def run_migration(
	plan: MigrationPlan,
	source: Source,
	target: Target,
	*,
	checkpoint: Checkpoint | None = None,
	dry_run: bool = True,
) -> MigrationResult:
	"""Run against adapters. ``dry_run=True`` guarantees ``Target.store`` is never called."""

	if not plan.ready:
		raise MigrationError("migration plan has unresolved issues:\n" + "\n".join(plan.issues))
	checkpoint = checkpoint or Checkpoint()
	seen = transformed = stored = skipped = 0
	failures: list[str] = []

	for doctype in plan.parent_doctypes:
		for source_document in source.iter_documents(doctype):
			seen += 1
			name = str(source_document.get("name") or "")
			if not name:
				failures.append(f"{doctype}: document has no name")
				continue
			digest = document_digest(source_document)
			if checkpoint.is_current(doctype, name, digest):
				skipped += 1
				continue
			try:
				target_document = transform_document(source_document, plan)
				transformed += 1
				if not dry_run:
					target.store(target_document)
					stored += 1
					checkpoint.mark_complete(doctype, name, digest)
			except Exception as exc:
				message = f"{doctype}:{name}: {exc}"
				failures.append(message)
				if not dry_run:
					checkpoint.mark_failed(doctype, name, str(exc))

	return MigrationResult(
		seen=seen,
		transformed=transformed,
		stored=stored,
		skipped=skipped,
		failures=tuple(failures),
		dry_run=dry_run,
	)
