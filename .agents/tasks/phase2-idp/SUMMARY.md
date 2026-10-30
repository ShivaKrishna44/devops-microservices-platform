# Phase 2 summary: Developer-friendly-infra

Project folder: `c:\Devops\Repository\Developer-friendly-infra`

**Review verdict: APPROVED (from `review.json`). Nothing was run.** The approval is based on reading files only. The shell returned `Exit Code: -1` for the coder and the reviewer. No test, build, lint or syntax check has been executed. Git was not run, so no repository state or commit is claimed.

Outstanding minor findings from the review:

- `kube.METRICS_RESOURCES` still allows `nodes.metrics.k8s.io`, and no caller reads it. Drop it or document it.
- Nothing was run. Run the commands in section 3 first, starting with `backend/tests/test_deploy_api.py`.

## 1. What was built

All paths are under `c:\Devops\Repository\Developer-friendly-infra`. Every file was written and re-read. None was executed.

### Part A. Phase 1 gaps

- A1: `scripts/destroy.sh`. The orphan path now reads `DFI_ENVIRONMENT` (default `dev`, checked with `validate_env`). A plain `ENVIRONMENT` in the shell is ignored.
- A2: `backend/app/services/kube.py`. kubectl is now a strict grammar: `get <resource> [-n <ns> | -A | --all-namespaces]`. The allow-list has 8 resource names (pods, namespaces, deployments, replicasets, statefulsets, persistentvolumeclaims, resourcequotas, events) plus 2 metrics names. Secrets are not allowed. The `get` verb is the only verb.
- A3: `backend/tests/test_kube.py`. Guard tests for accepted and rejected shapes.
- A4: `RUNBOOK.md`, `README.md`. Steps reordered, Python 3.12 or 3.13 recommended, cost figures labelled as estimates, note on the untagged state bucket.
- A5: `RUNBOOK.md`, `scripts/argocd-token.sh` (comment only), `backend/README.md`. Steps for a read-only ArgoCD account and a deploy account.
- A6: `VERSIONS.md`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `.gitignore`. Version table, header notes, and `.state/` ignored. No lockfile was created.

### Part B. Diagnose engine

- Config: `config/checks.yaml`, `backend/app/settings.py`, `backend/requirements.txt` (PyYAML range).
- Package `backend/app/diagnose/`: `__init__.py`, `models.py`, `quantities.py`, `facts.py`, `checks_config.py`, `rules_common.py`, `rules_pod.py`, `rules_pod_extra.py`, `rules_workload.py`, `rules_custom.py`, `engine.py`, `collect.py`, `llm_summary.py`. This covers 15 deterministic rules. The LLM summary is off by default and cannot change a finding.
- `backend/app/services/argocd_client.py` (ArgoCD detail reads).
- `backend/app/routers/diagnose.py`, `backend/app/routers/deps.py`, `backend/app/main.py` (wiring).
- Tests: `backend/tests/diagnose_support.py`, `backend/tests/fixtures/diagnose/*` and `fixtures/README.md`, `test_diagnose_quantities.py`, `test_diagnose_facts.py`, `test_diagnose_checks_config.py`, `test_diagnose_rules.py`, `test_diagnose_engine.py`, `test_diagnose_api.py`.

### Part C. Confirm-gated deploy

- Config: `config/components.yaml`. It ships as `components: []` with a how-to note.
- Package `backend/app/deploy/`: `catalog.py`, `guardrails.py`, `evidence.py`, `audit.py`, `gate.py`, `executor.py`.
- `backend/app/services/argocd_client.py` (refresh and sync only), `backend/app/services/argocd.py` (message now points to the read-only account).
- `backend/app/routers/deploy.py`, `backend/app/routers/audit.py`, `backend/app/routers/deps.py`, `backend/app/main.py` (including the 422 audit handler).
- Tests: `backend/tests/conftest.py`, `test_deploy_catalog.py`, `test_deploy_guardrails.py`, `test_deploy_audit.py`, `test_deploy_gate.py`, `test_argocd_client.py`, `test_deploy_api.py`, `test_guard.py` (extended), `test_argocd.py` (message updated), `test_kube.py`.

How the gate works: a plan is bound to cluster, component, ArgoCD app and target revision. It carries a SHA-256 hash of the evidence and a TTL (`APPROVAL_TTL_MINUTES`, default 15). The user must type `DEPLOY <cluster>/<component>`. Production needs two distinct actors. Execute re-checks everything and re-reads the live app. A plan works once. If the audit line cannot be written, no action is taken.

### Part D. Frontend

