#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare BoTTube's OpenAPI, Flask source, and an optional live deployment.

The Flask inventory is extracted from Python's AST.  Production modules are
never imported, because importing bottube_server.py creates directories and
initializes several database-backed integrations.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"})
SAFE_LIVE_METHODS = frozenset({"GET", "HEAD"})
MISSING_IN_CODE = 1
MISSING_IN_SPEC = 2
LIVE_UNAVAILABLE = 4
STALE_ALLOWANCE = 8
CONFIG_ERROR = 64

_FLASK_PARAMETER = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")
_OPENAPI_PARAMETER = re.compile(r"{([^{}]+)}")


class ConfigError(ValueError):
    """Raised for invalid sentinel input or unsupported source syntax."""


@dataclass(frozen=True, order=True)
class Operation:
    """A normalized HTTP method and route template."""

    method: str
    path: str

    def __post_init__(self) -> None:
        method = self.method.upper()
        if method not in HTTP_METHODS:
            raise ConfigError(f"unsupported HTTP method: {self.method}")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "path", normalize_path(self.path))

    @classmethod
    def parse(cls, value: str) -> "Operation":
        try:
            method, path = value.strip().split(None, 1)
        except ValueError as exc:
            raise ConfigError(f"operation must be 'METHOD /path': {value!r}") from exc
        return cls(method, path)

    def label(self) -> str:
        return f"{self.method} {self.path}"

    def as_dict(self) -> dict[str, str]:
        return {"method": self.method, "path": self.path}


@dataclass
class FlaskInventory:
    """Declared Flask operations plus methods Flask adds automatically."""

    declared: set[Operation]
    implicit: set[Operation]

    @property
    def effective(self) -> set[Operation]:
        return self.declared | self.implicit


