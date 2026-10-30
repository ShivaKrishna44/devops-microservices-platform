# Phase 2 IDP fix pass: audited validation refusals, honest post-action audit, least-privilege kubectl list

This pass closes the seven findings from the previous REVISE on Developer-friendly-infra. A `RequestValidationError` handler in `main.py` now writes a refusal audit line for the two deploy POST routes. `executor.execute` reports a failed result-audit write as "request WAS sent" instead of a bare 500. The kubectl allow-list dropped to 8 names. The Phase 1 ArgoCD message points at the read-only account. `config/components.yaml` ships as `components: []`. The earlier read of the diagnose engine, guardrails, gate, frontend and docs is unchanged by this pass and still stands.

Watch for: (1) nothing was executed by the coder or by this review, so every test, the TypeScript build and the two ArgoCD REST shapes are unproven (disclosed, `verification.md` marks all of it UNVERIFIED); (2) `METRICS_RESOURCES` still lists `nodes.metrics.k8s.io`, which no caller reads (confirmed, minor); (3) the 422 audit relies on pydantic error type names `extra_forbidden` or `value_error.extra` (likely correct, first `pytest tests/test_deploy_api.py` run will show).

**Verdict**: APPROVED

## High-level view

Refusals are now audited at every layer that can refuse. Schema rejections (`force`, `prune`, `dryRun`, any extra field, missing or oversized fields, non-JSON bodies) go through the new handler and write `PLAN_REFUSED` or `EXECUTE_REFUSED` with reason `forbidden_field` or `invalid_request`. Only names on the fixed `FORBIDDEN_FIELDS` list are logged, never values. `gr_no_forbidden_fields` is called from that path, so it is no longer dead code.

The execute path keeps its order: plan lookup, status, tamper hash, TTL, guardrails against the current registry and catalog, phrase, actors, deploy token present, live re-read, evidence hash and target-field comparison, intent audit (fail closed), single-use claim, one ArgoCD call. After the call, failures to record the result are caught and surfaced with `record_warning: true`, and the plan stays consumed so it cannot be replayed.

The kubectl wrapper is a strict grammar over 8 resource names plus 2 metrics names, with `fullmatch` on every pattern and no Secrets. The catalog ships empty, so the Deploy tab shows an explicit empty state and no invented app exists in runtime data.

<details>
<summary>Issues (2)</summary>

1. **Unused metrics resource** — `kube.METRICS_RESOURCES` still allows `nodes.metrics.k8s.io` and no caller reads it. Drop it, or leave it and note it in `docs/safety-model.md`.
2. **Nothing run** — run the command block at the end of `verification.md` before relying on any result. First file to run: `tests/test_deploy_api.py`.

</details>

<details>
<summary>Details</summary>

### Validation-refusal audit handler

`audit_invalid_request` swallows `AuditError`, so a broken audit disk still returns the standard 422. That is acceptable here because the request was refused and nothing was sent. It differs from the plan and execute paths, where an audit failure stops the action. The handler is keyed on the exact paths `/api/deploy/plan` and `/api/deploy/execute`, so read routes write no line, and `test_a_validation_error_on_a_read_route_writes_no_audit_line` covers that. Each of the nine parametrized execute shapes and six plan shapes asserts exactly one new line, the reason code, no echoed value and an unconsumed plan.

### Result-audit failure after a sent request

If `mark_consumed` or the `EXECUTE_RESULT` write fails after ArgoCD accepted the call, the answer is 200 with `record_warning: true` and wording that the request WAS sent. The intent line remains the only record, as the docs say. A failure after an ArgoCD error is swallowed and the 502 is still returned. One residual path: an unexpected non-`httpx.HTTPError` exception inside the ArgoCD client after `claim_plan` would leave the plan in `EXECUTING` with a 500 and no result line. The plan cannot be replayed in that state, so it fails closed (possible, low risk).

### Safety properties re-read against the requirements

The deploy gate binds cluster, component, ArgoCD app and target revision (plan record plus evidence), a SHA-256 evidence hash, `APPROVAL_TTL_MINUTES` and the exact phrase `DEPLOY <cluster>/<component>`, and re-verifies hash, TTL and target fields at execute time. Production requires two distinct actor names (honor system, documented). There is no skip or auto-approve path. The ArgoCD client has exactly two write functions, `refresh_app` and `sync_app` (prune off, no force), and `test_guard.py` pins that, the GET/POST route set, the closed resource list, and the absence of `deploy_tools` imports. The deploy token lookup never falls back to the read token. `llm_summary.py` is off by default, imports `litellm` lazily inside a try, and returns text only.

### Review limits

The shell returned `Exit Code: -1` for this review as well, and the file search tool did not index the project, so every conclusion comes from reading files. Read in this pass: `main.py`, `executor.py`, `gate.py`, `guardrails.py`, `audit.py`, `evidence.py`, `catalog.py`, `routers/deploy.py`, `argocd_client.py`, `argocd.py`, `kube.py`, `llm_summary.py`, `destroy.sh` (first 90 lines), `components.yaml`, `DeployTab.tsx`, `ArgoPanel.tsx`, `safety-model.md`, and the tests `test_deploy_api.py`, `test_kube.py`, `test_guard.py`. Not re-read: the 15 diagnose rule files, `types.ts`, `DeployConfirm.tsx`, README and RUNBOOK. The diagnose files and the rest of the frontend were unchanged by the fix pass, and the previous review read them without findings. `types.ts`, README and RUNBOOK were edited in the fix pass and rest on the previous review plus the coder's re-read. This is a reading-only approval, not a test result.

</details>

<details>
<summary>File map</summary>

Changed in this pass: `backend/app/main.py` (422 handler), `backend/app/deploy/executor.py` (`audit_invalid_request`, post-action guards), `backend/app/services/argocd.py` (read-only token message), `backend/app/services/kube.py` (8 names), `config/components.yaml` (empty), `frontend/src/components/DeployTab.tsx` (empty state), `frontend/src/components/ArgoPanel.tsx`, `frontend/src/types.ts` (`record_warning`), tests `test_deploy_api.py`, `test_kube.py`, `test_guard.py`, `test_deploy_catalog.py`, `test_argocd.py`, and docs `docs/safety-model.md`, `backend/README.md`, `RUNBOOK.md`, `README.md`.

Full diff not available: no git run, per the review constraints.

</details>
