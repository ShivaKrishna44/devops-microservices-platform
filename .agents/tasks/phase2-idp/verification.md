# Phase 2 verification record

Project: `c:\Devops\Repository\Developer-friendly-infra`
Iteration: FIX (pass 2). `review.json` existed (verdict REVISE, 7 findings). Pass 1 implemented Parts A to E.
The fix pass is recorded in the next section. The rest of this file is the pass 1 record and still applies.

## Fix iteration 1: findings and what was done

The shell still returned `Exit Code: -1` with no output (`echo hi` probed again). Nothing was run. Everything
below is **written, UNVERIFIED**. The grep and file-search tools still do not index this folder, so files were opened
and re-read instead.

| # | Finding | Status | What changed |
|---|---------|--------|--------------|
| 1 | Unaudited 422 validation refusals (blocking) | fixed, UNVERIFIED | `main.py`: `RequestValidationError` handler. For `/api/deploy/plan` and `/api/deploy/execute` it calls `executor.audit_invalid_request`, then returns the standard 422 answer. HTTP status is unchanged. Reason code is `forbidden_field` (via `gr_no_forbidden_fields`) or `invalid_request`. Only names on the fixed `FORBIDDEN_FIELDS` list are logged, no values. Tests added in `tests/test_deploy_api.py` (forbidden field names audited with no value, unknown name not echoed, missing fields audited on both routes, read route writes no line, 422 survives a broken audit log) |
| 7 | `gr_no_forbidden_fields` was dead code | fixed, UNVERIFIED | It is now called from `audit_invalid_request`, so `forbidden_field` can occur. `run_plan_guardrails(payload=...)` is unchanged and still accepts a payload |
| 2 | Post-action audit failure shown as "Execute failed" | fixed, UNVERIFIED | `executor.execute`: `mark_consumed` and the `EXECUTE_RESULT` write are wrapped. On failure the answer is 200 with `record_warning: true` and a message that says the request WAS sent. The `EXECUTE_FAILED` path now also still answers 502 if its audit write fails. `types.ts` got an optional `record_warning`. The Deploy tab already shows `message`. Tests added: result-audit failure reported as sent, failed audit after an ArgoCD error still 502, normal success has `record_warning: false` |
| 4 | Phase 1 message pointed at the admin token | fixed, UNVERIFIED | `services/argocd.py` (not_configured and unauthorized messages) and `frontend/src/components/ArgoPanel.tsx` now point to RUNBOOK step 5 (read-only account). `tests/test_argocd.py::test_not_configured_without_token` was updated to match |
| 3 | Unused kubectl allow-list entries | fixed after the caller chose DROP, UNVERIFIED | Callers checked with the grep tool using relative include patterns (it works that way): `run_kubectl` is called only from `routers/pods.py` (pods), `routers/namespaces.py` (namespaces), `agent_tools.py` (namespaces, pods) and `diagnose/collect.py` (pods, events, replicasets, deployments, statefulsets, persistentvolumeclaims, resourcequotas, pods.metrics.k8s.io). No script, test or doc needs `services`, `endpoints`, `configmaps` or `nodes`. `kube.ALLOWED_RESOURCES` now has 8 names, with a code comment on why. Tests: `test_kube.py` (count 8, exact set, each dropped resource refused with and without `-n`, `-A`), `test_guard.py::test_allowed_resource_list_is_closed`. Docs: `backend/README.md`, `docs/safety-model.md`. `METRICS_RESOURCES` still lists `nodes.metrics.k8s.io`, which nothing calls. That was outside the decision, so it was left as is and can be dropped the same way |
| 5 | Placeholder catalog entries | fixed after the caller chose EMPTY, UNVERIFIED | `config/components.yaml` is now `components: []` with a how-to-add note and a commented example. `DeployTab.tsx` shows an empty state with the instructions. `RUNBOOK.md` step 6 has the how-to, and the `example-*` names were removed from steps 5d and 9. `README.md` wording updated. Tests: `test_deploy_catalog.py` shipped file is valid and empty, and the commented example parses when uncommented |
| 1b | 422 audit coverage (caller asked for a test per shape) | tests added, UNVERIFIED | `test_deploy_api.py`: plan bodies (force, prune, extra field, empty component, wrong type, too-long actor), execute bodies (force, prune, dryRun, extra field, empty, too-long and non-string confirmation, missing plan id, too-long second actor), non-JSON bodies on both routes. Each asserts exactly one new refusal line, the reason code, no value echoed, no ArgoCD write, and that the plan stays PLANNED. A wrong phrase with a valid shape is a 409 and was already audited |
| 6 | Nothing was run | still true | Commands are in the table below |

