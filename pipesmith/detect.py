"""Detect a repository's stack, deploy target and runtime version."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

STACKS = ("dotnet", "node")
TARGETS = ("webapp", "apiapp", "functionapp", "staticwebapp", "storage")
STATIC_TARGETS = ("staticwebapp", "storage")

SKIP_DIRS = {"node_modules", ".git", "bin", "obj", "dist", "build", ".venv", "venv", "coverage"}
MAX_DEPTH = 3

NODE_SERVER_DEPS = ("express", "fastify", "koa", "@nestjs/core", "@hapi/hapi", "next", "nuxt", "restify")
NODE_STATIC_DEPS = ("react", "vue", "svelte", "@angular/core", "vite", "preact", "solid-js")

DEFAULT_NODE_VERSION = "20.x"
DEFAULT_DOTNET_VERSION = "8.0.x"


class DetectionError(Exception):
    """Raised when a repository cannot be mapped to a supported stack or target."""


@dataclass
class Detection:
    stack: str
    target: str
    working_directory: str
    runtime_version: str
    build_output: str = ""
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _find(root: Path, pattern: str) -> List[Path]:
    found = []
    for path in root.rglob(pattern):
        rel = path.relative_to(root)
        if len(rel.parts) > MAX_DEPTH or any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        found.append(path)
    return sorted(found, key=lambda p: (len(p.relative_to(root).parts), str(p)))


def _rel_dir(root: Path, path: Path) -> str:
    rel = path.parent.relative_to(root).as_posix()
    return rel if rel not in ("", ".") else "."


def _detect_dotnet(root: Path, projects: List[Path]) -> Detection:
    candidates = [p for p in projects if not re.search(r"test", p.stem, re.I)] or projects
    proj = candidates[0]
    text = proj.read_text(encoding="utf-8", errors="ignore")
    evidence = [f"found {proj.relative_to(root).as_posix()}"]

    tfm = re.search(r"<TargetFrameworks?>\s*net(\d+\.\d+)", text)
    version = f"{tfm.group(1)}.x" if tfm else DEFAULT_DOTNET_VERSION
    evidence.append(f"target framework net{tfm.group(1)}" if tfm else "no TargetFramework, defaulting to 8.0")

    build_output = ""
    if "<AzureFunctionsVersion>" in text or "Microsoft.Azure.Functions.Worker" in text or "Microsoft.NET.Sdk.Functions" in text:
        target = "functionapp"
        evidence.append("Azure Functions SDK or worker reference")
    elif "Microsoft.NET.Sdk.BlazorWebAssembly" in text:
        target = "staticwebapp"
        build_output = "wwwroot"
        evidence.append("Blazor WebAssembly SDK")
    elif "Microsoft.NET.Sdk.Web" in text:
        proj_dir = proj.parent
        has_ui = any((proj_dir / d).exists() for d in ("wwwroot", "Views", "Pages", "Components"))
        target = "webapp" if has_ui else "apiapp"
        evidence.append("Web SDK with UI folders" if has_ui else "Web SDK without UI folders")
    else:
        raise DetectionError(f"{proj.name} is not a web, Functions or Blazor WebAssembly project")

    return Detection("dotnet", target, _rel_dir(root, proj), version, build_output, evidence)


def _node_version(pkg: dict) -> str:
    engines = (pkg.get("engines") or {}).get("node", "")
    match = re.search(r"(\d+)", engines)
    return f"{match.group(1)}.x" if match else DEFAULT_NODE_VERSION


def _detect_node(root: Path, manifest: Path, target_override: Optional[str] = None) -> Detection:
    try:
        pkg = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DetectionError(f"cannot parse {manifest}: {exc}") from exc

    deps = dict(pkg.get("dependencies") or {})
    all_deps = {**deps, **(pkg.get("devDependencies") or {})}
    pkg_dir = manifest.parent
    evidence = [f"found {manifest.relative_to(root).as_posix()}"]
    version = _node_version(pkg)
    evidence.append(f"node engine {version}" if (pkg.get("engines") or {}).get("node") else "no engines.node, defaulting to 20")

    build_output = ""
    if (pkg_dir / "host.json").exists() or "@azure/functions" in all_deps:
        target = "functionapp"
        evidence.append("host.json or @azure/functions")
    elif (pkg_dir / "staticwebapp.config.json").exists():
        target = "staticwebapp"
        build_output = "build" if "react-scripts" in all_deps else "dist"
        evidence.append("staticwebapp.config.json")
    elif any(d in deps for d in NODE_SERVER_DEPS):
        target = "webapp"
        evidence.append("server framework: " + ", ".join(d for d in NODE_SERVER_DEPS if d in deps))
    elif any(d in all_deps for d in NODE_STATIC_DEPS):
        target = "staticwebapp"
        build_output = "build" if "react-scripts" in all_deps else "dist"
        evidence.append("frontend framework: " + ", ".join(d for d in NODE_STATIC_DEPS if d in all_deps))
    elif target_override:
        target = target_override
        evidence.append("no framework recognised; using --target")
    else:
        raise DetectionError("package.json found but no server, Functions or frontend framework recognised; pass --target")

    return Detection("node", target, _rel_dir(root, manifest), version, build_output, evidence)


def detect(path: str | Path, stack: Optional[str] = None, target: Optional[str] = None,
           build_output: Optional[str] = None) -> Detection:
    root = Path(path).resolve()
    if not root.is_dir():
        raise DetectionError(f"{root} is not a directory")
    if stack and stack not in STACKS:
        raise DetectionError(f"unsupported stack '{stack}', expected one of {', '.join(STACKS)}")
    if target and target not in TARGETS:
        raise DetectionError(f"unsupported target '{target}', expected one of {', '.join(TARGETS)}")

    projects = _find(root, "*.csproj")
    manifests = _find(root, "package.json")

    if stack is None:
        if projects and manifests:
            depth = lambda p: len(p.relative_to(root).parts)
            if depth(projects[0]) == depth(manifests[0]):
                raise DetectionError("both .NET and Node projects at the same level; pass --stack")
            stack = "dotnet" if depth(projects[0]) < depth(manifests[0]) else "node"
        elif projects:
            stack = "dotnet"
        elif manifests:
            stack = "node"
        else:
            raise DetectionError("no *.csproj or package.json found within 3 levels")

    if stack == "dotnet":
        if not projects:
            raise DetectionError("--stack dotnet but no *.csproj found")
        result = _detect_dotnet(root, projects)
    else:
        if not manifests:
            raise DetectionError("--stack node but no package.json found")
        result = _detect_node(root, manifests[0], target)

    if target and target != result.target:
        result.evidence.append(f"target overridden: {result.target} -> {target}")
        result.target = target
    if result.target in STATIC_TARGETS and not result.build_output:
        result.build_output = "wwwroot" if result.stack == "dotnet" else "dist"
    if result.target not in STATIC_TARGETS:
        result.build_output = ""
    if build_output:
        result.build_output = build_output
    return result
