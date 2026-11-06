import json
from pathlib import Path

import pytest
import yaml

from pipesmith.cli import main
from pipesmith.detect import DetectionError, detect
from pipesmith.generate import render

ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def pkg(deps=None, dev=None, engines=None):
    data = {"name": "x", "dependencies": deps or {}, "devDependencies": dev or {}}
    if engines:
        data["engines"] = {"node": engines}
    return json.dumps(data)


def test_node_express_is_webapp(tmp_path):
    write(tmp_path / "package.json", pkg({"express": "^4"}, engines=">=18"))
    d = detect(tmp_path)
    assert (d.stack, d.target, d.runtime_version, d.build_output) == ("node", "webapp", "18.x", "")


def test_node_functions(tmp_path):
    write(tmp_path / "package.json", pkg({"@azure/functions": "^4"}))
    assert detect(tmp_path).target == "functionapp"


def test_node_react_vite_is_static(tmp_path):
    write(tmp_path / "package.json", pkg({"react": "^18"}, {"vite": "^5"}))
    d = detect(tmp_path)
    assert (d.target, d.build_output, d.runtime_version) == ("staticwebapp", "dist", "20.x")


def test_cra_uses_build_folder(tmp_path):
    write(tmp_path / "package.json", pkg({"react": "^18", "react-scripts": "5"}))
    assert detect(tmp_path).build_output == "build"


def test_node_unknown_needs_target(tmp_path):
    write(tmp_path / "package.json", pkg({"chalk": "^5"}))
    with pytest.raises(DetectionError):
        detect(tmp_path)
    assert detect(tmp_path, target="storage").build_output == "dist"


def test_dotnet_api_vs_webapp(tmp_path):
    write(tmp_path / "src/Api/Api.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>')
    d = detect(tmp_path)
    assert (d.stack, d.target, d.working_directory, d.runtime_version) == ("dotnet", "apiapp", "src/Api", "8.0.x")
    (tmp_path / "src/Api/Pages").mkdir()
    assert detect(tmp_path).target == "webapp"


def test_dotnet_functions_and_blazor(tmp_path):
    write(tmp_path / "f/F.csproj", '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework><AzureFunctionsVersion>v4</AzureFunctionsVersion></PropertyGroup></Project>')
    assert detect(tmp_path).target == "functionapp"
    other = tmp_path / "b"
    write(other / "B.csproj", '<Project Sdk="Microsoft.NET.Sdk.BlazorWebAssembly"><PropertyGroup><TargetFramework>net9.0</TargetFramework></PropertyGroup></Project>')
    d = detect(other)
    assert (d.target, d.build_output, d.runtime_version) == ("staticwebapp", "wwwroot", "9.0.x")


def test_dotnet_prefers_non_test_project(tmp_path):
    write(tmp_path / "A.Tests/A.Tests.csproj", '<Project Sdk="Microsoft.NET.Sdk"></Project>')
    write(tmp_path / "A/A.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>')
    assert detect(tmp_path).working_directory == "A"


def test_skips_node_modules(tmp_path):
    write(tmp_path / "node_modules/x/package.json", pkg({"express": "4"}))
    with pytest.raises(DetectionError):
        detect(tmp_path)


def test_mixed_repo_at_same_level_needs_stack(tmp_path):
    write(tmp_path / "package.json", pkg({"express": "4"}))
    write(tmp_path / "A.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>')
    with pytest.raises(DetectionError):
        detect(tmp_path)
    assert detect(tmp_path, stack="node").stack == "node"


def test_generated_yaml_is_valid_and_complete(tmp_path):
    write(tmp_path / "package.json", pkg({"react": "18"}))
    doc = yaml.safe_load(render(detect(tmp_path), app_name="it's-app", service_connection="sc-prod"))
    params = doc["extends"]["parameters"]
    assert doc["extends"]["template"] == "pipeline.yml@templates"
    assert params["target"] == "staticwebapp" and params["buildOutput"] == "dist"
    assert params["appName"] == "it's-app"
    assert doc["resources"]["repositories"][0]["ref"].startswith("refs/tags/")


def test_cli_generate_and_no_overwrite(tmp_path, capsys):
    write(tmp_path / "package.json", pkg({"express": "4"}))
    args = ["generate", str(tmp_path), "--app-name", "app", "--service-connection", "sc"]
    assert main(args) == 0
    assert (tmp_path / "azure-pipelines.yml").exists()
    assert main(args) == 1
    assert main(args + ["--force"]) == 0


def test_examples_detect():
    assert detect(ROOT / "examples/node-demo").target == "webapp"
    assert detect(ROOT / "examples/dotnet-demo").target == "apiapp"


def test_templates_parse_and_wire_up():
    tdir = ROOT / "templates"
    for f in tdir.rglob("*.yml"):
        assert yaml.safe_load(f.read_text()) is not None, f
    pipeline = yaml.safe_load((tdir / "pipeline.yml").read_text())
    stages = [s["stage"] for s in pipeline["stages"]]
    assert stages == ["Security", "Build", "Deploy"]
    for stage in pipeline["stages"]:
        for job in stage["jobs"]:
            assert (tdir / job["template"]).exists()