Docs updated: `docs/safety-model.md` (layer 1 resource list, layer 7 bullet and layer 9 write order), `backend/README.md`
(errors table, execute response, resource list), `RUNBOOK.md` (steps 5d, 6, 9 and a troubleshooting row for the
"request WAS sent" message), `README.md` (catalog wording).

Also changed after the caller's decisions: `backend/app/services/kube.py`, `backend/tests/test_kube.py`,
`backend/tests/test_guard.py`, `backend/tests/test_deploy_catalog.py`, `config/components.yaml`,
`frontend/src/components/DeployTab.tsx`. The shell was probed again earlier in this pass and returned `Exit Code: -1`.
Nothing was run.

Files changed in this pass: `backend/app/main.py`, `backend/app/deploy/executor.py`, `backend/app/services/argocd.py`,
`backend/tests/test_deploy_api.py`, `backend/tests/test_argocd.py`, `frontend/src/types.ts`,
`frontend/src/components/ArgoPanel.tsx`, `docs/safety-model.md`, `backend/README.md`, `RUNBOOK.md`.

Weak spots to watch on the first real run: the `RequestValidationError` error type name (`extra_forbidden` on pydantic 2,
`value_error.extra` on pydantic 1 are both handled); `pytest tests/test_deploy_api.py` is the first file to run.

## What actually ran

**Nothing was executed.** The shell tool returned `Exit Code: -1` with empty output. Two probes were tried:
`echo hi` and `ls <phase2-idp folder>`. Both returned `Exit Code: -1` and no output. So no `terraform`,
`python`, `pytest`, `npm` or `bash -n` command ran. All work was done with file read, write, search and
string-replace tools.

Nothing in this file is marked PASSED, because nothing was run and seen to pass.

Other facts:

- The grep and file-search tools did not reliably index `Developer-friendly-infra` (a search for a string I had just
  written, `DFI_ENVIRONMENT`, returned no matches). Their "no matches" results were **not** used as evidence. Checks
  below marked "re-read" were done by opening the files.
- Git was not run. No repository, branch or commit is claimed. No push was made.
- No `terraform apply/destroy`, `aws`, `kubectl` or `helm` command was run, read-only or otherwise.
- Constraint 9: `backend/tests/test_kube.py` was written on the **first** attempt and was **not refused**. The fallback name
  `test_kubectl_guard.py` was not needed.
- The spec `Prepare-now\K-Real-scenario-debug.md` was not found. `Self-study-before-interview\K8-Real-scenario-debug.md`
  was used (it has the same 15 sections). `eks-cluster-argocd\...\argocd.sh` was not read; the ArgoCD flow came from this
  project's own `provision.sh` and `common.sh`.

## Checks (all UNVERIFIED)

Run these from `c:\Devops\Repository\Developer-friendly-infra` in Git Bash. They cost nothing and touch no cloud.

