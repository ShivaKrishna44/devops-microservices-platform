# Phase 2 implementation plan: Developer-friendly-infra

Project root (work directly here, no git worktree): `c:\Devops\Repository\Developer-friendly-infra`
Artifacts: `c:\Devops\Repository\devops-microservices-platform\.agents\tasks\phase2-idp\`
Mode: no approved design was supplied, so this plan records its own design decisions (section 3).

Everything below was written from reading files only. The shell tool returned `Exit Code: -1`
during planning, so nothing was run. Every "Verify" line has two forms: the command to run if the
coder's shell works, and the offline fallback (re-read with file tools, then mark UNVERIFIED).

## 0. Rules every coder pass must follow

1. Use ABSOLUTE paths with a lowercase drive letter, for example `c:\Devops\Repository\Developer-friendly-infra\backend\app\main.py`.
2. Write big files in chunks: create the file with the write tool, then append in pieces of about 150 to 250 lines (use `str_replace` on a trailing marker line such as `# CONTINUE` if there is no append tool, then remove the marker at the end).
3. Never run `terraform apply/destroy`, `aws eks`, any mutating `aws` call, `kubectl apply/delete/patch`, `helm install/upgrade`. Read-only validation only (section 1).
4. Never claim a check passed, or that a commit exists, unless a command really ran and printed it. Git cannot be run. Do not claim a repo exists.
5. Runtime code uses real data only. Sample JSON lives only under `backend/tests/fixtures/` and `frontend/src/test-fixtures/`, and only tests import it.
6. Plain language, short sentences, no em dashes, no exclamation points, in docs and comments.
7. Read the inline comments of a file before changing it. Do not weaken any Phase 1 protection: get-only kubectl wrapper (argv list, `shell=False`), account guard `589389425618`, typed confirmation in `provision.sh` and `destroy.sh`, registry locking, cost safety (t3.medium x2, max 3, single NAT, Project tag).
8. After each item, tick its box here and add one line to `c:\Devops\Repository\devops-microservices-platform\.agents\tasks\phase2-idp\verification.md` (item id, command run or "UNVERIFIED", result).

### Landmines found in existing tests (read before writing any code in `backend/app`)

`backend/tests/test_guard.py` scans every `.py` under `backend/app` and will fail the build if:

| Rule | What to avoid |
|------|----------------|
| `test_no_shell_true` | The text `shell=True` appears anywhere in `backend/app`, even in a comment. Write "shell off" or "shell=False" instead. |
| `test_no_write_verbs_as_string_constants` | Any string constant exactly equal to `apply`, `delete`, `patch`, `rollout`, `exec`, `scale`, `create`, `replace`, `edit`, `label`, `annotate`, `cordon`, `drain`, `taint`, `set`, `run`. This includes dict keys, enum values and default arguments. Sentences that merely contain these words are fine. |
| `test_no_crewai_import_at_module_top_level` | A top-level `import crewai`. The optional LLM summary must import lazily inside a function, inside `try/except`, and only when the env flag is on. |
| `test_never_imports_deploy_tools` | Any import whose name contains `deploy_tools`. The new package is named `app/deploy/`, which is fine. Never import from `devops-microservices-crewAi`. |
| `test_read_only_verbs_is_exactly_get` | `kube.READ_ONLY_VERBS` must stay `frozenset({"get"})`. |
| `test_agent_tools_import_without_crewai` / `test_main_does_not_import_agent_tools` | Leave `agent_tools.py` alone. `main.py` must not mention `agent_tools`. |

Other facts from the Phase 1 code that the plan depends on:

- `backend/app/settings.py` is a frozen dataclass built by `get_settings()` on every call. Add new fields at the END with defaults. Never add module-level constants for env values.
- `backend/tests/__init__.py` exists, so tests import `from .conftest import make_entry`. `conftest.py` has fixtures `registry_file` and `client`.
- `backend/tests/test_api.py` mocks kubectl with `monkeypatch.setattr(kube.subprocess, "run", ...)`. Keep `import subprocess` in `kube.py` so this still works.
- `backend/app/services/argocd.py` has `token_env_var`, `resolve_token`, `verify_tls_for`, `fetch_apps(cluster, transport=None)` (httpx `MockTransport` injection). Leave `_map_app` and `fetch_apps` unchanged so the existing ArgoCD tests keep passing.
- `frontend` uses `verbatimModuleSyntax` (use `import type`), `noUnusedLocals`, `noUnusedParameters`, `jsx: react-jsx`. `vite.config.ts` runs vitest in `environment: "node"` and includes only `src/**/*.test.ts`.
- Python in `pyproject`-less backend: keep code valid on 3.10 or newer (`from __future__ import annotations`, `timezone.utc`, no `datetime.UTC`).

## 1. Command catalogue (read-only validation only)

Run from `c:\Devops\Repository\Developer-friendly-infra` in Git Bash. If the shell returns `Exit Code: -1`, do not retry in a loop: mark the check UNVERIFIED and list the command for the user.

| Purpose | Command |
|---------|---------|
| Python syntax | `python -m py_compile <file.py>` or `python -m compileall -q backend/app` |
| Backend tests | `cd backend && python -m pytest -q` (one file: `python -m pytest tests/test_kube.py -q`) |
| Registry tests | `python -m pytest registry/tests -q` |
| Shell syntax | `bash -n scripts/destroy.sh` (and the other scripts) |
| Terraform (only if a `.tf` file changes; none planned) | `cd terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate` |
| Frontend | `cd frontend && npm install && npm test && npm run build` |
| Everything | `bash scripts/verify-local.sh` |

Offline fallback for any item: re-open each file written, check that every `import` and every name used across modules exists in the target file, and that every function the tests call exists with the same signature. Record "UNVERIFIED (static re-read only)".

## 2. Phase 1 gap ledger (the to-do list for Part A)

None of these is marked fixed from reading alone. "Seen" is what planning observed in the files.

| # | Gap from SUMMARY.md | Seen while planning | Plan item | Ledger status |
|---|---------------------|---------------------|-----------|---------------|
| G1 | `backend/tests/test_kube.py` never written | Only `test_guard.py` and `test_api.py` touch `kube`; no direct guard test seen | A3 | needs-verification |
| G2 | ArgoCD token is admin-scoped | `scripts/argocd-token.sh` logs in as `admin`; RUNBOOK step 4 tells the user to use it | A5 | needs-verification |
| G3 | `destroy.sh` orphan path inherits `ENVIRONMENT` | `ENVIRONMENT="${ENVIRONMENT:-dev}"` present in `scripts/destroy.sh` | A1 | needs-verification |
| G4 | kubectl token regex allows commas | `_TOKEN_RE = ^[a-z0-9]([-a-z0-9./,]*[a-z0-9])?$` in `backend/app/services/kube.py` | A2 | needs-verification |
| G5 | No lockfiles | No `package-lock.json`, no `.terraform.lock.hcl` seen | A6 (document only) | needs-verification |
| G6 | RUNBOOK ordering and Python 3.14 claim | Step 3 says "after step 4"; it says 3.14 is fine | A4 | needs-verification |
| G7 | State bucket untagged | RUNBOOK step 1 creates it with no tags | A4 (document, do not tag by script) | needs-verification |
| G8 | Hourly cost figures recalled, not checked | `0.10 + 0.045 + 2 x 0.0416` in README, `settings.py`, `common.sh`, `registry.py::cost_note` | A4 | needs-verification |
| G9 | Nothing in Phase 1 was ever executed | `verification.md` of phase 1 lists all checks as not run | every item | needs-verification |

## 3. Design decisions (each with the reason)

D1. **Kubectl wrapper becomes a strict grammar, not a token regex.** The only accepted shape is `get <resource> [-n <ns> | -A | --all-namespaces]`. The resource must be in an explicit allow-list. No names, no commas, no slashes, no `-o`, no `--raw`. Reason: a grammar cannot be widened by accident, and it kills `pods,secrets` and `secret/x` in one rule. Existing callers (`["get","pods","-n",ns]`, `["get","namespaces"]`) already fit.

D2. **Resource allow-list** is exactly: `pods`, `namespaces`, `deployments`, `replicasets`, `statefulsets`, `services`, `endpoints`, `events`, `persistentvolumeclaims`, `resourcequotas`, `configmaps`, `nodes`. `secrets` is not in it and must not appear in the file as a resource. One extra, separate set `METRICS_RESOURCES = {"pods.metrics.k8s.io", "nodes.metrics.k8s.io"}` is added so the diagnose engine can read usage with a plain `get` (the wrapper cannot run `kubectl top`, and `READ_ONLY_VERBS` must stay `{"get"}`). Flag this extra set in the final summary so the user can delete it. Needs verification against a real cluster: `kubectl get pods.metrics.k8s.io -n <ns> -o json`.

D3. **Pod lookups fetch the whole namespace and filter in Python.** No name argument is added to the wrapper. Reason: smaller attack surface, one call serves both the pod and namespace endpoints.

D4. **Diagnose engine is pure functions over a plain `DiagnoseInputs` object.** All I/O is in one file (`collect.py`). Reason: fixtures can drive every rule without kubectl or ArgoCD, and tests need no mocks of subprocess for the rules.

D5. **One rule function per check, 15 in total, each returns findings and a run status** (`executed`, `skipped` with reason, or `error`). A check that lacks its input (no metrics, ArgoCD not configured) is `skipped` with a reason, never silently dropped and never guessed.

D6. **Thresholds come from env vars read per call** (named in section 4), and user rules come from `config/checks.yaml` (strict schema). Reason: the spec limits the YAML to the named rule fields, and `settings.py` already uses per-call env reads.

D7. **Optional LLM summary** is off unless `DFI_DIAGNOSE_LLM_SUMMARY=1`. It runs only after deterministic findings exist, receives findings as read-only text, returns a `summary` string, and cannot change any severity or trigger any action. Its import is lazy and guarded. If no LLM library is installed it returns `llm_summary: null` with a reason. Reason: the API must start with no LLM library.

D8. **The only write path is the ArgoCD REST API, through two functions:** a refresh (`GET /api/v1/applications/{app}?refresh=normal`) and a sync (`POST /api/v1/applications/{app}/sync` with `prune: false`, no force, no dry-run override). There is no kubectl write, no rollback, no delete, no bulk, no wildcard. These two REST shapes come from the ArgoCD API docs and must be checked against the running server's swagger page (`/swagger-ui`) once a cluster exists. Mark as needs-verification-live.

D9. **Separate tokens.** Reads use `ARGOCD_TOKEN_<CLUSTER>` (read-only account `dfi-readonly`). Writes use `ARGOCD_DEPLOY_TOKEN_<CLUSTER>` or `ARGOCD_DEPLOY_TOKEN` (account `dfi-deploy`). The deploy lookup never falls back to the read token, and the read lookup never uses the deploy token. Reason: a leaked read token cannot sync.

D10. **Approval gate mirrors `approval_gate.py` / `guardrails.py` of the EKS upgrade project, adapted to a two-step plan then execute flow.**
- Plan record is bound to: cluster, environment, component, ArgoCD app, action, target revision.
- Evidence is canonical JSON (sorted keys, no timestamps) of those fields plus the live app state (sync status, health status, live revision, out-of-sync resources). `evidence_sha256` is its SHA-256.
- TTL from `APPROVAL_TTL_MINUTES` (default 15), the same name the EKS project uses.
- Typed phrase is exactly `DEPLOY <cluster>/<component>`.
- Execute re-verifies, in this order: plan exists, plan not yet used, stored evidence still hashes to the stored hash (tamper check), TTL, guardrails again (catalog and registry re-read from disk), phrase, actors, then re-reads the live ArgoCD app, rebuilds the evidence and compares the hash (drift check), then audits intent, then acts, then audits the result.
- A plan is single use. A second execute with the same plan id is refused.
- If the audit line cannot be written, the action is not taken (fail closed).
- Production (`environment == "prod"`) needs `actor` and `second_actor`, distinct after trimming and lower-casing. Locally this is honor system, with no identity check. Say so in the docs.

D11. **Refusals are HTTP 409** with `{ detail, kind: "deploy_refused", reason_code }`. Invalid body shape is 422. Request bodies use pydantic models with `extra="forbid"`, so a `force` or `prune` field is rejected as 422. ArgoCD failures during execute are 502 `kind: "argocd_error"`.

