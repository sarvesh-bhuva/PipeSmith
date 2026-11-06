# Azure DevOps setup

One-time setup per Azure DevOps project.

## 1. Templates repository

Create a repo (for example `Platform/pipeline-templates`) and push the **contents** of
`templates/` to its root, so `pipeline.yml` sits at the top level. Tag releases
(`v1.0.0`, `v1.1.0`, ...) and have generated pipelines pin a tag.

## 2. Signing key

```bash
cosign generate-key-pair          # writes cosign.key and cosign.pub
```

- Upload `cosign.key` and `cosign.pub` under **Pipelines > Library > Secure files**.
- Create variable group `pipesmith` with secret variable `COSIGN_PASSWORD`.
- For Static Web Apps, also add secret `SWA_DEPLOYMENT_TOKEN`.
- Authorise the secure files and variable group for the pipelines that use them.

Never commit `cosign.key`. It is in `.gitignore`.

## 3. Service connection and environment

- Create an Azure Resource Manager service connection (workload identity federation preferred).
- Create an environment (default name `production`) and add approvals if needed.

## 4. Enforce the template (important)

On the environment **and** the service connection, add **Approvals and checks > Required template**
pointing at `pipeline.yml` in the templates repo. Without this, a pipeline could skip the
template and deploy without the security gates.

## 5. Generate a pipeline

```bash
pipesmith generate path/to/repo --app-name my-app --service-connection sc-prod \
  --templates-repo Platform/pipeline-templates --templates-ref refs/tags/v1.0.0
```

Commit `azure-pipelines.yml` through a pull request and create the pipeline from it.