- Under `frontend/src/`: `types.ts`, `api.ts`, `severity.ts`, `tone.ts`, `styles.css`.
- Components: `FindingsPanel.tsx`, `NamespaceDiagnose.tsx`, `findings/*`, `PodTable.tsx`, `ClusterDetail.tsx`, `DeployTab.tsx`, `DeployPlanView.tsx`, `DeployConfirm.tsx`, `AuditList.tsx`, `ArgoPanel.tsx`, `App.tsx`.
- Config: `frontend/vite.config.ts`, `frontend/tsconfig.app.json`.
- Tests: `FindingsPanel.test.tsx`, `severity.test.ts`, `DeployConfirm.test.tsx`, `fixtures-boundary.test.ts`, `test-fixtures/findings.sample.json`.

### Part E. Docs

- `README.md`, `RUNBOOK.md`, `VERSIONS.md`, `docs/diagnose-checks.md`, `docs/safety-model.md`, `backend/README.md`.

No `.tf` file was changed in Phase 2.

## 2. What read-only validation passed

None. The shell was down, so no validation was run in this environment. `verification.md` has no PASSED rows. Every check is UNVERIFIED. The grep and file-search tools also did not index the project, so their "no matches" results were not used as evidence. The only checks done were re-reads of files, which are not validation.

## 3. UNVERIFIED list

Run these in Git Bash from `c:\Devops\Repository\Developer-friendly-infra`. None of them touches a cloud account.

| Check | Command |
|-------|---------|
| Python test dependencies | `python -m pip install -r backend/requirements-dev.txt` |
| Python syntax | `python -m py_compile <file.py>` for one file, or `python -m compileall -q backend/app registry` for all |
| Deploy API tests (run first) | `cd backend && python -m pytest tests/test_deploy_api.py -q` |
| Kubectl guard tests | `cd backend && python -m pytest tests/test_kube.py tests/test_guard.py -q` |
| Diagnose tests | `cd backend && python -m pytest tests/test_diagnose_quantities.py tests/test_diagnose_facts.py tests/test_diagnose_checks_config.py tests/test_diagnose_rules.py tests/test_diagnose_engine.py tests/test_diagnose_api.py -q` |
| Whole backend suite | `cd backend && python -m pytest -q` |
| Registry tests | `python -m pytest registry/tests -q` |
| Shell syntax | `bash -n scripts/*.sh` |
| Terraform format | `cd terraform && terraform fmt -check -recursive` |
| Terraform validate | `cd terraform && terraform init -backend=false -input=false && terraform validate` |
| Frontend install | `cd frontend && npm install` |
| Frontend tests | `cd frontend && npm test` |
| Frontend build | `cd frontend && npm run build` |
| Everything | `bash scripts/verify-local.sh` |
| destroy.sh dry run | `ENVIRONMENT=production DRY_RUN=1 REGISTRY_PATH=/tmp/r.json TF_STATE_BUCKET=dummy bash scripts/destroy.sh ghost-one` (needs terraform, aws and kubectl on PATH; it may stop at the command check) |
| Tool versions | `terraform version`, `kubectl version --client` |
| Account | `aws sts get-caller-identity` (expect account 589389425618) |

Places most likely to fail on the first run: strict TypeScript options in `npm run build`, the `import.meta.glob` typing in `fixtures-boundary.test.ts`, the pydantic error type names in the 422 handler, YAML parse errors in the malformed-config test, and Windows file replace behavior in the plan store.

## 4. Git commands for you

Git could not be run here. Run these yourself:

```
cd c:\Devops\Repository\Developer-friendly-infra
git init
git add -A
git commit -m "Phase 2: diagnose engine, confirm-gated deploy, frontend, docs"
```

Run `git init` only if the folder is not already a repository. Check with `git status` first. If it is already a repository, skip `git init`.

Before you commit, generate the lockfiles yourself:

- `cd terraform && terraform init` creates `.terraform.lock.hcl`.
- `cd frontend && npm install` creates `package-lock.json`.

These two files were not created or invented here. Commit them once they exist. `.gitignore` does not ignore `.terraform.lock.hcl`. It does ignore `.state/`, which holds the audit log and plans.

## 5. Known limits

- Review verdict: APPROVED, based on reading only. It is not a test result.
- The two-actor rule for production is honor system when run locally. There is no authentication on the actor names.
- Nothing was verified against a live cluster or an AWS account. The ArgoCD refresh and sync REST shapes, the metrics resource names, and the RBAC lines in the RUNBOOK are written from documentation and memory, not seen working. Check them against the ArgoCD swagger page on a running server.
- The deploy path can only refresh and sync an ArgoCD app. Sync has prune off and no force. There is no kubectl write, rollback, delete or bulk action.
- The component catalog ships empty. Deploy does nothing until you add an app to `config/components.yaml`.
- AWS hourly cost figures were recalled, not checked against AWS pricing.
- An unexpected non-HTTP error inside the ArgoCD client after a plan is claimed leaves the plan in `EXECUTING` with a 500 and no result line. The plan cannot be reused, so it fails closed.
- The spec file `Prepare-now\K-Real-scenario-debug.md` was not found. `Self-study-before-interview\K8-Real-scenario-debug.md` was used instead.