| Check | Exact command | Status |
|-------|---------------|--------|
| Install Python test deps | `python -m pip install -r backend/requirements-dev.txt` | UNVERIFIED (shell down) |
| Python syntax | `python -m compileall -q backend/app registry` | UNVERIFIED (shell down) |
| Backend tests (whole suite) | `cd backend && python -m pytest -q` | UNVERIFIED (shell down) |
| Kubectl guard tests only | `cd backend && python -m pytest tests/test_kube.py tests/test_guard.py -q` | UNVERIFIED (shell down) |
| Diagnose tests only | `cd backend && python -m pytest tests/test_diagnose_quantities.py tests/test_diagnose_facts.py tests/test_diagnose_checks_config.py tests/test_diagnose_rules.py tests/test_diagnose_engine.py tests/test_diagnose_api.py -q` | UNVERIFIED (shell down) |
| Deploy tests only | `cd backend && python -m pytest tests/test_deploy_catalog.py tests/test_deploy_guardrails.py tests/test_deploy_audit.py tests/test_deploy_gate.py tests/test_argocd_client.py tests/test_deploy_api.py -q` | UNVERIFIED (shell down) |
| Registry tests | `python -m pytest registry/tests -q` | UNVERIFIED (shell down) |
| Shell syntax | `bash -n scripts/*.sh` | UNVERIFIED (shell down) |
| Terraform format | `cd terraform && terraform fmt -check -recursive` | UNVERIFIED (shell down). No `.tf` file was changed in Phase 2 |
| Terraform validate | `cd terraform && terraform init -backend=false -input=false && terraform validate` | UNVERIFIED (shell down). No `.tf` file was changed in Phase 2 |
| Frontend install, tests, build | `cd frontend && npm install && npm test && npm run build` | UNVERIFIED (shell down) |
| Everything | `bash scripts/verify-local.sh` | UNVERIFIED (shell down) |
| `A1` dry run | `ENVIRONMENT=production DRY_RUN=1 REGISTRY_PATH=/tmp/r.json TF_STATE_BUCKET=dummy bash scripts/destroy.sh ghost-one` (needs terraform, aws, kubectl on PATH; may stop at `require_cmd`) | UNVERIFIED (shell down) |
| Account | `aws sts get-caller-identity` (expect account 589389425618) | UNVERIFIED (AWS access not available) |
| Terraform version | `terraform version` (expect 1.11 or newer) | UNVERIFIED |
| Kubectl version | `kubectl version --client` | UNVERIFIED |

Expected weak spots if something fails on the first run (written without being run):

- `npm run build`: strict TypeScript options (`noUnusedLocals`, `verbatimModuleSyntax`), the JSON import in the vitest
  fixture (`resolveJsonModule` was added to `tsconfig.app.json`), and `import.meta.glob` typing in
  `src/fixtures-boundary.test.ts`.
- `pytest`: exact YAML parse error behavior for `checks_malformed_syntax.yaml`, and Windows behavior of writing the plan
  store (`os.replace`) and audit log.
- Pydantic: `str | None` annotations in `routers/deploy.py` under `from __future__ import annotations` (fine on 3.10+).

## Static checks done by re-reading (not validation)

| Item | What was re-read | Result of the reading |
|------|------------------|-----------------------|
| A1 | `scripts/destroy.sh` lines 1 to 70 | `ENVIRONMENT` replaced by `DFI_ENVIRONMENT` (default `dev`, validated with `validate_env`) at the orphan default and at `export_tf_vars`. Header comment explains it. No `${ENVIRONMENT` remains in the part read. The typed confirmation, account guard and cleanup were not touched |
| A2 | `kube.py` against every caller: `routers/pods.py` (`get pods -n <ns>`), `routers/namespaces.py` (`get namespaces`), `agent_tools.py` (same two shapes), `diagnose/collect.py` (`get <resource> -n <ns>` for 7 resources and `get pods.metrics.k8s.io -n <ns>`) | All fit the grammar `get <resource> [-n <ns> \| -A \| --all-namespaces]` |
| A3 | `tests/test_kube.py` against the grammar, case by case | Every rejected case hits one of: bad verb, resource not in the sets, extra or repeated tokens, namespace regex, or non-str argument. Not executed |
| Landmines | `tests/test_guard.py` rules against all new `app/` code | Known string constants in new code are not write verbs. No shell flag text. Imports of `httpx` only in the two ArgoCD modules. `subprocess` only in `kube.py`. No top-level `crewai` import. Done by reading, not by search tool |
| Text scans | Deploy package and `argocd_client.py` for the words `kubectl`, `subprocess` and for write HTTP method calls | The files were written to avoid these words. No working search tool confirmed it afterwards. `test_argocd_client.py` repeats the scan, so run it first if a test fails here |
| Docs | Link targets in `README.md` | `RUNBOOK.md`, `VERSIONS.md`, `docs/diagnose-checks.md`, `docs/safety-model.md` exist |