def normalize_path(path: str) -> str:
    """Normalize Flask converters to OpenAPI parameter syntax."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ConfigError(f"route path must start with '/': {path!r}")
    if "?" in path or "#" in path or "\n" in path or "\r" in path:
        raise ConfigError(f"route path must not contain query, fragment, or newline data: {path!r}")
    return _FLASK_PARAMETER.sub(r"{\1}", path)


def _literal_string(node: ast.AST, context: str) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    raise ConfigError(f"{context} must be a string literal")


def _literal_methods(node: ast.AST, context: str) -> set[str]:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        raise ConfigError(f"{context} methods must be a literal list, tuple, or set")
    methods = set()
    for item in node.elts:
        methods.add(_literal_string(item, context).upper())
    unsupported = methods - HTTP_METHODS
    if unsupported:
        raise ConfigError(f"{context} uses unsupported methods: {', '.join(sorted(unsupported))}")
    return methods


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _call_owner(call: ast.Call) -> tuple[str, str] | None:
    if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
        return None
    return call.func.value.id, call.func.attr


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        if parent:
            return parent + "." + node.attr
    return None


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def _flask_constructor_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    flask_modules: set[str] = set()
    app_factories: set[str] = set()
    blueprint_factories: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "flask":
                    flask_modules.add(alias.asname or "flask")
        elif isinstance(node, ast.ImportFrom) and node.module == "flask":
            for alias in node.names:
                local_name = alias.asname or alias.name
                if alias.name == "Flask":
                    app_factories.add(local_name)
                elif alias.name == "Blueprint":
                    blueprint_factories.add(local_name)
    app_factories.update(module + ".Flask" for module in flask_modules)
    blueprint_factories.update(module + ".Blueprint" for module in flask_modules)
    return app_factories, blueprint_factories


def _discover_route_owners(
    tree: ast.AST,
    source: Path,
    configured_app_names: set[str],
) -> tuple[set[str], dict[str, set[str]]]:
    app_factories, blueprint_factories = _flask_constructor_names(tree)
    assignments = [node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))]
    app_owners = set(configured_app_names)
    blueprint_canonical: dict[str, str] = {}
    declared_prefixes: dict[str, str] = {}

    for node in assignments:
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        constructor = _qualified_name(value.func)
        targets = _assignment_targets(node)
        if constructor in app_factories:
            app_owners.update(targets)
        elif constructor in blueprint_factories:
            prefix_node = _keyword(value, "url_prefix")
            prefix = "" if prefix_node is None else _literal_string(
                prefix_node, f"{source}:{node.lineno}: Blueprint url_prefix"
            )
            for target in targets:
                blueprint_canonical[target] = target
                declared_prefixes[target] = prefix

    changed = True
    while changed:
        changed = False
        for node in assignments:
            if not isinstance(node.value, ast.Name):
                continue
            value_name = node.value.id
            for target in _assignment_targets(node):
                if value_name in app_owners and target not in app_owners:
                    app_owners.add(target)
                    changed = True
                canonical = blueprint_canonical.get(value_name)
                if canonical is not None and blueprint_canonical.get(target) != canonical:
                    blueprint_canonical[target] = canonical
                    changed = True

    registration_prefixes: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        owner = _call_owner(node)
        if owner is None or owner[0] not in app_owners or owner[1] != "register_blueprint":
            continue
        blueprint_node = node.args[0] if node.args else _keyword(node, "blueprint")
        if blueprint_node is None:
            raise ConfigError(f"{source}:{node.lineno}: register_blueprint has no blueprint")
        if not isinstance(blueprint_node, ast.Name):
            raise ConfigError(
                f"{source}:{node.lineno}: qualified register_blueprint owner is unsupported; assign it a local alias"
            )
        canonical = blueprint_canonical.get(blueprint_node.id)
        if canonical is None:
            # Imported blueprints are outside this source file's configured inventory.
            if _keyword(node, "url_prefix") is not None:
                raise ConfigError(
                    f"{source}:{node.lineno}: cannot resolve url_prefix override for imported blueprint "
                    f"{blueprint_node.id!r}; declare and register it in one configured source"
                )
            continue
        prefix_node = _keyword(node, "url_prefix")
        if prefix_node is None or (isinstance(prefix_node, ast.Constant) and prefix_node.value is None):
            prefix = declared_prefixes[canonical]
        else:
            prefix = _literal_string(prefix_node, f"{source}:{node.lineno}: register_blueprint url_prefix")
        registration_prefixes.setdefault(canonical, set()).add(prefix)

    effective_prefixes: dict[str, set[str]] = {}
    for owner, canonical in blueprint_canonical.items():
        effective_prefixes[owner] = registration_prefixes.get(canonical, {declared_prefixes[canonical]})
    return app_owners, effective_prefixes


def _rule_node(call: ast.Call) -> ast.AST | None:
    if call.args:
        return call.args[0]
    return _keyword(call, "rule")


def _declared_and_implicit_methods(
    call: ast.Call,
    shortcut: str,
    context: str,
) -> tuple[set[str], set[str]]:
    if shortcut == "route" or shortcut == "add_url_rule":
        methods_node = _keyword(call, "methods")
        declared = {"GET"} if methods_node is None else _literal_methods(methods_node, context)
    else:
        declared = {shortcut.upper()}

    automatic_options_node = _keyword(call, "provide_automatic_options")
    if automatic_options_node is None:
        automatic_options = True
    elif isinstance(automatic_options_node, ast.Constant) and automatic_options_node.value is None:
        automatic_options = True
    elif isinstance(automatic_options_node, ast.Constant) and isinstance(automatic_options_node.value, bool):
        automatic_options = automatic_options_node.value
    else:
        raise ConfigError(f"{context} provide_automatic_options must be a boolean literal")

    implicit: set[str] = set()
    if "GET" in declared and "HEAD" not in declared:
        implicit.add("HEAD")
    if automatic_options and "OPTIONS" not in declared:
        implicit.add("OPTIONS")
    return declared, implicit


def extract_flask_inventory(
    source_paths: Sequence[Path],
    app_names: Iterable[str] = ("app",),
) -> FlaskInventory:
    """Extract declared and Flask-implicit operations without importing code."""
    declared_operations: set[Operation] = set()
    implicit_operations: set[Operation] = set()
    configured_app_names = set(app_names)

    for source in sorted(source_paths):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise ConfigError(f"could not parse application source {source}: {exc}") from exc

        app_owners, blueprint_prefixes = _discover_route_owners(tree, source, configured_app_names)
        route_owners = app_owners | set(blueprint_prefixes)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    decorator_name = decorator.func.attr if isinstance(decorator.func, ast.Attribute) else None
                    if decorator_name not in {"route", "get", "post", "put", "patch", "delete"}:
                        continue
                    rule_node = _rule_node(decorator)
                    if rule_node is None:
                        raise ConfigError(f"{source}:{decorator.lineno}: route has no rule")
                    if not isinstance(rule_node, ast.Constant) or not isinstance(rule_node.value, str):
                        raise ConfigError(f"{source}:{decorator.lineno}: route rule must be a string literal")
                    if not rule_node.value.startswith("/"):
                        continue
                    owner = _call_owner(decorator)
                    if owner is None or owner[0] not in route_owners:
                        qualified_owner = _qualified_name(decorator.func.value)
                        raise ConfigError(
                            f"{source}:{decorator.lineno}: unsupported route owner {qualified_owner!r}; "
                            "assign Flask apps or blueprints to a local alias"
                        )
                    object_name = owner[0]
                    route = rule_node.value
                    context = f"{source}:{decorator.lineno}: route"
                    methods, implicit_methods = _declared_and_implicit_methods(decorator, decorator_name, context)
                    prefixes = blueprint_prefixes.get(object_name, {""})
                    for prefix in prefixes:
                        full_path = _join_route(prefix, route)
                        declared_operations.update(Operation(method, full_path) for method in methods)
                        implicit_operations.update(Operation(method, full_path) for method in implicit_methods)

            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_url_rule":
                continue
            rule_node = _rule_node(node)
            if rule_node is None:
                raise ConfigError(f"{source}:{node.lineno}: add_url_rule has no rule")
            route = _literal_string(rule_node, f"{source}:{node.lineno}: add_url_rule rule")
            owner = _call_owner(node)
            if owner is None or owner[0] not in route_owners:
                qualified_owner = _qualified_name(node.func.value)
                raise ConfigError(
                    f"{source}:{node.lineno}: unsupported add_url_rule owner {qualified_owner!r}; "
                    "assign Flask apps or blueprints to a local alias"
                )
            context = f"{source}:{node.lineno}: add_url_rule"
            methods, implicit_methods = _declared_and_implicit_methods(node, "add_url_rule", context)
            prefixes = blueprint_prefixes.get(owner[0], {""})
            for prefix in prefixes:
                full_path = _join_route(prefix, route)
                declared_operations.update(Operation(method, full_path) for method in methods)
                implicit_operations.update(Operation(method, full_path) for method in implicit_methods)

    implicit_operations.difference_update(declared_operations)
    return FlaskInventory(declared_operations, implicit_operations)


def _join_route(prefix: str, route: str) -> str:
    if not prefix:
        return route
    if route == "/":
        return prefix.rstrip("/") + "/"
    return prefix.rstrip("/") + "/" + route.lstrip("/")


def extract_flask_operations(source_paths: Sequence[Path], app_names: Iterable[str] = ("app",)) -> set[Operation]:
    """Extract explicitly declared Flask operations without importing code."""
    return extract_flask_inventory(source_paths, app_names).declared


def load_openapi_operations(path: Path) -> set[Operation]:
    """Load operations from an OpenAPI 3 document."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised by the CI install contract
        raise ConfigError("PyYAML is required to read openapi.yaml (pip install PyYAML)") from exc

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"could not read OpenAPI document {path}: {exc}") from exc
    if not isinstance(document, Mapping) or not isinstance(document.get("paths"), Mapping):
        raise ConfigError(f"OpenAPI document {path} must contain a paths mapping")

    operations: set[Operation] = set()
    for route, path_item in document["paths"].items():
        if not isinstance(route, str) or not isinstance(path_item, Mapping):
            raise ConfigError(f"invalid OpenAPI path item: {route!r}")
        for method in path_item:
            if isinstance(method, str) and method.upper() in HTTP_METHODS:
                operations.add(Operation(method, route))
    return operations