D12. **Audit log** is JSONL, append-only, default `<repo>/.state/audit.log`, path from `AUDIT_LOG_PATH`. Plans are stored in `<repo>/.state/plans.json` (path from `DEPLOY_STATE_PATH`), written atomically (temp file then replace) under a `threading.Lock`. The backend is single process by design (documented). `.state/` goes into `.gitignore`. Tokens never appear in any audit line or response.

D13. **Frontend tests use `renderToStaticMarkup` from `react-dom/server`** so no new dev dependency (no jsdom, no testing-library) is needed. Change only the vitest `include` to `src/**/*.test.{ts,tsx}`.

D14. **PyYAML** is the only new backend dependency. Add it to `backend/requirements.txt` as a bounded range (`PyYAML>=6.0,<7`), because the exact latest patch version was not checked. Use `yaml.safe_load` only. A test asserts `yaml.load(` never appears in `backend/app`.

## 4. Names introduced (use exactly these)

Env vars (all read per call in `settings.py`):

| Name | Default | Used by |
|------|---------|---------|
| `DFI_PENDING_TOO_LONG_MIN` | `10` | check 14 and severity of 15 |
| `DFI_QUOTA_WARN_PERCENT` | `90` | check 3 |
| `DFI_OOM_WARN_PERCENT` | `80` | check 9 (HIGH at 95) |
| `DFI_OVERPROV_PERCENT` | `20` | check 7 (usage below this percent of request) |
| `DFI_OVERPROV_MIN_CPU_M` / `DFI_OVERPROV_MIN_MEM_MI` | `100` / `128` | check 7 ignores requests smaller than these |
| `DFI_IMAGE_MIRROR_HOST` | empty | check 12 (no hardcoded host; empty means "set your mirror") |
| `DFI_CHECKS_CONFIG` | `<repo>/config/checks.yaml` | check 13 |
| `DFI_DIAGNOSE_LLM_SUMMARY` | off | optional summary |
| `DFI_COMPONENTS_CONFIG` | `<repo>/config/components.yaml` | deploy catalog |
| `APPROVAL_TTL_MINUTES` | `15` | deploy gate |
| `AUDIT_LOG_PATH` | `<repo>/.state/audit.log` | audit |
| `DEPLOY_STATE_PATH` | `<repo>/.state/plans.json` | plan store |
| `ARGOCD_DEPLOY_TOKEN_<CLUSTER>`, `ARGOCD_DEPLOY_TOKEN` | none | deploy writes only |
| `DFI_ENVIRONMENT` | `dev` | `destroy.sh` orphan path only |

New backend layout:

```
backend/app/diagnose/   __init__.py models.py quantities.py facts.py thresholds.py checks_config.py
                        rules_pod.py rules_pod_extra.py rules_workload.py rules_custom.py engine.py collect.py llm_summary.py
backend/app/deploy/     __init__.py catalog.py guardrails.py evidence.py audit.py gate.py executor.py
backend/app/services/   argocd_client.py   (detail reads, refresh, sync; reuses helpers from argocd.py)
backend/app/routers/    diagnose.py deploy.py audit.py
config/                 checks.yaml components.yaml
docs/                   diagnose-checks.md safety-model.md
```

# Implementation Plan

Item ids are stable (A1, B1, ...). Work them in the order listed. Each item leaves the repo in a
state where existing tests still make sense.

## Part A. Close Phase 1 gaps

- [ ] A1. Stop `destroy.sh` orphan recovery from inheriting an exported `ENVIRONMENT`.
      Replace `ENVIRONMENT="${ENVIRONMENT:-dev}"` with `DFI_ENVIRONMENT="${DFI_ENVIRONMENT:-dev}"` and use that variable for the orphan default and for the later `export_tf_vars` call. When a registry entry exists, its environment still wins. Add a header comment explaining that only `DFI_ENVIRONMENT=dev|staging|prod` is read, and that a plain `ENVIRONMENT` in the shell is ignored. Validate the value with the existing `validate_env` helper in `scripts/common.sh` so a typo fails early with a clear message. Do not touch the typed confirmation, the account guard or the cleanup logic. Re-read the whole file first and list in verification.md which lines changed. Needs-verification: the ledger item G3 is only closed after `bash -n` and a `DRY_RUN=1` run by the user.
      Files: `c:\Devops\Repository\Developer-friendly-infra\scripts\destroy.sh`
      Verify: `bash -n scripts/destroy.sh` passes. User-run (offline, no AWS): `ENVIRONMENT=production DRY_RUN=1 REGISTRY_PATH=/tmp/r.json TF_STATE_BUCKET=dummy bash scripts/destroy.sh ghost-one` must get past variable validation (it needs terraform, aws and kubectl on PATH, so it may stop at `require_cmd`; record that). Offline fallback: re-read and confirm no remaining `${ENVIRONMENT` in the file.

- [ ] A2. Replace the loose kubectl argument check with a strict grammar and a resource allow-list (design D1, D2, D3).
      In `kube.py`: delete `_TOKEN_RE` and `_ALLOWED_FLAGS`. Add `ALLOWED_RESOURCES` (the 12 names in D2, as a `frozenset`) and `METRICS_RESOURCES` (D2). Rewrite `_check_args(cluster, args)` to accept only: `args[0] == "get"`, `args[1]` an exact member of the two sets, then either nothing, `-A`, `--all-namespaces`, or `-n <namespace>` where namespace matches the RFC-1123 label pattern already used in `routers/deps.py` (`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`, max 63). Reject: extra tokens, repeated flags, both `-n` and `-A`, any token starting with `-` other than those flags, any `,` `/` `=` `;` whitespace or other character, `secrets` or any word not in the sets. The error text stays fixed (never echo the offending value back inside shell-like text). Keep `READ_ONLY_VERBS = frozenset({"get"})`, keep `import subprocess` at module level, keep `shell=False`, the timeout, and the `-o json` suffix. Keep `_CONTEXT_RE`. Update the module docstring: deploy no longer needs kubectl writes because it uses the ArgoCD REST API only; this module stays get-only. Do not put the word `secrets` in any string constant except inside a docstring or comment sentence. Existing callers (`routers/pods.py`, `routers/namespaces.py`, `agent_tools.py`) must still pass: confirm each one's argument list against the grammar by reading them.
      Files: `c:\Devops\Repository\Developer-friendly-infra\backend\app\services\kube.py`
      Verify: `cd backend && python -m pytest tests/test_api.py tests/test_guard.py -q` still passes (they exercise `run_kubectl`). Offline fallback: read `routers/namespaces.py`, `routers/pods.py` and `agent_tools.py` and write the check result for each call in verification.md.

