# PipeSmith

**Secure-by-default CI/CD pipelines, generated from a repository's tech stack.**

Most pipelines are copied from an old project. Secret scanning, SAST, dependency checks and
artifact signing get added late, inconsistently, or never. PipeSmith inspects a repository,
detects its stack and deployment target, and generates an Azure DevOps pipeline that
**extends a versioned org template** where those gates are always on.

Change a control once in the template repo, tag a release, and every pipeline that pins it
gets the change.

## What every generated pipeline does

| Stage | Gate | Tool | Fails when |
|---|---|---|---|
| Security | Secret scanning (source + git history) | Gitleaks | Any secret found |
| Security | SAST | Semgrep (`p/default`) | ERROR-severity finding |
| Security | Dependency scan | `npm audit` / `dotnet list package --vulnerable` | High or critical (configurable) |
| Build | Build, test, package | npm / dotnet | Build or tests fail |
| Build | SBOM | Syft (SPDX JSON) | — |
| Build | Signing | Cosign (`sign-blob`) | Package or SBOM unsigned |
| Deploy | Signature verification | Cosign (`verify-blob`) | Signature missing or invalid |
| Deploy | Deploy | Azure DevOps tasks | Only from the deploy branch |

Tool versions are pinned in [`templates/versions.yml`](templates/versions.yml).

## Supported in v0.1

| Stack | Detected from | Targets |
|---|---|---|
| .NET | `*.csproj` (`Sdk.Web`, Functions, Blazor WebAssembly), `TargetFramework` | App Service (web/API), Function App, Static Web App, Storage static website |
| Node.js | `package.json` (server frameworks, `@azure/functions`, `host.json`, frontend frameworks), `engines.node` | App Service, Function App, Static Web App, Storage static website |

Storage static website is never auto-detected (it looks identical to a Static Web App); use `--target storage`.

## Quick start

```bash
pip install git+https://github.com/<you>/pipesmith.git

pipesmith detect path/to/repo
pipesmith generate path/to/repo --app-name my-app --service-connection sc-prod
```

`detect` prints what was found and why:

```json
{
  "stack": "node",
  "target": "webapp",
  "working_directory": ".",
  "runtime_version": "20.x",
  "build_output": "",
  "evidence": ["found package.json", "node engine 20.x", "server framework: express"]
}
```

`generate` writes an `azure-pipelines.yml` like this:

```yaml
resources:
  repositories:
    - repository: templates
      type: git
      name: Platform/pipeline-templates
      ref: refs/tags/v1.0.0

extends:
  template: pipeline.yml@templates
  parameters:
    stack: node
    target: webapp
    runtimeVersion: '20.x'
    appName: 'my-app'
    azureSubscription: 'sc-prod'
    failOnSeverity: high
    extraBuildSteps: []
```

Overrides: `--stack`, `--target`, `--build-output`, `--fail-on critical`, `--branch`,
`--environment`, `--templates-repo`, `--templates-ref`. Run `pipesmith generate -h` for all options.

## How the gates stay on

- Application pipelines contain only parameters; the stages live in the template repo.
- Teams can add steps through `extraBuildSteps`. Those run after the security stage and before
  packaging, so they cannot skip a gate.
- Add a **Required template** check on environments and service connections so a pipeline that
  does not extend `pipeline.yml` cannot deploy. See [docs/azure-devops-setup.md](docs/azure-devops-setup.md).

## Repository layout

```
pipesmith/        CLI: stack/target detection and pipeline generation
templates/        Org templates; push the contents to your Azure DevOps templates repo
  pipeline.yml      Entry template (Security -> Build -> Deploy)
  versions.yml      Pinned tool versions
  jobs/ steps/      Security, build, SBOM/sign and deploy pieces
examples/         Demo apps that fail the gates on purpose
docs/             Azure DevOps setup
tests/            pytest suite
```

## Demo

The apps in `examples/` pin vulnerable dependencies (lodash 4.17.20, Newtonsoft.Json 12.0.1)
so the dependency gate fails. To show the secret gate failing, run
`examples/plant-fake-secret.sh` to generate a random fake key, then commit it to a throwaway
branch in your Azure DevOps demo project. Nothing secret-shaped is committed to this repo.

## Roadmap

- Open the generated pipeline as a pull request automatically
- More stacks (Python, Java) and targets (containers to AKS / Container Apps)
- GitHub Actions and GitLab CI emitters
- Checksum verification for downloaded scanner binaries
- SARIF publishing to Azure DevOps Advanced Security

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## License

MIT. See [LICENSE](LICENSE).