## Backlog items

Status key: `written, unverified` means the file exists and was re-read, but nothing was run.

| Id | What | Files | Status |
|----|------|-------|--------|
| A1 | `DFI_ENVIRONMENT` in `destroy.sh` | `scripts/destroy.sh` | written, unverified |
| A2 | Strict kubectl grammar and allow-list (12 names in pass 1, cut to 8 in the fix pass, plus 2 metrics names, see decision D2) | `backend/app/services/kube.py` | written, unverified |
| A3 | Guard tests | `backend/tests/test_kube.py` | written, unverified |
| A4 | RUNBOOK reorder, Python 3.12/3.13, cost-estimate note, state bucket tag note | `RUNBOOK.md`, `README.md` | written, unverified. AWS pricing numbers are recalled, not checked |
| A5 | Read-only and deploy ArgoCD account steps, `argocd-token.sh` comment, backend README token notes | `RUNBOOK.md`, `scripts/argocd-token.sh`, `backend/README.md` | written, unverified. RBAC lines and `can-i` results are expected, not seen. Not checked against ArgoCD docs because no web search was used |
| A6 | `VERSIONS.md`, requirements header notes, `.state/` in `.gitignore` | `VERSIONS.md`, `backend/requirements*.txt`, `.gitignore` | written, unverified. No lockfile was created. `.gitignore` does not ignore `.terraform.lock.hcl` |
| B1 | Package scaffold, settings, PyYAML range, `config/checks.yaml` | `backend/app/diagnose/__init__.py`, `backend/app/settings.py`, `backend/requirements.txt`, `config/checks.yaml` | written, unverified |
| B2 | Models, quantities, facts | `diagnose/models.py`, `quantities.py`, `facts.py` | written, unverified |
| B3 | Strict `checks.yaml` loader | `diagnose/checks_config.py` | written, unverified |
| B4 | Rules 1, 5, 9, 10, 12 | `diagnose/rules_pod.py` | written, unverified |
| B5 | Rules 4, 6, 8, 14, 15 | `diagnose/rules_pod_extra.py` | written, unverified |
| B6 | Rules 2, 3, 7, 11, 13 | `diagnose/rules_workload.py`, `rules_custom.py` | written, unverified |
| B7 | Engine, collector, optional LLM summary, ArgoCD detail reader | `diagnose/engine.py`, `collect.py`, `llm_summary.py`, `services/argocd_client.py`, `diagnose/rules_common.py` | written, unverified |
| B8 | Diagnose router and wiring | `routers/diagnose.py`, `routers/deps.py`, `main.py` | written, unverified |
| T1 | Fixtures | `tests/fixtures/diagnose/*.json`, `*.yaml`, `tests/fixtures/README.md`, `tests/diagnose_support.py` | written, unverified |
| T2 | Quantities, facts, loader tests | `tests/test_diagnose_quantities.py`, `test_diagnose_facts.py`, `test_diagnose_checks_config.py` | written, unverified |
| T3 | Rule tests per scenario | `tests/test_diagnose_rules.py` | written, unverified |
| T4 | Engine and API tests | `tests/test_diagnose_engine.py`, `test_diagnose_api.py` | written, unverified |
| C1 | Settings, catalog, `components.yaml` | `deploy/catalog.py`, `config/components.yaml` | written, unverified |
| C2 | ArgoCD client write side, separate tokens, transport dependency | `services/argocd_client.py`, `routers/deps.py` | written, unverified. REST shapes not seen working |
| C3 | Audit log and endpoint | `deploy/audit.py`, `routers/audit.py` | written, unverified |
| C4 | Deterministic guardrails | `deploy/guardrails.py` | written, unverified |
| C5 | Evidence and approval gate | `deploy/evidence.py`, `deploy/gate.py` | written, unverified |
| C6 | Executor, deploy router, wiring | `deploy/executor.py`, `routers/deploy.py`, `main.py` | written, unverified |
| CT0 | Test isolation | `tests/conftest.py` | written, unverified |
| CT1 | Catalog and guardrail tests | `tests/test_deploy_catalog.py`, `test_deploy_guardrails.py` | written, unverified |
| CT2 | Audit and gate tests | `tests/test_deploy_audit.py`, `test_deploy_gate.py` | written, unverified |
| CT3 | ArgoCD client tests (MockTransport, test only) | `tests/test_argocd_client.py` | written, unverified |
| CT4 | End-to-end gate tests | `tests/test_deploy_api.py` | written, unverified |
| CT5 | Extended static guard tests | `tests/test_guard.py` (appended; no existing test changed) | written, unverified |
| D1 | Types, API, severity, styles, vitest include, `resolveJsonModule` | `frontend/src/types.ts`, `api.ts`, `severity.ts`, `tone.ts`, `styles.css`, `vite.config.ts`, `tsconfig.app.json` | written, unverified |
| D2 | Findings panel and namespace summary | `components/FindingsPanel.tsx`, `NamespaceDiagnose.tsx`, `components/findings/*` | written, unverified |
| D3 | Diagnose button, tabs, panel wiring | `components/PodTable.tsx`, `ClusterDetail.tsx` | written, unverified. Not seen in a browser |
| D4 | Deploy tab: list and plan view | `components/DeployTab.tsx`, `DeployPlanView.tsx` | written, unverified. Not seen in a browser |
| D5 | Deploy tab: confirmation, result, audit list, header text | `components/DeployConfirm.tsx`, `AuditList.tsx`, `App.tsx` | written, unverified. Not seen in a browser |
| D6 | Vitest tests | `FindingsPanel.test.tsx`, `severity.test.ts`, `DeployConfirm.test.tsx`, `fixtures-boundary.test.ts`, `src/test-fixtures/findings.sample.json` | written, unverified |
| E1 | README | `README.md` | written (status table says `not run`) |
| E2 | Diagnose docs | `docs/diagnose-checks.md` | written, re-read against the rules |
| E3 | Safety model | `docs/safety-model.md` | written, re-read against `gate.py` and `guardrails.py` |
| E4 | RUNBOOK Phase 2 steps | `RUNBOOK.md` | written, unverified |