- [ ] A3. Add the guard tests (ledger G1). Retry rule from the task: write `c:\Devops\Repository\Developer-friendly-infra\backend\tests\test_kube.py` ONCE. If the permission layer refuses it, write the same content to `backend\tests\test_kubectl_guard.py`. If that is also refused, STOP, do not use any other route (no shell redirection, no other folder), and report exactly which writes were refused in verification.md and in a `send_message` warning.
      Content (use `monkeypatch.setattr(kube.subprocess, "run", fake)` where `fake` records `cmd` and kwargs and returns an object with `stdout='{"items": []}'`, `stderr=''`, `returncode=0`):
      1. Accepted: `["get","pods","-n","default"]`, `["get","namespaces"]`, `["get","events","-A"]`, `["get","nodes"]`, every member of `ALLOWED_RESOURCES`.
      2. Argv shape on an accepted call: `cmd` is a `list`, `kwargs["shell"] is False`, `cmd[:3] == [kubectl_bin, "--context", "dev-eu"]`, `cmd[-2:] == ["-o","json"]`, and `--request-timeout=` is present.
      3. Rejected with `ReadOnlyViolation` and the fake NEVER called (parametrize): verbs `apply`, `delete`, `patch`, `exec`, `edit`, `scale`, `rollout`, `create`, `replace`, `label`, `annotate`, `cordon`, `drain`, `taint`, `top`, `logs`, `port-forward`, `run`, an empty list, `["GET","pods"]`.
      4. Rejected: shell metacharacters in any position (`pods;id`, `pods&&ls`, `pods|cat`, `pods$(id)`, backtick, newline, space, `>`, `<`, quotes, `\`), and in the namespace value.
      5. Rejected: `secrets`, `secret`, `Secrets`, `secrets.v1`, `pods,secrets`, `pods,pods`, `pods/foo`, `secrets/x`, `all`, `*`, `pods.metrics.k8s.io,secrets`, any comma-joined list even of allowed names.
      6. Rejected: argument injection: `["get","pods","-n","default","-o","yaml"]`, `["get","pods","--output=yaml"]`, `["get","pods","--raw","/api"]`, `["get","pods","-n","--all-namespaces"]`, `["get","pods","-n"]`, `["get","pods","-n","a","-n","b"]`, `["get","pods","-n","a","-A"]`, `["get","pods","--token=x"]`, `["get","pods","-l","a=b"]`, `["get","pods","--kubeconfig","/tmp/x"]`, `["get","pods","--context","other"]`, `["get","pods","--as","admin"]`.
      7. Rejected cluster context names: `""`, `"-x"`, `"dev-eu --token=x"`, `"a"`, `"Dev_EU"`, 40 characters, `"dev-eu;ls"`.
      8. `"secrets" not in kube.ALLOWED_RESOURCES` and no member contains a comma; `kube.READ_ONLY_VERBS == frozenset({"get"})`.
      9. Failure mapping still works: non-zero return code gives `KubectlError`; `FileNotFoundError` gives `KubectlError`; invalid JSON gives `KubectlError`.
      Files: `c:\Devops\Repository\Developer-friendly-infra\backend\tests\test_kube.py` (or `test_kubectl_guard.py`)
      Verify: `cd backend && python -m pytest tests/test_kube.py -q` (or the fallback name). Offline fallback: re-read test and `kube.py` side by side and check each rejected case against the grammar by hand; record UNVERIFIED.

- [ ] A4. Fix RUNBOOK ordering and wording, and add the cost note (ledger G6, G7, G8). Do this as a pure reorder plus text edits, no new commands in this item. New order of the existing steps: 0 prerequisites, 1 state bucket, 2 create cluster, 3 give the portal access to ArgoCD (old step 4), 4 start the backend (old step 3), 5 frontend, 6 what to look for, 7 tear down, 8 troubleshooting. Remove "Do this after step 4 if you want ArgoCD data on first load" and "Python 3.14 is fine for the portal itself". Replace the prerequisites line with: Python 3.12 or 3.13 recommended, 3.10 to 3.13 allowed, not 3.14 (not tested; CrewAI, if you ever install it, needs 3.10 to 3.13). Fix the troubleshooting row about `crewai` to say the same. Add a "Cost figures are estimates" note near step 2 and in `README.md` under the cost table: the hourly numbers (0.10, 0.045, 2 x 0.0416) were recalled, have not been checked against AWS pricing, and change by region and over time; check the AWS pricing pages and the Billing console; the portal's "est. $" is a clock times a constant, not a bill. Add one line saying the state bucket from step 1 is untagged and left behind on purpose, and how to tag it (`aws s3api put-bucket-tagging ...` printed as an optional user command, never run by a script). Do NOT yet write the new Phase 2 steps (that is item E4).
      Files: `c:\Devops\Repository\Developer-friendly-infra\RUNBOOK.md`, `c:\Devops\Repository\Developer-friendly-infra\README.md`
      Verify: re-read both files; confirm step numbers in cross references (for example "see step 4") match the new order. No command runs. Mark UNVERIFIED for anything about AWS pricing.

- [ ] A5. Document read-only and deploy ArgoCD accounts (ledger G2). Add a new RUNBOOK section "ArgoCD accounts" directly after the ArgoCD access step, with exact, copy-paste steps for the user to run themselves once the cluster exists (they are the user's own admin commands, the portal never runs them). Content:
      1. Bootstrap login with the existing admin flow (`scripts/argocd-token.sh` and the port-forward). State that this admin token is for setup only and must not be the portal's token.
      2. Create accounts with an `argocd-cm` merge patch: `accounts.dfi-readonly: apiKey` and `accounts.dfi-deploy: apiKey` (commands use `kubectl --context <name> -n argocd patch configmap argocd-cm --type merge --patch-file ...`, with the patch file content shown in a code block).
      3. RBAC in `argocd-rbac-cm` `policy.csv`: `p, role:dfi-readonly, applications, get, */*, allow` and `g, dfi-readonly, role:dfi-readonly`; for deploy, per named app: `p, role:dfi-deploy, applications, get, default/<APP>, allow`, `p, role:dfi-deploy, applications, sync, default/<APP>, allow`, `g, dfi-deploy, role:dfi-deploy`; and `policy.default: ""` so an unlisted user has no role. Tell the user to replace `<APP>` with each app name from `config/components.yaml` (one line pair per app, no wildcard).
      4. Generate tokens with the ArgoCD CLI: `argocd login localhost:<port> --username admin --insecure`, then `argocd account generate-token --account dfi-readonly --expires-in 24h` and the same for `dfi-deploy`. Show the export lines: `export ARGOCD_TOKEN_DEV_EU='...'` (read-only) and `export ARGOCD_DEPLOY_TOKEN_DEV_EU='...'` (deploy).
      5. Say clearly: the portal needs the read-only token for Phase 1 and Phase 2 (pods, diagnose, ArgoCD list, deploy plan). The deploy token is needed only for Part C execute. Do not export the deploy token until you want to deploy.
      6. Check, expected result written as "expected" not "seen": `argocd --auth-token "$READ_TOKEN" account can-i sync applications '*'` should print `no`; `... can-i get applications '*'` should print `yes`.
      7. Change the header comment of `scripts/argocd-token.sh` to say it prints an ADMIN session token for bootstrap only. Change nothing else in that script.
      Also update `backend/README.md` env table with the two deploy token names and the rule that the deploy token never falls back to `ARGOCD_TOKEN`.
      Files: `c:\Devops\Repository\Developer-friendly-infra\RUNBOOK.md`, `c:\Devops\Repository\Developer-friendly-infra\scripts\argocd-token.sh` (comment only), `c:\Devops\Repository\Developer-friendly-infra\backend\README.md`
      Verify: `bash -n scripts/argocd-token.sh`. Re-read the RUNBOOK section and check every command is in a code block and says who runs it. The RBAC lines and the `can-i` outputs are NOT verified; label them "expected, not yet seen" and check them against the ArgoCD RBAC docs if web search is available.

- [ ] A6. Version notes and lockfile statement (ledger G5). Do not invent lockfile contents and do not create `package-lock.json` or `.terraform.lock.hcl`. Add a header comment to `backend/requirements.txt` and `backend/requirements-dev.txt` ("pins are exact; they were looked up when written; install and run the tests to confirm they resolve together"). Create `VERSIONS.md` in the repo root with a table of what is pinned and where: Terraform `>= 1.11`, AWS provider `>= 6.59, < 7.0`, `terraform-aws-modules/eks/aws` 21.29.0, `vpc` 6.7.3, EKS 1.35, ArgoCD v3.5.6 (override `ARGOCD_VERSION`), Python 3.12 or 3.13, Node 20 or newer, and the exact backend and frontend pins read from `requirements.txt` and `frontend/package.json` at the time (read both files again and copy; do not guess). State at the top: "Re-check every version before relying on it. These were not validated by an install in this environment." State that `terraform/.terraform.lock.hcl` and `frontend/package-lock.json` must be generated by the user running `terraform init` and `npm install`, then committed. Check `.gitignore` does not ignore `.terraform.lock.hcl` (it must not). Add `.state/` to `.gitignore` here (it is needed from item C3 on) with a comment line.
      Files: `c:\Devops\Repository\Developer-friendly-infra\VERSIONS.md`, `c:\Devops\Repository\Developer-friendly-infra\backend\requirements.txt`, `c:\Devops\Repository\Developer-friendly-infra\backend\requirements-dev.txt`, `c:\Devops\Repository\Developer-friendly-infra\.gitignore`
      Verify: re-read; confirm `VERSIONS.md` numbers match `package.json`, `requirements.txt` and `terraform/` files exactly (read `terraform/versions.tf` or the file that holds `required_providers`). `pip install -r backend/requirements-dev.txt` if the shell works.

## Part B. Diagnose engine (backend core)

Spec used: `c:\Devops\Repository\Self-study-before-interview\K8-Real-scenario-debug.md` (the `Prepare-now` copy named in the task was not found; this one has the same 15 sections, same numbering). Section numbers below are its numbers. Tips must be written in the coder's own short sentences from the "Common causes and fixes" tables, not copied in bulk.

### Rule table (the contract for B4 to B6 and the tests)

Severity words are CRITICAL, HIGH, WARNING, INFO. `doc_ref` is `{"file": "K8-Real-scenario-debug.md", "section": N}`.

| # | key | Reads (kubectl JSON field or ArgoCD field) | Severity logic |
|---|-----|--------------------------------------------|----------------|
| 1 | `probe_failure` | Events on the pod with `reason == "Unhealthy"` and message containing `Liveness probe failed`, `Readiness probe failed` or `Startup probe failed`; message class: `connection refused`, `statuscode: 5xx`, `context deadline exceeded`; `spec.containers[].livenessProbe/readinessProbe/startupProbe` present; container `restartCount` | Liveness or startup failure with restarts > 0: HIGH. Readiness only: WARNING. No probe defined at all on a long-running pod is NOT reported (not in the spec). |
| 2 | `argocd_sync` | ArgoCD app `status.sync.status`, `status.health.status`, `status.operationState.phase` and `.message`, `status.conditions[].type/message`, `status.resources[]` with non-Synced status | `OutOfSync`: WARNING. `Degraded` or `Missing`: HIGH. Operation phase `Failed` or `Error`, or condition `ComparisonError`: HIGH, with the message mapped to the spec's error table (namespace not found, field is immutable, is forbidden, exceeded quota, CRD missing, hook failed). Both OutOfSync and Degraded give two findings. Skipped when ArgoCD status is not `ok`. |
| 3 | `resource_quota` | `resourcequotas[].status.used` vs `.status.hard`; ReplicaSet and Job events with `reason == "FailedCreate"` and message containing `exceeded quota` or `must specify` | FailedCreate with `exceeded quota`: CRITICAL. `must specify limits`: HIGH. Used/hard >= 100%: HIGH. Used/hard >= `DFI_QUOTA_WARN_PERCENT`: WARNING. Evidence names the resource and the used/hard values. |
| 4 | `volume_mount` | Events with reason `FailedMount`, `FailedAttachVolume`, `FailedScheduling` mentioning PVC; message class: `not found`, `unbound immediate PersistentVolumeClaims`, `Multi-Attach error`, `secret ... not found`, `configmap ... not found`; PVC `status.phase == "Pending"`; pod status `ContainerCreating` or `Init:n/m` | HIGH for each class. Multi-Attach tip mentions `Recreate`, StatefulSet or RWX storage. |
| 5 | `crashloop` | `containerStatuses[].state.waiting.reason == "CrashLoopBackOff"`, `lastState.terminated.exitCode/reason`, `restartCount` | CRITICAL. Exit code table from spec (0, 1, 2, 126, 127, 137, 139, 143) goes into the message and tip. Exit 137 points to check 9. |
| 6 | `pod_pending` | `status.phase == "Pending"`, `spec.nodeName` empty, `FailedScheduling` events; message class: `Insufficient cpu`, `Insufficient memory`, `untolerated taint`, `node affinity/selector`, `anti-affinity`, `unbound immediate PersistentVolumeClaims`, `volume node affinity conflict`, `Too many pods` | HIGH when a `FailedScheduling` event exists. WARNING when Pending with no event yet. |
| 7 | `overprovisioned` | Container `resources.requests` vs metrics-API usage (`pods.metrics.k8s.io`) | INFO when usage is below `DFI_OVERPROV_PERCENT` of request and the request is at least the minimum. Skipped with reason `metrics-server not available` when no metrics. |
| 8 | `pod_failure` | `status.phase == "Failed"`, `status.reason` (`Evicted`, `DeadlineExceeded`), `status.message`, terminated containers with exit code != 0 on pods with `restartPolicy` not `Always` | HIGH. Evicted tip mentions node pressure and ephemeral storage. |
| 9 | `oom_risk` | `lastState.terminated.reason == "OOMKilled"` or `exitCode == 137` (also in current `state.terminated`); `resources.limits.memory`; usage percent from metrics | OOMKilled: CRITICAL, tip proposes at least double the current limit (512Mi gives 1Gi). Usage >= `DFI_OOM_WARN_PERCENT`: WARNING; >= 95: HIGH. If metrics are missing the OOMKilled part still runs and the check is `executed` with a note that the usage part was skipped. |
| 10 | `image_pull` | `waiting.reason` in `ErrImagePull`, `ImagePullBackOff`, `InvalidImageName`; events `Failed` or `BackOff` with pull messages; message class from spec table (`manifest unknown`, `pull access denied`, `unauthorized`, `toomanyrequests`, `i/o timeout`, `x509`) | HIGH. |
| 11 | `deployment_health` | `deployments[].spec.replicas` vs `status.readyReplicas`, `availableReplicas`, `updatedReplicas`; condition `Progressing` with reason `ProgressDeadlineExceeded`; the same for StatefulSet `readyReplicas`; ReplicaSet events | Ready < desired: HIGH. `ProgressDeadlineExceeded` or available == 0 with desired > 0: CRITICAL. Evidence names the stuck ReplicaSet (owner chain pod, ReplicaSet, Deployment through `ownerReferences`). |
| 12 | `bitnami_image` | `spec.containers[].image` and `initContainers[].image` starting with `docker.io/bitnami/`, `bitnami/`, `registry-1.docker.io/bitnami/`, `index.docker.io/bitnami/`; `bitnamilegacy/` variants | WARNING. HIGH when the same pod also has an image pull failure. Message names the mirror from `DFI_IMAGE_MIRROR_HOST`; if empty it says to set `DFI_IMAGE_MIRROR_HOST`. `bitnamilegacy` gets a separate "no security updates" message. |
| 13 | `custom_rules` | `config/checks.yaml` rules over the derived metrics (below) | Severity from the rule. A config error becomes one WARNING finding named `custom_rules_config_error` with the error list in evidence; it never raises. |
| 14 | `pending_too_long` | Pod phase `Pending` and age > `DFI_PENDING_TOO_LONG_MIN`; `spec.nodeName` empty means scheduling cause (points to check 6 and quotes the `FailedScheduling` message); node assigned means start-up cause from container waiting reason (`ContainerCreating` plus `FailedMount` -> check 4, `ErrImagePull` -> 10, `PodInitializing` -> 4, `CreateContainerConfigError`) | HIGH. |
| 15 | `pod_not_ready` | Pod phase `Running`, condition `Ready == "False"`, containers with `ready == false`, other false conditions (`Initialized`, `ContainersReady`, `PodScheduled`), `spec.readinessGates` | WARNING. HIGH when the Ready condition has been False longer than `DFI_PENDING_TOO_LONG_MIN`. Not raised for pods in phase `Succeeded` or `Failed`. |

Derived metrics per pod and container (used by check 13 and shown in the UI): `pod_age_hours`, `total_restarts`, `last_restart_hours`, `restart_rate` (restarts per hour of pod age), `container_exit_code`, `container_exit_reason`, `event_count_warning`, `memory_percent_of_limit`. A metric that cannot be computed is `null`, and a custom rule on a `null` metric is skipped for that row with a note, never treated as zero.

- [ ] B1. Scaffold the package, settings and config reader fields.
      Create `backend/app/diagnose/__init__.py` (docstring only, no imports, so importing `app.diagnose` can never pull in an LLM library). Add the new env-driven fields from section 4 to `Settings` and `get_settings()` in `settings.py` for diagnose only (`pending_too_long_min`, `quota_warn_percent`, `oom_warn_percent`, `overprov_percent`, `overprov_min_cpu_m`, `overprov_min_mem_mi`, `image_mirror_host`, `checks_config_path`, `diagnose_llm_summary`). Fields go at the END of the dataclass, with the same `_number` and `_flag` helpers. Add `PyYAML>=6.0,<7` to `backend/requirements.txt`. Create the `config/` folder with `config/checks.yaml` containing the three example rules from the spec (high restart count with `total_restarts > 3`, memory near limit with `memory_percent_of_limit >= 80`, old pod with `pod_age_hours > 1500`), each preceded by a comment saying these are example rules the user edits, and severity in lower case as in the spec. Use real metric names from the list above.
      Files: `backend/app/diagnose/__init__.py`, `backend/app/settings.py`, `backend/requirements.txt`, `config/checks.yaml` (all under `c:\Devops\Repository\Developer-friendly-infra\`)
      Verify: `cd backend && python -m py_compile app/settings.py app/diagnose/__init__.py` and `python -m pytest tests/test_api.py -q` (settings change must not break it). Offline fallback: re-read `settings.py` and confirm no field was inserted before an existing one.

- [ ] B2. Models, quantity parsing and derived facts (pure code, no I/O).
      `models.py`: `Severity` as plain string constants plus an ordering dict (do not use the strings `set` or `create` anywhere); dataclasses `Finding(id, check, check_key, severity, subject{namespace,pod,container}, message, evidence, tip, doc_ref)`, `CheckRun(number, key, name, status in {"executed","skipped","error"}, reason, findings_count)`, `DiagnoseInputs(cluster, namespace, now, pods, events, replicasets, deployments, statefulsets, pvcs, resourcequotas, metrics, argocd, argocd_reason)` where each of the first group is the raw `items` list and `metrics` is `None` or a parsed dict keyed `(pod, container)`, and `DiagnoseResult` with a `to_dict()` that returns JSON-safe data (sorted by severity then subject). Finding ids are stable: `<check_key>:<namespace>/<pod>/<container or ->` plus a short suffix only when two findings of the same check share a subject.
      `quantities.py`: `parse_cpu_millicores("250m"|"1"|"0.5")`, `parse_memory_bytes("512Mi"|"1Gi"|"128974848"|"1G")` (binary and decimal suffixes), `parse_timestamp(str)` for RFC 3339 `Z` times, `percent(a, b)` that returns `None` when `b` is 0 or missing. Bad input returns `None`, never raises.
      `facts.py`: `pod_facts(pod, events, metrics, now)` returning the derived metrics rows described above, plus helpers used by rules: `container_waiting_reason`, `last_terminated`, `owner_chain(pod, replicasets)`, `pod_events(events, pod_name)` (match `involvedObject.kind == "Pod"` and name), `workload_events` (ReplicaSet, Deployment, Job events), `ready_false_since(pod)`. All take `now` as an argument so tests are deterministic.
      Files: `backend/app/diagnose/models.py`, `backend/app/diagnose/quantities.py`, `backend/app/diagnose/facts.py`
      Verify: `python -m py_compile` on each file; real tests come in T2. Offline fallback: re-read for names used by later items and list them in verification.md so B3 to B6 import exactly these.

- [ ] B3. Strict `checks.yaml` loader (check 13 support).
      `checks_config.py`: `load_checks(path) -> (rules, errors)`. Rules: only `yaml.safe_load`; top level must be a mapping with a single key `checks` holding a list (max 100). Each rule must have exactly the keys `name`, `severity`, `metric`, `operator`, `threshold`, `message`, `tip` (no missing, no unknown key). `name` unique, matches `^[a-z0-9][a-z0-9-]{0,62}$`. `severity` one of critical/high/warning/info, case-insensitive, stored upper case. `metric` must be one of the 8 derived metrics. `operator` one of `>`, `>=`, `<`, `<=`, `==`, `!=`. `threshold` a number (not a bool) for numeric metrics, a string for `container_exit_reason` (operators `==` and `!=` only). `message` and `tip` non-empty strings, max 300 characters. Missing file returns `([], [])` with a separate flag so check 13 is `skipped` with reason "config/checks.yaml not found". A YAML syntax error returns one error that includes the line and column from the YAML exception mark. Per-rule problems each give one error string with the rule index and name. Valid rules next to invalid ones are NOT run when any error exists in the file's structure (fail closed to avoid half-applied config), but the finding lists every error. `evaluate(rule, value)` does the comparison and returns `None` when `value is None`.
      Files: `backend/app/diagnose/checks_config.py`
      Verify: `python -m py_compile backend/app/diagnose/checks_config.py`; tests in T2.

- [ ] B4. Rules, part 1: container state and image checks, 1, 5, 9, 10, 12.
      `rules_pod.py` with five functions `rule_probe_failure`, `rule_crashloop`, `rule_oom_risk`, `rule_image_pull`, `rule_bitnami_image`, each `(inputs, pod, facts) -> list[Finding]`, following the rule table. Put the exit-code table and pull-error class table in module-level dicts (keys are error text fragments, not write verbs). Every finding fills `evidence` with the raw fields read (field path, value), `doc_ref`, and a tip in plain sentences. Check 9 must compute "at least double the limit" from `parse_memory_bytes` and format it back (512Mi -> 1Gi). Check 12 reads the mirror host from `get_settings().image_mirror_host` at call time.
      Files: `backend/app/diagnose/rules_pod.py`
      Verify: `python -m py_compile backend/app/diagnose/rules_pod.py`; behavior tests in T3.

- [ ] B5. Rules, part 2: scheduling, volume, failure and readiness checks, 4, 6, 8, 14, 15.
      `rules_pod_extra.py` with `rule_volume_mount`, `rule_pod_pending`, `rule_pod_failure`, `rule_pending_too_long`, `rule_pod_not_ready`. Check 14 must not repeat the full FailedScheduling analysis: it states the age, the threshold, whether the pod was scheduled, and points to check 6 or check 4 or check 10 by section number. Check 4 reads PVC objects from `inputs.pvcs` to say whether the PVC exists and its phase. Do not read Secrets to test for existence (the wrapper cannot); use the event message only.
      Files: `backend/app/diagnose/rules_pod_extra.py`
      Verify: `python -m py_compile backend/app/diagnose/rules_pod_extra.py`; behavior tests in T3.

- [ ] B6. Rules, part 3: workload, namespace and custom checks, 2, 3, 7, 11, 13.
      `rules_workload.py`: `rule_argocd_sync(inputs, scope)` (apps whose `destination_namespace` equals the namespace, or for a pod the app named by label `argocd.argoproj.io/instance` on the pod when present), `rule_resource_quota(inputs, scope)`, `rule_overprovisioned(inputs, pod, facts)`, `rule_deployment_health(inputs, scope)`. `rules_custom.py`: `rule_custom(inputs, pod_fact_rows, rules, errors)` which turns each row and rule into a finding, and turns config errors into the single `custom_rules_config_error` finding. For ArgoCD data, `inputs.argocd` is a list of detailed app dicts (see C2 for `argocd_client.list_apps_detail`) or `None` with `inputs.argocd_reason` saying why (`not_configured`, `unreachable`, `unauthorized`).
      Files: `backend/app/diagnose/rules_workload.py`, `backend/app/diagnose/rules_custom.py`
      Verify: `python -m py_compile` on both; behavior tests in T3.

- [ ] B7. Engine, collector and ArgoCD detail reader.
      `engine.py`: a `CHECKS` list of 15 entries `(number, key, name, scope)` where scope is `pod` or `workload`; `diagnose_pod(inputs, pod_name)` and `diagnose_namespace(inputs)`. Both return `DiagnoseResult.to_dict()` with: `cluster`, `namespace`, `pod` (or null), `header` `{phase, restarts, error_count, warning_count, info_count, checks_executed, checks_total}` (error_count counts CRITICAL and HIGH), `findings`, `metrics` (the derived metrics rows), `checks` (all 15, each with `status`, `reason`, `findings_count`), `llm_summary`. Pod mode runs pod rules for that pod plus the workload rules narrowed to the pod's owner chain and ArgoCD app. Namespace mode runs pod rules for every pod (cap 200, add a note in `checks` reason if capped) and the workload rules for the whole namespace, and returns a `pods` list of `{name, phase, restarts, error_count, warning_count}`. A rule that raises is caught: its check becomes `error` with the exception class name in `reason`, and the other checks still run (no stack trace in the response).
      `collect.py`: the only I/O file. `collect_inputs(cluster, namespace)` calls `kube.run_kubectl` for `pods`, `events`, `replicasets`, `deployments`, `statefulsets`, `persistentvolumeclaims`, `resourcequotas` (each `["get", <resource>, "-n", ns]`), and `["get","pods.metrics.k8s.io","-n",ns]` for metrics. A `KubectlError` on pods is fatal and propagates (502 as today). A `KubectlError` on any other resource is recorded as that resource missing and the checks that need it are `skipped` with reason `could not read <resource>: <short message>`. A metrics failure gives `metrics=None` and reason `metrics-server not available`. ArgoCD detail comes from `services/argocd_client.list_apps_detail` (C2 defines it; to keep B7 buildable, create `services/argocd_client.py` now with only the read side: `list_apps_detail(cluster, transport=None)` returning `{status, message, apps}` where each app has name, project, destination_namespace, sync_status, health_status, target_revision, live_revision, operation_phase, operation_message, conditions, out_of_sync_resources). It must reuse `token_env_var`, `resolve_token`, `verify_tls_for` from `argocd.py` and follow the same never-raise result shape and the same no-secrets-in-messages rule.
      `llm_summary.py`: `maybe_summarize(result_dict) -> {"summary": str|None, "reason": str}`. Returns `None` with reason `disabled` unless `get_settings().diagnose_llm_summary` is true. When on, import the LLM library lazily inside the function inside `try/except Exception`; if the import fails return reason `library not installed`. It receives only the findings list, returns text only, and the caller never reads severity from it. Add a short comment: the summary cannot change severity and cannot trigger any action.
      Files: `backend/app/diagnose/engine.py`, `backend/app/diagnose/collect.py`, `backend/app/diagnose/llm_summary.py`, `backend/app/services/argocd_client.py`
      Verify: `python -m py_compile` on each; `python -c "import app.diagnose.engine, app.diagnose.collect"` from `backend/` with no LLM library installed. Tests in T4.

- [ ] B8. Routers and wiring.
      `routers/diagnose.py` with `GET /diagnose/pod?cluster=&namespace=&pod=` and `GET /diagnose/namespace?cluster=&namespace=`, using `cluster_param` and `namespace_param` from `deps.py`; add a `pod_param` (RFC-1123 subdomain pattern, max 253, dots allowed) to `deps.py`. A pod name not found in the namespace returns 404 `{detail, kind:"pod_not_found"}` (add a small exception class and handler in `main.py`, same style as `ClusterNotFound`). Mount the router in `main.py` by adding `diagnose` to the existing import and loop. Update the `main.py` docstring: Phase 2 adds read-only diagnose; the deploy router (item C6) is the only write path and is documented in `docs/safety-model.md`. Add the two endpoints and their response shape to `backend/README.md` (endpoint table and a "Diagnose" subsection). `GET` only, no body.
      Files: `backend/app/routers/diagnose.py`, `backend/app/routers/deps.py`, `backend/app/main.py`, `backend/README.md`
      Verify: `cd backend && python -m pytest tests/test_api.py tests/test_guard.py -q`; `test_sources_found` still passes. Offline fallback: re-read `main.py` and check the router import name matches the file name.

## Part B tests

- [ ] T1. Sample fixtures under `backend/tests/fixtures/diagnose/`. These are hand-written JSON shaped like `kubectl get ... -o json` output (a `List` with `items`), not recordings from a live cluster; say so in `backend/tests/fixtures/README.md`. One folder or file per scenario, each holding the lists it needs (`pods`, `events`, `replicasets`, `deployments`, `statefulsets`, `pvcs`, `resourcequotas`, optional `metrics`, optional `argocd`). Use a fixed clock: tests pass `now = 2026-01-15T12:00:00Z`, and fixture timestamps are written relative to that. Scenarios (file names): `oom_killed_137_512mi`, `crashloop_exit1`, `imagepull_manifest_unknown_bitnami` (image `docker.io/bitnami/mongodb:7.0.14`), `pending_insufficient_cpu`, `pending_unbound_pvc`, `multi_attach_error`, `readiness_probe_failing`, `failed_evicted`, `quota_exceeded_replicaset_event` (event on the ReplicaSet, no Pending pod), `deployment_stuck_2_of_4`, `argocd_outofsync_degraded`, `overprovisioned_with_metrics`, `healthy_pod` (Running, ready, no restarts, quota at 50%, metrics at 40% of limit, non-bitnami image, Synced and Healthy app), plus `checks_valid.yaml`, `checks_malformed_syntax.yaml` (bad indentation), `checks_malformed_schema.yaml` (unknown key, bad operator, unknown metric, duplicate name, bool threshold). Write each file in its own write call to keep calls small.
      Files: `backend/tests/fixtures/diagnose/*.json`, `backend/tests/fixtures/diagnose/*.yaml`, `backend/tests/fixtures/README.md`
      Verify: if the shell works, `python -c "import json,glob;[json.load(open(f)) for f in glob.glob('backend/tests/fixtures/diagnose/*.json')]"` exits 0. Offline fallback: re-read each file for balanced braces and the fields the matching test will read.

- [ ] T2. Unit tests for quantities, facts and the checks.yaml loader.
      `backend/tests/test_diagnose_quantities.py` (cpu and memory parsing incl. bad input returns `None`, percent with zero), `test_diagnose_facts.py` (derived metrics from `oom_killed_137_512mi`: `container_exit_code == 137`, `container_exit_reason == "OOMKilled"`, `total_restarts`, `last_restart_hours`, `restart_rate`, `memory_percent_of_limit is None` without metrics and a number with metrics), `test_diagnose_checks_config.py` (valid file loads; missing file flagged not-found; syntax error gives one error with a line number; every schema fault in `checks_malformed_schema.yaml` is reported; `yaml.load(` absent from `backend/app` via a text scan; `evaluate` returns `None` for `None` values and rejects `<` on a string metric).
      Files: the three test files above under `backend/tests/`
      Verify: `cd backend && python -m pytest tests/test_diagnose_quantities.py tests/test_diagnose_facts.py tests/test_diagnose_checks_config.py -q`.

- [ ] T3. Rule tests, one test per fixture scenario, all through `rule_*` functions or `diagnose_pod` with `now` fixed.
      `backend/tests/test_diagnose_rules.py` asserts, per scenario: OOM fixture gives a CRITICAL `oom_risk` finding with exit code 137 and the tip text containing `1Gi`; crashloop gives CRITICAL check 5; image-pull fixture gives HIGH check 10 with class `manifest unknown` and a check 12 finding that names `DFI_IMAGE_MIRROR_HOST` when unset and the monkeypatched host when set (use a test-only host like `mirror.test.invalid`), and check 12 escalates to HIGH; pending CPU fixture gives check 6 with `Insufficient cpu`; pending PVC fixture gives check 4 and check 6; Multi-Attach gives check 4 mentioning `Recreate`; readiness fixture gives check 1 WARNING and check 15; evicted gives check 8 HIGH; quota fixture gives CRITICAL check 3 and shows that there is no Pending pod; stuck deployment gives HIGH check 11 for 2 of 4; ArgoCD fixture gives WARNING for OutOfSync and HIGH for Degraded; over-provisioned fixture gives INFO check 7 and with `metrics=None` the check is `skipped` with reason `metrics-server not available`; healthy fixture gives exactly zero findings in pod mode and namespace mode. Also: check 14 changes cause (scheduling vs ContainerCreating) with a pod age of 9 minutes (no finding) and 11 minutes (finding), and the threshold changes with `monkeypatch.setenv("DFI_PENDING_TOO_LONG_MIN", "5")`. Every finding in every scenario has non-empty `evidence`, `tip`, `doc_ref.section` between 1 and 15, and a stable `id`.
      Files: `backend/tests/test_diagnose_rules.py`
      Verify: `cd backend && python -m pytest tests/test_diagnose_rules.py -q`.

- [ ] T4. Engine, collector and API tests.
      `backend/tests/test_diagnose_engine.py`: all 15 checks always appear in `checks`; a rule that raises becomes `error` and the others still run (use a monkeypatched rule); header counts match findings; custom rules: valid file produces findings with the rule's severity, malformed files produce exactly one `custom_rules_config_error` WARNING and no crash, missing file marks check 13 `skipped`; namespace cap note. `backend/tests/test_diagnose_api.py`: with `registry_file` and `monkeypatch.setattr(kube.subprocess, "run", ...)` returning fixture JSON per requested resource, `GET /api/diagnose/pod` and `/namespace` return 200 with the documented keys; unknown pod gives 404 `pod_not_found`; unknown cluster 404; bad namespace 422; pods call failing gives 502; metrics failing still gives 200 with check 7 skipped; ArgoCD not configured gives 200 with check 2 skipped and reason; LLM flag off gives `llm_summary` null and the app starts with no LLM library (assert `"crewai" not in sys.modules` after import of `app.main` in a subprocess-free way by checking the module name is absent). Also assert every kubectl argv the collector issued is accepted by the A2 grammar (the fake records them) and none contains the word `secrets`.
      Files: `backend/tests/test_diagnose_engine.py`, `backend/tests/test_diagnose_api.py`
      Verify: `cd backend && python -m pytest tests -q` (the whole backend suite).

## Part C. Confirm-gated deploy (the only write path)

Safety contract for every item in this part. Allowed actions: ArgoCD application refresh (`normal` only) and ArgoCD application sync. Not allowed, anywhere, in code or config: kubectl writes, rollback or undo, restart, delete, prune, force, dry-run override, bulk or wildcard targets, cluster creation. No LLM is in this path. No skip-approval flag and no auto-approve mode exist, and none may be added.

Request flow:

```
GET  /api/deploy/components?cluster=   -> catalog entries + live ArgoCD status (read token)
POST /api/deploy/plan                  -> guardrails, live app read, evidence + sha256 + expiry, audit PLAN
POST /api/deploy/execute               -> re-verify everything, audit intent, call ArgoCD (deploy token), audit result
GET  /api/audit?limit=50               -> last N audit lines (read-only)
```

Plan body: `{cluster, component, action, actor}` (`action` is a plain string checked by a guardrail, so `rollback` gives a 409 refusal with an audit line, not a 422). Execute body: `{plan_id, confirmation, actor, second_actor?}`. Both bodies use pydantic models with `extra="forbid"` and length limits.

- [ ] C1. Settings, catalog file and catalog loader.
      Add to `Settings`/`get_settings()` (at the end): `components_config_path`, `approval_ttl_minutes` (default 15, minimum 1, maximum 240), `audit_log_path`, `deploy_state_path`. Create `config/components.yaml` with a top comment block in capitals: `PLACEHOLDER CATALOG: edit every entry to match ArgoCD applications that really exist in your cluster. Nothing here is a real deployment.` Two placeholder entries (names like `example-mongodb` and `example-api`, `argocd_app` set to the same names, `chart` and `chart_version` as obvious placeholders such as `REPLACE-ME`, `cluster_environments: [dev, staging]`). `deploy/catalog.py`: `load_catalog() -> Catalog` with strict validation (only `yaml.safe_load`; top key `components`; each entry exactly the keys `name`, `description`, `argocd_app`, `chart`, `chart_version`, `cluster_environments`; `name` and `argocd_app` match `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` max 63; no `*`, `?`, `,`, `/` or whitespace in names; names unique; environments subset of `dev`, `staging`, `prod`; `chart_version` may be an empty string, meaning "do not compare"). Errors raise `CatalogError` with a clear message and the API returns 500 `catalog_error` (same style as `RegistryError`). `catalog.components_for(environment)`, `catalog.get(name)`. Do not write any "status" field into the catalog.
      Files: `backend/app/settings.py`, `config/components.yaml`, `backend/app/deploy/__init__.py` (docstring only), `backend/app/deploy/catalog.py`, `backend/app/main.py` (add a `CatalogError` handler)
      Verify: `python -m py_compile` on each Python file; `python -c "from app.deploy import catalog"` from `backend/`. Tests in CT1.

- [ ] C2. ArgoCD client: detail read, refresh, sync, separate tokens (extends the file created in B7).
      In `services/argocd_client.py` add: `resolve_deploy_token(cluster_name)` which reads `ARGOCD_DEPLOY_TOKEN_<CLUSTER>` then `ARGOCD_DEPLOY_TOKEN` and NEVER `ARGOCD_TOKEN`; `get_app(cluster, app_name, transport=None)` (read token, `GET {url}/api/v1/applications/{app}`) returning `{status, message, app}` with the same status words as `fetch_apps` plus `not_found` for HTTP 404; `refresh_app(cluster, app_name, transport=None)` (deploy token, `GET .../applications/{app}?refresh=normal`); `sync_app(cluster, app_name, revision, transport=None)` (deploy token, `POST .../applications/{app}/sync` with JSON body exactly `{"revision": <str>, "prune": false, "dryRun": false, "strategy": {"hook": {}}}`; no `force`, no `resources`, no `syncOptions`). Each write function first checks `app_name` against `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` and refuses anything else (defense in depth, the guardrail module checks too), URL-quotes the name, uses `httpx.Client(verify=verify_tls_for(url), timeout=...)`, never logs or returns a token, and builds error messages from fixed text and the HTTP status only. There must be no `delete`, `put`, `patch` or other write method anywhere in the file. Add `argocd_transport()` to `routers/deps.py` as a FastAPI dependency that returns `None`; routers pass it down; tests override it with an `httpx.MockTransport` through `app.dependency_overrides` (this is the "faked ArgoCD HTTP client", test only). Also wire `argocd_transport` into the diagnose router from B8 so the ArgoCD-aware diagnose tests can use the same override.
      Files: `backend/app/services/argocd_client.py`, `backend/app/routers/deps.py`, `backend/app/routers/diagnose.py`
      Verify: `python -m py_compile`; `cd backend && python -m pytest tests/test_api.py tests/test_guard.py tests/test_diagnose_api.py -q`. Live check later by the user: compare the two REST shapes with `https://localhost:<port>/swagger-ui` on the running ArgoCD (needs-verification-live).

- [ ] C3. Audit log and the audit endpoint.
      `deploy/audit.py`: `write(event: dict) -> None` appends ONE JSON line (`json.dumps(..., sort_keys=True, separators=(",", ":"))` plus `"\n"`) to `get_settings().audit_log_path`, opening with mode `"a"`, `encoding="utf-8"`, `newline="\n"`, creating the parent folder, flushing and `os.fsync`, all under a module `threading.Lock`. It adds `ts` (UTC, `%Y-%m-%dT%H:%M:%SZ`) and `schema: 1`. It refuses any event that has a key named like a token or password (`token`, `password`, `secret`, `authorization`, case-insensitive substring) by raising `AuditError`. If the write fails it raises `AuditError` (callers fail closed). `tail(limit)` returns the last `limit` lines parsed (cap 500, default 50), turning an unparseable line into `{"malformed": true, "raw": "<first 200 chars>"}`; a missing file returns `[]`. Event names: `PLAN`, `PLAN_REFUSED`, `EXECUTE_REFUSED`, `EXECUTE_INTENT`, `EXECUTE_RESULT`, `EXECUTE_FAILED`. Common fields: `event`, `plan_id` (or null), `cluster`, `component`, `argocd_app`, `action`, `target_revision`, `evidence_sha256`, `actor`, `second_actor`, `reason_code`, `detail`. `routers/audit.py`: `GET /audit?limit=` with `limit` validated 1..500, returns `{entries: [...], path_hint: "<relative path only>"}`. Mount it in `main.py`.
      Files: `backend/app/deploy/audit.py`, `backend/app/routers/audit.py`, `backend/app/main.py`
      Verify: `python -m py_compile`; tests in CT2.

- [ ] C4. Deterministic deploy guardrails (separate module).
      `deploy/guardrails.py`, mirroring the `GuardrailResult` and `GuardrailReport` shapes of `devops-microservices-Eksupgrade-by-agent\app\guardrails.py` (copy the idea, do not import it). Pure functions, no I/O, no LLM: `gr_cluster_registered(name, registry_entries)`, `gr_cluster_active(entry)` (registry `status == "active"`), `gr_component_in_catalog(component, catalog)`, `gr_environment_allowed(entry_environment, component_entry)`, `gr_app_name_safe(app_name, component_entry)` (equals the catalog `argocd_app`, matches the DNS-label pattern, contains none of `*?,/ ` or whitespace, not `-`-prefixed), `gr_action_allowed(action)` (exactly `refresh` or `sync` after no normalising: `Sync` and ` sync` are refused), `gr_revision_matches_catalog(live_target_revision, component_entry)` (if catalog `chart_version` is non-empty it must equal the app's `targetRevision`; the refused message says which two values differ), `gr_confirmation_phrase(expected, typed)` (exact string equality, no trimming, no case folding), `gr_actors(environment, actor, second_actor)` (actor required, 1..64 characters from `[A-Za-z0-9._@-]`; for `prod` a second actor is required and must differ after trim and lower-casing; for other environments `second_actor` is ignored), `gr_no_forbidden_fields(payload_dict)` (rejects keys `force`, `prune`, `dryRun`, `all`, `apps`, `selector`, `resources`, `syncOptions`). `run_plan_guardrails(...)` and `run_execute_guardrails(...)` run ALL checks, return a report, and `report.blocked` is true when any blocks. Each failing check has a stable `reason_code` string (for example `unknown_cluster`, `cluster_not_active`, `unknown_component`, `environment_not_allowed`, `bad_app_name`, `action_not_allowed`, `revision_mismatch`, `bad_confirmation`, `actors_invalid`, `second_actor_required`, `second_actor_same`, `forbidden_field`).
      Files: `backend/app/deploy/guardrails.py`
      Verify: `python -m py_compile backend/app/deploy/guardrails.py`; tests in CT1.

- [ ] C5. Evidence and the approval gate (plan store, TTL, hash, single use).
      `deploy/evidence.py`: `build_evidence(cluster_entry, component_entry, action, app_detail) -> dict` containing exactly: `cluster`, `environment`, `region`, `component`, `argocd_app`, `chart`, `chart_version`, `action`, `target_revision` (the app's `spec.source.targetRevision`), `live_revision` (`status.sync.revision`), `sync_status`, `health_status`, `destination_namespace`, `out_of_sync_resources` (sorted list of `{kind, namespace, name, status}` for resources whose status is not `Synced`). No timestamps and no token. `canonical(evidence) -> str` (`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)`), `sha256_hex(str)`. `deploy/gate.py` (the same idea as `approval_gate.py`: bound to target, bound to evidence hash, TTL, independent re-check):
      - `utcnow()` is a module function so tests can patch the clock.
      - `create_plan(...)` stores `{plan_id (uuid4 hex), cluster, environment, component, argocd_app, action, target_revision, evidence_json, evidence_sha256, planned_by, created_at, expires_at, status:"PLANNED"}` in `get_settings().deploy_state_path` (atomic write: temp file in the same folder, then `os.replace`; `threading.Lock`; keep at most 100 records, dropping the oldest consumed or expired first; an unreadable file raises `GateError`, it is never treated as empty).
      - `load_plan(plan_id)` validates the id format (32 hex characters) before any lookup.
      - `verify_plan_for_execute(plan, now, live_evidence_json)` returns `(ok, reason_code, detail)` and checks in this order: status is `PLANNED` (else `plan_already_used`), `sha256(evidence_json) == evidence_sha256` (else `plan_tampered`), `now <= expires_at` (else `plan_expired`), then the live evidence hash equals the stored hash (else `evidence_changed`, detail says to create a new plan), and that cluster, component, app, action and target revision in the live evidence equal those in the plan (else `target_changed`).
      - `mark_consumed(plan_id, outcome)` sets `status` to `EXECUTED` or `EXECUTE_FAILED` so the plan cannot be replayed. A failed ArgoCD call also consumes the plan (the user plans again).
      Files: `backend/app/deploy/evidence.py`, `backend/app/deploy/gate.py`
      Verify: `python -m py_compile` on both; tests in CT2.

- [ ] C6. Executor and the deploy router.
      `deploy/executor.py`: `plan(cluster_name, component, action, actor, transport)` and `execute(plan_id, confirmation, actor, second_actor, transport)` implementing the order in design D10, writing an audit line for EVERY outcome (allowed and refused) before returning. Plan: load registry entry and catalog, run plan guardrails, read the live app with the read token (`get_app`; a non-`ok` status gives a refusal `argocd_unavailable` or `app_not_found`), build evidence, create the plan, audit `PLAN`, return `{plan_id, cluster, environment, component, argocd_app, action, target_revision, evidence, evidence_sha256, expires_at, confirmation_phrase: "DEPLOY <cluster>/<component>", requires_second_actor: bool, guardrails: [{name, passed, detail}]}`. Execute: refusals raise `DeployRefused(reason_code, detail)` after auditing `EXECUTE_REFUSED`; before the action it audits `EXECUTE_INTENT` and, if that write fails, aborts with `audit_unavailable` and does NOT call ArgoCD; it needs the deploy token (`no_deploy_token` refusal otherwise, and no network call is made); then calls `refresh_app` or `sync_app`; audits `EXECUTE_RESULT` (HTTP status, accepted true/false) or `EXECUTE_FAILED`; marks the plan consumed; returns `{executed: true, action, argocd_app, argocd_http_status, message}`. `routers/deploy.py`: the three endpoints above (`GET /deploy/components`, `POST /deploy/plan`, `POST /deploy/execute`); `DeployRefused` maps to 409 `{detail, kind:"deploy_refused", reason_code}` through an exception handler in `main.py`; `AuditError`/`GateError` map to 500 `{kind:"audit_error"|"gate_error"}`; ArgoCD transport errors on execute map to 502 `argocd_error`. `GET /deploy/components` returns, per catalog entry allowed for the cluster's environment, `{name, description, argocd_app, chart, chart_version, enabled, disabled_reason, live: {argocd_status, sync_status, health_status, target_revision} | null}`; `enabled` is true only when plan guardrails would pass and the app was found; `live` is null when ArgoCD could not be read, with `disabled_reason` saying why. No status is ever invented. Update `main.py` docstring to say the portal is still unauthenticated and the deploy router is gated by the plan/confirm flow, not by login.
      Files: `backend/app/deploy/executor.py`, `backend/app/routers/deploy.py`, `backend/app/main.py`
      Verify: `python -m py_compile`; `cd backend && python -m pytest tests/test_api.py tests/test_guard.py -q`. Tests in CT4.

## Part C tests

- [ ] CT0. Make tests safe for the new state files (do this before any test in this part).
      Edit `backend/tests/conftest.py`: add an `autouse=True` fixture `isolated_state(tmp_path, monkeypatch)` that sets `AUDIT_LOG_PATH`, `DEPLOY_STATE_PATH`, `DFI_COMPONENTS_CONFIG` (to a temp copy written by the test) and `DFI_CHECKS_CONFIG` (to a temp path that does not exist unless a test writes it), and deletes `ARGOCD_DEPLOY_TOKEN`, `ARGOCD_DEPLOY_TOKEN_DEV_EU`, `ARGOCD_TOKEN`, `ARGOCD_TOKEN_DEV_EU`, `DFI_*` and `APPROVAL_TTL_MINUTES`. Additive change only; do not alter `make_entry`, `registry_file` or `client`. Add `make_component(**overrides)` and a `components_file` fixture (writes a temp catalog and sets the env var), and `argocd_app_json(**overrides)` that builds an ArgoCD application dict (test input).
      Files: `backend/tests/conftest.py`
      Verify: `cd backend && python -m pytest tests/test_api.py tests/test_guard.py -q` still passes. No test may ever write to `<repo>/.state`; add one assertion in CT4 that the repo `.state` folder does not exist after the run (skip the assertion if it existed before).

- [ ] CT1. Catalog and guardrail tests.
      `backend/tests/test_deploy_catalog.py` (valid file; every schema fault refused: unknown key, wildcard in `argocd_app`, duplicate name, bad environment, missing file, YAML syntax error) and `backend/tests/test_deploy_guardrails.py` (one parametrized test per guardrail, each with a passing case and every failing case from C4, including `Sync`, ` sync`, `rollback`, `restart`, `delete`, `sync,refresh`, `*`, `app-*`, `../x`, unknown cluster, cluster not `active`, component not for the environment, revision mismatch, phrase with a trailing space, phrase in lower case, prod with one actor, prod with `Alice` and `alice `, forbidden fields `force` and `prune`).
      Files: the two test files above
      Verify: `cd backend && python -m pytest tests/test_deploy_catalog.py tests/test_deploy_guardrails.py -q`.

- [ ] CT2. Audit, evidence and gate tests.
      `backend/tests/test_deploy_audit.py`: appends one line per call, lines parse as JSON, file is append-only across calls, a key containing `token` is refused, a write failure raises `AuditError` (point the path at a directory), `tail` honors the limit and survives a malformed line, a missing file returns `[]`. `backend/tests/test_deploy_gate.py`: same input gives the same hash; changing any evidence field changes it; a timestamp is not part of it; tampered stored evidence gives `plan_tampered`; expired plan gives `plan_expired` (patch `gate.utcnow`); consumed plan gives `plan_already_used`; changed live evidence gives `evidence_changed`; a corrupt plan store raises `GateError`; plan id with non-hex characters is rejected before lookup.
      Files: the two test files above
      Verify: `cd backend && python -m pytest tests/test_deploy_audit.py tests/test_deploy_gate.py -q`.

- [ ] CT3. ArgoCD client tests with `httpx.MockTransport` (test only).
      `backend/tests/test_argocd_client.py`: `list_apps_detail` maps operation and condition fields and `out_of_sync_resources`; `get_app` maps 200, 401/403, 404, connection error to `ok`, `unauthorized`, `not_found`, `unreachable` with no token in any message; `refresh_app` sends exactly one GET whose query is `refresh=normal` and uses the deploy token header; `sync_app` sends exactly one POST to `/sync` whose JSON body equals the body in C2 (assert `prune is False`, `"force" not in body`); the read token is never sent on a write and the deploy token is never sent on a read; `resolve_deploy_token` does not fall back to `ARGOCD_TOKEN`; invalid app names (`*`, `a/b`, `../x`) raise before any request is made (the handler counts requests and the count stays 0). A text scan of `backend/app/services/argocd_client.py` and `backend/app/deploy/` asserts none of `.delete(`, `.put(`, `.patch(`, `"DELETE"`, `"PUT"`, `"PATCH"`, `subprocess`, `kubectl` appears.
      Files: `backend/tests/test_argocd_client.py`
      Verify: `cd backend && python -m pytest tests/test_argocd_client.py -q`.

- [ ] CT4. End-to-end gate tests through the HTTP API.
      `backend/tests/test_deploy_api.py` using `client`, `registry_file`, `components_file`, a fake ArgoCD built from `httpx.MockTransport` injected with `app.dependency_overrides[deps.argocd_transport]`, and `monkeypatch.setenv` for tokens. Required cases (each asserts the HTTP status, the `reason_code` where it is a refusal, AND that an audit line with the matching event and `reason_code` was written, using `audit.tail`):
      1. Components list shows live status from the fake ArgoCD and shows `enabled: false` with a reason when ArgoCD is not configured; nothing is invented.
      2. Plan success returns `plan_id`, `evidence_sha256` (64 hex characters), `expires_at`, the required phrase `DEPLOY dev-eu/example-mongodb`; audit `PLAN`.
      3. Plan with unknown component -> 409 `unknown_component`; plan with `rollback`, `restart`, `delete`, `Sync` -> 409 `action_not_allowed`; plan for a component not allowed in the cluster environment -> 409 `environment_not_allowed`; plan when the fake app returns 404 -> 409 `app_not_found`.
      4. Execute with wrong phrase -> 409 `bad_confirmation`, fake ArgoCD saw NO write request.
      5. Execute after expiry (patch `gate.utcnow` forward) -> 409 `plan_expired`, no write request.
      6. Execute after the fake app state changed between plan and execute -> 409 `evidence_changed`, no write request.
      7. Execute for a plan whose component was removed from the catalog after planning -> 409 `unknown_component`, no write request.
      8. Prod cluster: one actor -> 409 `second_actor_required`; same name twice with different case -> 409 `second_actor_same`; two distinct names -> success.
      9. Success path for `sync` on a staging cluster: 200, `executed: true`, fake saw exactly one POST `/sync` with the deploy token and the body from C2; audit has `PLAN`, `EXECUTE_INTENT`, `EXECUTE_RESULT` in that order.
      10. Success path for `refresh`: fake saw exactly one GET with `refresh=normal`.
      11. Replay of the same `plan_id` -> 409 `plan_already_used`.
      12. No deploy token set -> 409 `no_deploy_token` and zero network calls; a read token alone never allows a write.
      13. Audit failure (point `AUDIT_LOG_PATH` at a directory after planning) -> execute fails closed with no write request.
      14. Body with `force: true` or `prune: true` -> 422.
      15. `GET /api/audit?limit=2` returns at most 2 newest entries; neither tokens nor the confirmation phrase typed by the user appear in any audit line or response body (assert by scanning the strings used in the test).
      16. ArgoCD returns 500 on sync -> 502 `argocd_error`, audit `EXECUTE_FAILED`, plan consumed.
      Files: `backend/tests/test_deploy_api.py`
      Verify: `cd backend && python -m pytest tests/test_deploy_api.py -q`, then `python -m pytest tests -q`.

- [ ] CT5. Extend the static guard tests.
      Append to `backend/tests/test_guard.py` (do not remove or loosen any existing test): the only files under `backend/app` that may import `httpx` are `services/argocd.py` and `services/argocd_client.py`; `backend/app/deploy/` and `backend/app/diagnose/` never import `subprocess`; only `services/kube.py` imports `subprocess`; `kube.ALLOWED_RESOURCES` has 12 members and no `secrets`; no file in `backend/app` contains `--force`, `prune": true`, `kubectl apply` or `rollout undo`; `main.py` mounts exactly these routers: health, clusters, namespaces, pods, argocd, diagnose, deploy, audit; every route outside `deploy` is a GET and the deploy router has exactly one GET and two POSTs.
      Files: `backend/tests/test_guard.py`
      Verify: `cd backend && python -m pytest tests/test_guard.py -q`.

## Part D. Frontend completion

Frontend facts: components live in `frontend/src/components/`, data loading uses `useLoadable(loader, key)` from `frontend/src/useLoadable.ts`, errors are `ApiError` from `frontend/src/api.ts`, pills use `<StatusPill label tone>` with CSS classes `pill pill-<tone>`, `Tone` is `green | yellow | red | gray` in `tone.ts`. Dark theme variables are in `styles.css` (`--red-bg`, `--yellow-bg` and so on). Do not add a runtime dependency. Do not add fake rows anywhere: every list is rendered from an API response, with explicit loading, empty and error states.

- [ ] D1. Types, API client, severity tones, styles, test config.
      Add to `types.ts`: `Severity = "CRITICAL" | "HIGH" | "WARNING" | "INFO"`, `Finding`, `CheckRunInfo`, `MetricsRow`, `DiagnoseHeader`, `DiagnoseResponse` (pod and namespace shapes from B7), `DeployComponent`, `DeployPlan`, `DeployExecuteResult`, `AuditEntry`. Add to `api.ts`: `diagnosePod(cluster, ns, pod)`, `diagnoseNamespace(cluster, ns)`, `deployComponents(cluster)`, `audit(limit)`, and a `postJson` helper that mirrors `fetchJson` error handling (a 409 refusal body `{detail, kind:"deploy_refused", reason_code}` becomes `ApiError(409, detail, "deploy_refused")`); `deployPlan(body)` and `deployExecute(body)` use it. Create `severity.ts` with `severityTone(sev)` returning one of `red | orange | yellow | blue` and `severityRank(sev)`; extend the `Tone` type in `tone.ts` with `orange` and `blue` (keep the existing functions and tests unchanged). Add CSS in `styles.css` for `pill-orange` and `pill-blue` (new variables `--orange-bg/fg`, `--blue-bg/fg`) following the existing pill pattern, plus classes for the findings panel (`.findings`, `.finding`, `.tip`, `.metrics-table`, `.check-list`), the warning banner (`.banner-danger`) and tabs (`.tabs`, `.tab`, `.tab-active`). In `vite.config.ts` change only `include` to `["src/**/*.test.{ts,tsx}"]`.
      Files: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/severity.ts`, `frontend/src/tone.ts`, `frontend/src/styles.css`, `frontend/vite.config.ts` (all under `c:\Devops\Repository\Developer-friendly-infra\`)
      Verify: `cd frontend && npm test` (existing `tone.test.ts`, `format.test.ts` still pass) and `npm run build` (type check). Offline fallback: re-read `tone.ts` and check `podTone` and `syncTone` callers still type-check against the widened `Tone`.

- [ ] D2. Findings panel in the Nokia-screen style (pure presentational).
      `components/FindingsPanel.tsx` takes `{ result: DiagnoseResponse; onClose?: () => void }` and renders no data of its own. Sections in this order: (1) header strip: pod name, phase, restarts, error count, warning count, "checks executed N of 15"; (2) findings sorted by `severityRank`: each shows a severity pill (CRITICAL red, HIGH orange, WARNING yellow, INFO blue, label text always shown), check name, subject (`namespace/pod/container`), message, a `Tip:` line, a collapsed `<details>` with the raw `evidence` as formatted JSON and the `doc_ref` text ("K8-Real-scenario-debug.md, section N"); (3) derived metrics table (the 8 metrics, `null` shown as `n/a`); (4) checks list with all 15 entries, a text mark `executed` / `skipped` / `error` (plus a symbol), and the skip reason; (5) optional `llm_summary` block, shown only when the field is a non-empty string, labelled "AI summary (does not change severity)". Empty state when there are no findings: "No findings. 15 checks ran" (using the real executed count; if some were skipped it says how many and lists the reasons below). Namespace mode: `components/NamespaceDiagnose.tsx` renders the namespace header, a table of pods with their counts (each row has a button calling `onOpenPod(name)`), and the namespace-level findings using the same finding component. Extract `FindingItem`, `MetricsTable` and `ChecksList` into `components/findings/` so the tests can render them alone.
      Files: `frontend/src/components/FindingsPanel.tsx`, `frontend/src/components/NamespaceDiagnose.tsx`, `frontend/src/components/findings/FindingItem.tsx`, `frontend/src/components/findings/MetricsTable.tsx`, `frontend/src/components/findings/ChecksList.tsx`
      Verify: `cd frontend && npm run build`. Tests in D6.

- [ ] D3. Diagnose button per pod and the namespace summary.
      `PodTable.tsx`: add props `onDiagnose: (pod: string) => void` and `diagnosingPod: string | null`; add a last column "Diagnose" with a `<button className="btn">Diagnose</button>` per row (disabled while that pod is loading). `ClusterDetail.tsx`: add state for the open diagnosis (`{kind:"pod", name} | {kind:"namespace"} | null`), a "Diagnose namespace" button in the pod panel controls, and render a `useLoadable` result (loading, error through `ErrorBanner` with retry, ready through `FindingsPanel` or `NamespaceDiagnose`) under the table. Selecting another namespace or cluster closes the panel. Each call uses a key that includes cluster, namespace and pod so a stale response is never shown for another pod.
      Files: `frontend/src/components/PodTable.tsx`, `frontend/src/components/ClusterDetail.tsx`
      Verify: `cd frontend && npm run build` and `npm test`. UNVERIFIED in a browser until the user runs the portal (list it).

- [ ] D4. Deploy tab: component list and plan view.
      In `ClusterDetail.tsx` add two tabs, "Pods and diagnose" and "Deploy" (buttons with `role="tab"`, keyboard focusable). `components/DeployTab.tsx`: first a warning banner that is always visible: "This tab changes a real cluster. A sync or refresh runs against ArgoCD on <cluster> (<environment>). Plan first, read the evidence, then type the confirmation phrase." Then the component list from `deployComponents`: name, description, chart and version, ArgoCD sync and health pills from the live data (or "ArgoCD data unavailable: <reason>"), an enabled/disabled indicator with the reason, and radio buttons for action `refresh` or `sync`, and a "Plan" button (disabled when the component is disabled). Clicking Plan calls `deployPlan` and shows the result: target (cluster, component, ArgoCD app, target revision), the evidence table, the `evidence_sha256`, the expiry time with a live countdown (computed from `expires_at`, recomputed on a timer, and a visible "Plan expired, create a new one" state), and the required phrase text. A plan refusal (409) shows the `detail` and `reason_code` in an error banner. Empty catalog: "No components in config/components.yaml for this environment."
      Files: `frontend/src/components/DeployTab.tsx`, `frontend/src/components/DeployPlanView.tsx`, `frontend/src/components/ClusterDetail.tsx`
      Verify: `cd frontend && npm run build`. UNVERIFIED in a browser.

- [ ] D5. Deploy tab: typed confirmation, execute, result and audit list.
      `components/DeployConfirm.tsx`: an input for the actor name, a second actor input shown only when `requires_second_actor` is true, and a text input for the confirmation phrase. The phrase is NEVER pre-filled and there is no copy-phrase button. The Execute button is enabled only when the typed text equals the required phrase exactly, an actor name is present, the second actor is present when required, and the plan has not expired (this is a convenience; the backend repeats every check and its refusal is shown verbatim). On success show the result block (`executed`, action, ArgoCD HTTP status, message) and a note "Request sent. Watch the ArgoCD panel for the result". A 409 shows the refusal reason and `reason_code`. After any outcome the plan view is cleared because the plan is single use. `components/AuditList.tsx`: renders `GET /api/audit?limit=20` newest first, with columns time, event, actor, target, outcome or reason; a "Refresh" button; loading, empty ("No audit entries yet") and error states; the list reloads after every plan and execute. Update the page header text in `App.tsx`, which currently says "Nothing here changes infrastructure", to say the Deploy tab can change a real cluster after a typed confirmation, and that the backend has no login (localhost only).
      Files: `frontend/src/components/DeployConfirm.tsx`, `frontend/src/components/AuditList.tsx`, `frontend/src/components/DeployTab.tsx`, `frontend/src/App.tsx`
      Verify: `cd frontend && npm run build` and `npm test`. UNVERIFIED in a browser.

- [ ] D6. Vitest tests (sample data is test only).
      Create `frontend/src/test-fixtures/findings.sample.json` with one namespace-level and one pod-level response that matches the `DiagnoseResponse` type: a CRITICAL OOM finding (512Mi, exit 137, tip suggests 1Gi), a HIGH, a WARNING and an INFO finding, the 8-metric table with one `null`, and 15 check entries of which two are `skipped` with a reason (`metrics-server not available`), plus a second sample with zero findings. Only `*.test.tsx` files may import from `test-fixtures/` (add a test that scans `src/` non-test files for the string `test-fixtures` and expects none). `frontend/src/components/FindingsPanel.test.tsx` uses `renderToStaticMarkup` from `react-dom/server` and asserts: each severity renders its pill class (`pill-red`, `pill-orange`, `pill-yellow`, `pill-blue`) and its text label; the order is CRITICAL, HIGH, WARNING, INFO; the Tip line text appears; evidence JSON and the doc reference appear inside `<details>`; the metrics table shows `n/a` for the null metric; the checks list shows 15 entries with 13 `executed` and 2 `skipped` and shows the skip reason; the zero-findings sample renders the empty-state text with the real executed count; the AI summary block is absent when `llm_summary` is null and present when set. `frontend/src/severity.test.ts` covers `severityTone` and `severityRank`. `frontend/src/components/DeployConfirm.test.tsx` tests the pure helper `canExecute({typed, required, actor, secondActor, requiresSecond, expiresAt, now})` exported from `DeployConfirm.tsx`: exact match only, trailing space fails, lower case fails, expired fails, second actor required for prod.
      Files: `frontend/src/test-fixtures/findings.sample.json`, `frontend/src/components/FindingsPanel.test.tsx`, `frontend/src/severity.test.ts`, `frontend/src/components/DeployConfirm.test.tsx`
      Verify: `cd frontend && npm test`, then `npm run build`. If JSON import fails the type check, add `"resolveJsonModule": true` to `frontend/tsconfig.app.json` (read it first; the current file does not set it).

## Part E. Documentation

- [ ] E1. Update `README.md`.
      Replace the Phase 1 "Safety stance" and "Phase 1 scope" text that says "No deploy endpoint exists" and "Read-only portal" with accurate Phase 2 text (read-only diagnose, one gated write path, still unauthenticated and localhost only). Replace the top ASCII diagram with the full flow: `provision.sh -> EKS + ArgoCD -> registry/clusters.json -> backend (read-only kubectl + ArgoCD read token) -> portal -> diagnose (15 checks) -> gated deploy (plan -> typed phrase -> ArgoCD refresh/sync with deploy token) -> .state/audit.log`. Add a phase status table with two columns that stay honest: "Written" and "Verified". Every Verified cell says `not run` unless a command really ran in this work; Phase 1 and Phase 2 rows for Terraform, scripts, registry, backend, frontend, diagnose, deploy, docs. Keep the cost note from A4. Add a layout block with the new folders (`config/`, `docs/`, `.state/` runtime). Link `docs/diagnose-checks.md`, `docs/safety-model.md`, `VERSIONS.md`, `RUNBOOK.md`. Update the Phases list (Phase 3 in the old text was the gated deploy; it is now Phase 2, and auth/RBAC remains later).
      Files: `c:\Devops\Repository\Developer-friendly-infra\README.md`
      Verify: re-read; every link target exists (read each linked path with the file tool); no sentence claims something was tested. No command.

- [ ] E2. `docs/diagnose-checks.md`.
      A table with one row per check (15 rows): number, name, exact signal read (kubectl resource and JSON field path, or ArgoCD field), severity logic, threshold env var names (from section 4), skip conditions, and the spec section pointer. Build it from the rule table in this plan and from the final code (re-read `rules_*.py` and fix any difference in favor of the code). Add sections: derived metrics definitions (formulas), `config/checks.yaml` field reference with the allowed operators and metrics and one valid and one invalid example, what "skipped" means, why `kubectl top` is replaced by the metrics API `get` (D2), the optional LLM summary flag and its limits, and a short "what this does not check" list (services and endpoints selectors, node pressure, secrets existence, logs).
      Files: `c:\Devops\Repository\Developer-friendly-infra\docs\diagnose-checks.md`
      Verify: re-read against `rules_*.py`; spot check 5 rows against the code. No command.

- [ ] E3. `docs/safety-model.md`.
      Describe each layer and where it lives: get-only kubectl grammar and allow-list (`kube.py`, tests `test_kube.py`), account guard `589389425618` (`common.sh`, Terraform), typed confirmation in `provision.sh` and `destroy.sh`, registry locking, cost safety, ArgoCD role split (read-only account and deploy account, two tokens), deploy guardrails (allow-lists, deterministic, no LLM), approval gate (target binding, evidence SHA-256, TTL, typed phrase `DEPLOY <cluster>/<component>`, single use, independent re-verification at execute), fail-closed audit, append-only audit log, two-actor rule for `prod`. Then "Known limits", stated plainly: identity is honor system locally (no authentication on `actor`), enforcement of real identity would be CI with required reviewers (same limit as the user's `guarded-eks-upgrade-agent` project); the backend has no login so anyone who can reach port 8000 can call plan and execute (keep it on 127.0.0.1); the audit file is plain JSONL that a local user can edit (it is evidence, not tamper-proof); a single backend process is assumed; EKS control plane upgrades are not part of this tool and are irreversible elsewhere; nothing in Phase 1 or Phase 2 has been verified against a live cluster or live ArgoCD; the two ArgoCD REST shapes and RBAC lines need a live check. Include the list of things that do not exist on purpose: skip-approval flag, auto-approve, rollback, restart, delete, prune, force, bulk or wildcard targets, cluster creation from the portal.
      Files: `c:\Devops\Repository\Developer-friendly-infra\docs\safety-model.md`
      Verify: re-read against `deploy/gate.py` and `deploy/guardrails.py`; each layer named has a real file path. No command.

- [ ] E4. Extend `RUNBOOK.md` with the ordered Phase 2 commands (after A4 and A5 are done, so the numbering is final).
      Add the ordered sequence the user runs once AWS access is back, each step with "expect" and "stop if": (1) the three verification commands: `aws sts get-caller-identity`, `terraform version`, `kubectl version --client`, with the expected account `589389425618`; (2) validate offline first: `terraform fmt -check -recursive`, `terraform init -backend=false` and `terraform validate` in `terraform/`, `python -m pytest` in `backend/` and in `registry/tests`, `npm install`, `npm test`, `npm run build` in `frontend/`, `bash -n scripts/*.sh`, `bash scripts/verify-local.sh`; commit the generated lockfiles; (3) set `TF_STATE_BUCKET`; (4) `./scripts/provision.sh dev-eu staging` (COSTS MONEY); (5) read-only ArgoCD account and token (from A5); (6) edit `config/components.yaml` to real ArgoCD app names and create the matching apps; (7) start backend then frontend; (8) diagnose a pod and a namespace in the portal and compare with `kubectl describe pod`; (9) deploy: export the deploy token only now, Plan, read the evidence, type the phrase, Execute, then read the audit tab and `.state/audit.log`; (10) `./scripts/destroy.sh dev-eu` and the two leftovers checks to stop paying. Add the `DFI_*` variables table and say which are optional. Add troubleshooting rows: deploy refusals by `reason_code` (`plan_expired`, `evidence_changed`, `no_deploy_token`, `second_actor_required`, `bad_confirmation`), `checks.yaml` config error finding, and "metrics-server not available" (how to see whether the metrics API exists: `kubectl get apiservices | grep metrics`, read only).
      Files: `c:\Devops\Repository\Developer-friendly-infra\RUNBOOK.md`
      Verify: re-read the whole file and check step numbers, cross references and that no step uses `terraform apply` or `destroy` directly (only the scripts). No command.

## Part F. Close-out artifacts

- [ ] F1. Write `c:\Devops\Repository\devops-microservices-platform\.agents\tasks\phase2-idp\verification.md` and `SUMMARY.md`.
      `verification.md`: a table with one row per backlog item (id, command, result `PASS` / `FAIL` / `UNVERIFIED`, short note). Only `PASS` when a command ran in this step and printed success; otherwise `UNVERIFIED` with the exact command for the user. Include the gap ledger from section 2 with a final status column using only these words: `written, unverified`, `verified by test run`, `not done`. Copy the command block from section 1. `SUMMARY.md`: what was built (by file writing), what ran and passed (probably nothing, say so), the UNVERIFIED list, the decisions the user should look at (D2 metrics API addition to the kubectl allow-list, D8 ArgoCD REST shapes, D14 PyYAML range, placeholder catalog), the statement that `terraform/.terraform.lock.hcl` and `frontend/package-lock.json` must be generated by the user running `terraform init` and `npm install`, and the exact git commands for the user (below). State that git could not be run, no repository or commit was created or checked, and no push was made.
      Git commands to write into SUMMARY.md (for the user to run; do not run them):
      ```
      cd /c/Devops/Repository/Developer-friendly-infra
      git status
      git checkout -b phase2-idp
      python -m pip install -r backend/requirements-dev.txt
      bash scripts/verify-local.sh
      git add scripts/destroy.sh scripts/argocd-token.sh backend config docs frontend README.md RUNBOOK.md VERSIONS.md .gitignore
      git commit -m "feat: phase 2 diagnose engine and confirm-gated ArgoCD deploy"
      ```
      (Phase 1 was never committed per its SUMMARY.md. If `git status` says "not a git repository", run the Phase 1 block from `phase1-idp\SUMMARY.md` first.)
      Files: `verification.md`, `SUMMARY.md` under the phase2-idp artifact folder
      Verify: re-read both; search them for the words "passed", "validated", "committed" and make sure each use is true.

## Ordered backlog (work one pass per item, top to bottom)

Part A, close Phase 1 gaps
- [ ] A1. `destroy.sh`: `DFI_ENVIRONMENT` instead of inherited `ENVIRONMENT`
- [ ] A2. `kube.py`: strict grammar plus resource allow-list (no `secrets`, no commas)
- [ ] A3. `backend/tests/test_kube.py` guard tests (retry once, fallback `test_kubectl_guard.py`, else stop and report)
- [ ] A4. RUNBOOK reorder, Python 3.12/3.13, cost-estimate note (RUNBOOK, README)
- [ ] A5. RUNBOOK read-only and deploy ArgoCD accounts; `argocd-token.sh` comment; backend README token notes
- [ ] A6. `VERSIONS.md`, requirements header notes, lockfile statement, `.state/` in `.gitignore`

Part B, diagnose engine
- [ ] B1. Package scaffold, diagnose settings, PyYAML range, `config/checks.yaml`
- [ ] B2. Models, quantity parsing, derived facts
- [ ] B3. Strict `checks.yaml` loader
- [ ] B4. Rules 1, 5, 9, 10, 12
- [ ] B5. Rules 4, 6, 8, 14, 15
- [ ] B6. Rules 2, 3, 7, 11, 13
- [ ] B7. Engine, collector, ArgoCD detail reader, optional LLM summary
- [ ] B8. Diagnose routers and wiring, backend README
- [ ] T1. Sample fixtures
- [ ] T2. Tests: quantities, facts, checks loader
- [ ] T3. Tests: one per rule scenario
- [ ] T4. Tests: engine and diagnose API

Part C, confirm-gated deploy
- [ ] C1. Deploy settings, `config/components.yaml`, catalog loader
- [ ] C2. ArgoCD client write side, separate tokens, transport dependency
- [ ] C3. Audit log and `GET /api/audit`
- [ ] C4. Deterministic deploy guardrails
- [ ] C5. Evidence and approval gate
- [ ] C6. Executor, deploy router, wiring
- [ ] CT0. Test isolation in `conftest.py`
- [ ] CT1. Catalog and guardrail tests
- [ ] CT2. Audit and gate tests
- [ ] CT3. ArgoCD client tests
- [ ] CT4. End-to-end gate tests
- [ ] CT5. Extended static guard tests

Part D, frontend
- [ ] D1. Types, API, severity tones, styles, vitest include
- [ ] D2. Findings panel and namespace summary components
- [ ] D3. Diagnose button and panel wiring
- [ ] D4. Deploy tab: list and plan view
- [ ] D5. Deploy tab: confirmation, execute, result, audit list, header text
- [ ] D6. Vitest tests

Part E, docs
- [ ] E1. README
- [ ] E2. `docs/diagnose-checks.md`
- [ ] E3. `docs/safety-model.md`
- [ ] E4. RUNBOOK Phase 2 ordered commands

Part F
- [ ] F1. `verification.md` and `SUMMARY.md` with the git commands

## Open assumptions (checked while planning, or not checkable offline)

1. The spec file named in the task (`Prepare-now\K-Real-scenario-debug.md`) does not exist. `Self-study-before-interview\K8-Real-scenario-debug.md` has the 15 sections and was used. `K8-Namespace-deployment.md` was not needed in detail; owner chains use standard `ownerReferences` (pod to ReplicaSet to Deployment).
2. `eks-cluster-argocd\eks-cluster-argocd\argocd.sh` is not in the readable workspace, so the ArgoCD install flow was taken from this project's own `provision.sh` and `common.sh` (pinned `ARGOCD_VERSION`, `argocd` namespace, `argocd-server` service). If the coder can read the other file, it changes nothing in this plan.
3. `devops-microservices-crewAi\app\tools\*.py` were used for ideas only (event field selectors, exit code meanings). `incident_tools.py` builds shell strings, so none of it may be imported or copied as code.
4. The ArgoCD REST shapes (refresh as a GET with `refresh=normal`, sync as a POST with the body in C2), the RBAC lines in A5 and the `account can-i` output are from documentation and memory. They are needs-verification-live.
5. `kubectl get pods.metrics.k8s.io -n <ns> -o json` is assumed to work when metrics-server is installed. The Phase 1 cluster does not install metrics-server, so on a fresh cluster checks 7 and the usage part of 9 will be `skipped`. That is correct behavior, not a bug. Installing metrics-server is out of scope.
6. Phase 1 code was read for this plan: `kube.py`, `argocd.py`, `settings.py`, `main.py`, `registry.py`, `pods.py`, `routers/{argocd,pods,deps}.py`, `agent_tools.py`, `tests/{conftest,test_api,test_guard}.py`, `scripts/{destroy,common,argocd-token,verify-local}.sh`, the frontend `App.tsx`, `api.ts`, `types.ts`, `tone.ts`, `useLoadable.ts`, `PodTable.tsx`, `ClusterDetail.tsx`, `vite.config.ts`, `tsconfig.app.json`. `routers/namespaces.py`, `routers/clusters.py`, `routers/health.py`, `tests/test_argocd.py`, `tests/test_pods.py` and the Terraform files were not opened. The coder must read `routers/namespaces.py` and `tests/test_argocd.py` before items A2 and B7.