def _resolve_sources(repo_root: Path, patterns: Sequence[str]) -> list[Path]:
    if not patterns:
        raise ConfigError("application_sources must contain at least one source glob")
    matches: set[Path] = set()
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern:
            raise ConfigError("application_sources entries must be non-empty strings")
        current = {path.resolve() for path in repo_root.glob(pattern) if path.is_file()}
        if not current:
            raise ConfigError(f"application source pattern matched no files: {pattern}")
        for path in current:
            try:
                path.relative_to(repo_root)
            except ValueError as exc:
                raise ConfigError(f"application source is outside repo root: {path}") from exc
        matches.update(current)
    return sorted(matches)


def _operation_list(values: Any, context: str) -> set[Operation]:
    if values is None:
        return set()
    if not isinstance(values, list):
        raise ConfigError(f"{context} must be a list")
    operations = set()
    for value in values:
        if isinstance(value, str):
            operations.add(Operation.parse(value))
        elif isinstance(value, Mapping):
            try:
                operations.add(Operation(str(value["method"]), str(value["path"])))
            except KeyError as exc:
                raise ConfigError(f"{context} entries require method and path") from exc
        else:
            raise ConfigError(f"{context} entries must be strings or objects")
    return operations


def _path_matches(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _operation_dicts(operations: Iterable[Operation]) -> list[dict[str, str]]:
    return [operation.as_dict() for operation in sorted(operations)]


def _parse_fixtures(values: Sequence[str]) -> dict[str, str]:
    fixtures: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ConfigError(f"fixture must be NAME=VALUE: {value!r}")
        name, fixture = value.split("=", 1)
        if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ConfigError(f"invalid fixture name: {name!r}")
        fixtures[name] = _fixture_segment(name, fixture)
    return fixtures


def _fixture_segment(name: str, value: Any) -> str:
    """Validate one fixture as a non-traversing URL path segment."""
    segment = str(value)
    if not segment or not segment.strip():
        raise ConfigError(f"fixture value must not be empty: {name}")

    decoded = segment
    for _ in range(4):
        if decoded in {".", ".."}:
            raise ConfigError(f"fixture value must not be a dot segment: {name}")
        if any(char in decoded for char in ("/", "\\")):
            raise ConfigError(f"fixture value must be one path segment: {name}")
        if any(ord(char) < 32 or ord(char) == 127 for char in decoded):
            raise ConfigError(f"fixture value contains control characters: {name}")
        next_value = urllib.parse.unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    else:
        raise ConfigError(f"fixture value is excessively encoded: {name}")

    if decoded in {".", ".."} or any(char in decoded for char in ("/", "\\")):
        raise ConfigError(f"fixture value could normalize outside one path segment: {name}")
    return segment


def _timeout_seconds(value: Any) -> float:
    if isinstance(value, bool):
        raise ConfigError("timeout must be a positive number")
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("timeout must be a positive number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ConfigError("timeout must be a positive number")
    return timeout


def render_path(path: str, fixtures: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    """Render an OpenAPI route template with URL-encoded fixture values."""
    missing = sorted({name for name in _OPENAPI_PARAMETER.findall(path) if name not in fixtures})
    if missing:
        return None, missing

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return urllib.parse.quote(_fixture_segment(name, fixtures[name]), safe="")

    return _OPENAPI_PARAMETER.sub(replace, path), []


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ANN001
        return None


def request_head(url: str, timeout: float) -> int:
    """Make one credential-free HEAD request without following redirects."""
    request = urllib.request.Request(
        url,
        headers={"Accept": "*/*", "User-Agent": "bottube-deployment-drift/1"},
        method="HEAD",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def validate_live_base_url(base_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(base_url)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ConfigError(f"invalid live base URL: {exc}") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError("live base URL must be an absolute http:// or https:// URL")
    if hostname is None:
        raise ConfigError("live base URL must include a valid hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError("live base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ConfigError("live base URL must not contain a query string or fragment")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in base_url):
        raise ConfigError("live base URL must not contain whitespace or control characters")
    return base_url.rstrip("/")


def probe_live(
    operations: Iterable[Operation],
    base_url: str,
    fixtures: Mapping[str, Any],
    timeout: float,
    requester: Callable[[str, float], int] = request_head,
) -> list[dict[str, Any]]:
    """Probe only safe route operations, using HEAD on the wire."""
    base_url = validate_live_base_url(base_url)
    results: list[dict[str, Any]] = []
    for operation in sorted(set(operations)):
        if operation.method not in SAFE_LIVE_METHODS:
            raise ConfigError(f"live probes may only target GET or HEAD: {operation.label()}")
        request_path, missing = render_path(operation.path, fixtures)
        result: dict[str, Any] = {
            "available": False,
            "method": operation.method,
            "path": operation.path,
            "reason": "",
            "request_method": "HEAD",
            "request_path": request_path,
            "status": None,
        }
        if missing:
            result["reason"] = "missing_fixture:" + ",".join(missing)
            results.append(result)
            continue

        try:
            status = int(requester(base_url + str(request_path), timeout))
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            result["reason"] = "network_error:" + type(exc).__name__
            results.append(result)
            continue
        result["status"] = status
        if status in {404, 405} or status >= 500:
            result["reason"] = f"http_status:{status}"
        else:
            result["available"] = True
            result["reason"] = "route_present"
        results.append(result)
    return results


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read sentinel config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError("sentinel config root must be a JSON object")
    return value


def build_report(
    repo_root: Path,
    config: Mapping[str, Any],
    *,
    live_enabled: bool = False,
    live_base_url: str | None = None,
    fixture_overrides: Mapping[str, str] | None = None,
    requester: Callable[[str, float], int] = request_head,
) -> dict[str, Any]:
    """Build a deterministic drift report from validated inputs."""
    openapi_name = config.get("openapi", "openapi.yaml")
    if not isinstance(openapi_name, str):
        raise ConfigError("openapi must be a path string")
    openapi_path = (repo_root / openapi_name).resolve()
    try:
        openapi_path.relative_to(repo_root)
    except ValueError as exc:
        raise ConfigError("openapi path must stay inside the repo root") from exc

    source_patterns = config.get("application_sources", ["bottube_server.py"])
    if not isinstance(source_patterns, list):
        raise ConfigError("application_sources must be a list")
    source_paths = _resolve_sources(repo_root, source_patterns)
    app_names = config.get("application_names", ["app"])
    if not isinstance(app_names, list) or not all(isinstance(name, str) for name in app_names):
        raise ConfigError("application_names must be a list of strings")

    spec_operations = load_openapi_operations(openapi_path)
    flask_inventory = extract_flask_inventory(source_paths, app_names)
    code_operations = flask_inventory.declared
    effective_code_operations = flask_inventory.effective
    canaries = _operation_list(config.get("canaries", []), "canaries")
    unsafe_canaries = canaries - {op for op in canaries if op.method in SAFE_LIVE_METHODS}
    if unsafe_canaries:
        labels = ", ".join(operation.label() for operation in sorted(unsafe_canaries))
        raise ConfigError(f"canaries must be safe GET or HEAD routes: {labels}")

    expected_in_code = spec_operations | canaries
    missing_in_code = expected_in_code - effective_code_operations

    patterns = config.get("missing_in_spec_patterns", ["*"])
    if not isinstance(patterns, list) or not patterns or not all(isinstance(item, str) for item in patterns):
        raise ConfigError("missing_in_spec_patterns must be a non-empty list of glob strings")
    scoped_code = {operation for operation in code_operations if _path_matches(operation.path, patterns)}
    missing_in_spec = scoped_code - spec_operations - canaries

    allowed_config = config.get("allowed_drift", {})
    if not isinstance(allowed_config, Mapping):
        raise ConfigError("allowed_drift must be an object")
    allowed_missing_in_code = _operation_list(
        allowed_config.get("missing_in_code", []), "allowed_drift.missing_in_code"
    )
    allowed_missing_in_spec = _operation_list(
        allowed_config.get("missing_in_spec", []), "allowed_drift.missing_in_spec"
    )
    blocking_missing_in_code = missing_in_code - allowed_missing_in_code
    blocking_missing_in_spec = missing_in_spec - allowed_missing_in_spec
    stale_allowances = (allowed_missing_in_code - missing_in_code) | (allowed_missing_in_spec - missing_in_spec)

    config_fixtures = config.get("fixtures", {})
    if not isinstance(config_fixtures, Mapping):
        raise ConfigError("fixtures must be an object")
    fixtures: dict[str, str] = {}
    for key, value in config_fixtures.items():
        name = str(key)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ConfigError(f"invalid fixture name: {name!r}")
        fixtures[name] = _fixture_segment(name, value)
    for name, value in (fixture_overrides or {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ConfigError(f"invalid fixture name: {name!r}")
        fixtures[name] = _fixture_segment(name, value)
    timeout = _timeout_seconds(config.get("timeout", 5))

    if live_enabled and not live_base_url:
        raise ConfigError("--live requires --live-base-url")
    if not live_enabled and live_base_url:
        raise ConfigError("--live-base-url is inert without explicit --live")

    live_results: list[dict[str, Any]] = []
    normalized_live_base: str | None = None
    if live_enabled:
        normalized_live_base = validate_live_base_url(str(live_base_url))
        probe_openapi = config.get("live_probe_openapi_reads", True)
        if not isinstance(probe_openapi, bool):
            raise ConfigError("live_probe_openapi_reads must be true or false")
        live_operations = set(canaries)
        if probe_openapi:
            live_operations.update(op for op in spec_operations if op.method in SAFE_LIVE_METHODS)
        live_results = probe_live(live_operations, normalized_live_base, fixtures, timeout, requester)

    live_unavailable = [result for result in live_results if not result["available"]]
    exit_code = 0
    if blocking_missing_in_code:
        exit_code |= MISSING_IN_CODE
    if blocking_missing_in_spec:
        exit_code |= MISSING_IN_SPEC
    if live_unavailable:
        exit_code |= LIVE_UNAVAILABLE
    if stale_allowances:
        exit_code |= STALE_ALLOWANCE

    relative_sources = [str(path.relative_to(repo_root)) for path in source_paths]
    report = {
        "allowed": {
            "missing_in_code": _operation_dicts(missing_in_code & allowed_missing_in_code),
            "missing_in_spec": _operation_dicts(missing_in_spec & allowed_missing_in_spec),
        },
        "blocking": {
            "live_unavailable": live_unavailable,
            "missing_in_code": _operation_dicts(blocking_missing_in_code),
            "missing_in_spec": _operation_dicts(blocking_missing_in_spec),
        },
        "drift": {
            "live_unavailable": live_unavailable,
            "missing_in_code": _operation_dicts(missing_in_code),
            "missing_in_spec": _operation_dicts(missing_in_spec),
        },
        "exit_code": exit_code,
        "inventory": {
            "application_operations": len(code_operations),
            "application_effective_operations": len(effective_code_operations),
            "application_sources": relative_sources,
            "canary_operations": len(canaries),
            "openapi": str(openapi_path.relative_to(repo_root)),
            "openapi_operations": len(spec_operations),
        },
        "live": {
            "base_url": normalized_live_base,
            "enabled": live_enabled,
            "results": live_results,
        },
        "stale_allowances": _operation_dicts(stale_allowances),
        "status": "pass" if exit_code == 0 else "fail",
    }
    return report


def format_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _operation_from_dict(value: Mapping[str, Any]) -> Operation:
    return Operation(str(value["method"]), str(value["path"]))


def format_text(report: Mapping[str, Any]) -> str:
    """Render a stable, human-readable report."""
    inventory = report["inventory"]
    live = report["live"]
    lines = [
        "BoTTube deployment drift sentinel",
        f"OpenAPI: {inventory['openapi']} ({inventory['openapi_operations']} operations)",
        f"Application: {inventory['application_operations']} declared, "
        f"{inventory['application_effective_operations']} effective operations from "
        + ", ".join(inventory["application_sources"]),
        f"Canaries: {inventory['canary_operations']} operations",
        "Live: " + (f"enabled ({live['base_url']}, HEAD only)" if live["enabled"] else "disabled"),
    ]

    allowed_code = {_operation_from_dict(item) for item in report["allowed"]["missing_in_code"]}
    allowed_spec = {_operation_from_dict(item) for item in report["allowed"]["missing_in_spec"]}
    for key, title, allowed in (
        ("missing_in_code", "Missing in code", allowed_code),
        ("missing_in_spec", "Missing in spec", allowed_spec),
    ):
        values = [_operation_from_dict(item) for item in report["drift"][key]]
        blocking = len(report["blocking"][key])
        lines.append(f"{title}: {len(values)} ({blocking} blocking)")
        for operation in values:
            marker = "known" if operation in allowed else "blocking"
            lines.append(f"  [{marker}] {operation.label()}")

    unavailable = report["drift"]["live_unavailable"]
    lines.append(f"Live unavailable: {len(unavailable)} ({len(unavailable)} blocking)")
    for result in unavailable:
        destination = result["request_path"] or result["path"]
        lines.append(
            f"  [blocking] {result['method']} {result['path']} -> HEAD {destination}: {result['reason']}"
        )

    stale = [_operation_from_dict(item) for item in report["stale_allowances"]]
    lines.append(f"Stale allowances: {len(stale)}")
    for operation in stale:
        lines.append(f"  [blocking] {operation.label()}")
    lines.append(f"Status: {str(report['status']).upper()}")
    lines.append(f"Exit code: {report['exit_code']}")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root (default: current directory)")
    parser.add_argument("--config", default="deployment-drift.json", help="JSON policy path relative to repo root")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="report output format")
    parser.add_argument("--fixture", action="append", default=[], metavar="NAME=VALUE", help="override a path fixture")
    parser.add_argument("--live", action="store_true", help="explicitly enable credential-free HEAD probes")
    parser.add_argument("--live-base-url", help="base URL to probe; requires --live")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repo_root = Path(args.repo_root).resolve()
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = repo_root / config_path
        config = load_config(config_path)
        report = build_report(
            repo_root,
            config,
            live_enabled=args.live,
            live_base_url=args.live_base_url,
            fixture_overrides=_parse_fixtures(args.fixture),
        )
    except ConfigError as exc:
        print(f"deployment-drift: configuration error: {exc}", file=sys.stderr)
        return CONFIG_ERROR

    output = format_json(report) if args.format == "json" else format_text(report)
    sys.stdout.write(output)
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