## Phase 1 gap ledger

| # | Gap | Final status |
|---|-----|--------------|
| G1 | `test_kube.py` never written | written, unverified |
| G2 | ArgoCD token is admin-scoped | written, unverified (docs and comment; no live check) |
| G3 | `destroy.sh` inherits `ENVIRONMENT` | written, unverified |
| G4 | kubectl token regex allows commas | written, unverified |
| G5 | No lockfiles | not done on purpose: generated by `terraform init` and `npm install`; stated in `VERSIONS.md` |
| G6 | RUNBOOK ordering and Python 3.14 claim | written, unverified |
| G7 | State bucket untagged | written, unverified (documented, optional user command) |
| G8 | Hourly cost figures recalled, not checked | not done: still unchecked; labelled as estimates |
| G9 | Nothing in Phase 1 was ever executed | not done: still true |

## Command block for the user

```
cd /c/Devops/Repository/Developer-friendly-infra
python -m pip install -r backend/requirements-dev.txt
python -m compileall -q backend/app registry
(cd backend && python -m pytest -q)
python -m pytest registry/tests -q
bash -n scripts/*.sh
(cd terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate)
(cd frontend && npm install && npm test && npm run build)
bash scripts/verify-local.sh
aws sts get-caller-identity
terraform version
kubectl version --client
```
