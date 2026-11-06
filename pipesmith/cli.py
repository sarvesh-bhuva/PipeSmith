"""Command-line interface: `pipesmith detect` and `pipesmith generate`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .detect import STACKS, TARGETS, DetectionError, detect
from .generate import render


def _add_detect_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", help="path to the repository")
    p.add_argument("--stack", choices=STACKS, help="override stack detection")
    p.add_argument("--target", choices=TARGETS, help="override deploy target detection")
    p.add_argument("--build-output", help="static build output folder (staticwebapp/storage)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipesmith", description=__doc__)
    parser.add_argument("--version", action="version", version=f"pipesmith {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("detect", help="show what PipeSmith detects in a repo")
    _add_detect_args(d)

    g = sub.add_parser("generate", help="write azure-pipelines.yml for a repo")
    _add_detect_args(g)
    g.add_argument("--app-name", required=True, help="App Service, Function App, Static Web App or storage account name")
    g.add_argument("--service-connection", required=True, help="Azure Resource Manager service connection name")
    g.add_argument("--templates-repo", default="Platform/pipeline-templates", help="<project>/<repo> holding the org templates")
    g.add_argument("--templates-ref", default="refs/tags/v1.0.0", help="pinned ref of the templates repo")
    g.add_argument("--environment", default="production", help="Azure DevOps environment for approvals")
    g.add_argument("--fail-on", choices=("high", "critical"), default="high", help="minimum dependency severity that fails the build")
    g.add_argument("--branch", default="main", help="branch that triggers and deploys")
    g.add_argument("--variable-group", default="pipesmith", help="variable group holding COSIGN_PASSWORD (and SWA_DEPLOYMENT_TOKEN)")
    g.add_argument("-o", "--output", help="output file (default: <path>/azure-pipelines.yml)")
    g.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    g.add_argument("--force", action="store_true", help="overwrite an existing pipeline file")

    args = parser.parse_args(argv)
    try:
        det = detect(args.path, stack=args.stack, target=args.target, build_output=args.build_output)
    except DetectionError as exc:
        print(f"pipesmith: {exc}", file=sys.stderr)
        return 2

    if args.command == "detect":
        print(json.dumps(det.to_dict(), indent=2))
        return 0

    yaml_text = render(det, app_name=args.app_name, service_connection=args.service_connection,
                       templates_repo=args.templates_repo, templates_ref=args.templates_ref,
                       environment=args.environment, fail_on=args.fail_on, branch=args.branch,
                       variable_group=args.variable_group)
    if args.stdout:
        sys.stdout.write(yaml_text)
        return 0
    out = Path(args.output) if args.output else Path(args.path) / "azure-pipelines.yml"
    if out.exists() and not args.force:
        print(f"pipesmith: {out} exists; use --force to overwrite", file=sys.stderr)
        return 1
    out.write_text(yaml_text, encoding="utf-8")
    print(f"wrote {out} ({det.stack} / {det.target})")
    return 0
