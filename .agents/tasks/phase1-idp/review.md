# Phase 1 IDP portal: read-only EKS provisioning, registry and dashboard

Adds a single-stack Terraform (VPC + EKS 1.35, one `t3.medium` node group, S3 state with `use_lockfile`), paired `provision.sh` / `destroy.sh`, a stdlib registry helper, a read-only FastAPI backend (five GET endpoints) and a React dashboard. All seven gates pass on a static read of the code. Nothing has been executed: `verification.md` records every build, test, `terraform validate` and shell check as NOT RUN because the coder's shell was down, and the folder is not a git repo. The reviewer did not re-run anything either (per instructions), so APPROVED is a design and code-reading verdict, not an "it works" verdict.

Watch for: (1) zero executed verification, so first-run failures in `terraform validate`, `tsc -b`, `pytest` and the shell scripts are likely (confirmed, per verification.md); (2) `backend/tests/test_kube.py` was never written, so the "write verbs are rejected" behaviour of `run_kubectl` has no direct test (confirmed); (3) the ArgoCD token is an admin session token, so "read-only" for ArgoCD rests only on the backend issuing GETs (confirmed, `argocd-token.sh`).

**Verdict**: APPROVED

## High-level view

The write path is closed deterministically. Every kubectl call goes through one function that uses an argv list with `shell=False`, accepts only the `get` verb, and validates every argument. The cluster parameter is an allowlist lookup against the registry and the namespace is regex-checked. No router defines anything other than GET, `deploy_tools.py` is not imported anywhere, and the CrewAI wrappers live in a module `main.py` never imports (try/except guard, AST test covering both).

Cost handling targets orphaned infra. The registry entry is written before `terraform apply`, an ERR/INT/TERM trap marks it `failed` and prints the destroy command, and `destroy.sh` removes the entry only after `terraform destroy` succeeds, otherwise leaving `destroy_failed`. Sizing matches the plan (`t3.medium`, 2/2/3, single NAT, two AZs, logging off, tags via provider defaults and both modules), the account is pinned in provider and scripts, and the API endpoint is limited to the caller's `/32` with `0.0.0.0/0` rejected in HCL and shell.

The backend and frontend render only what the registry, kubectl and ArgoCD return, with explicit empty and error states. Test fixtures exist only under `tests/`. The residual risk is operational: none of it has been run.

<details>
<summary>Issues (7)</summary>

1. **No executed verification** (confirmed) — run `bash scripts/verify-local.sh` (or the block at the bottom of `verification.md`) before the first provision and fix whatever `terraform fmt`/`validate`, `tsc -b` and `pytest` report. Then commit; the folder is not a git repo yet.
2. **Missing `test_kube.py`** (confirmed) — add tests that `run_kubectl` rejects `apply`, `delete`, `rollout`, `patch`, `exec`, bad context names and injected arguments, and builds an argv list with `shell=False`. Plan section 0.3 required this proof; `test_guard.py` only checks the `READ_ONLY_VERBS` constant.
3. **Admin-scoped ArgoCD token** (confirmed) — `argocd-token.sh` logs in as `admin`, so the token in the backend's environment can write to ArgoCD. Before Phase 2, create a read-only ArgoCD account/role and issue its token instead.
4. **`ENVIRONMENT` env var leaks into destroy** (likely) — `destroy.sh` uses `ENVIRONMENT="${ENVIRONMENT:-dev}"` when there is no registry entry (orphan recovery). A shell with `ENVIRONMENT=production` exported fails Terraform's `environment` validation and ends in `destroy_failed`. Use a script-specific variable name.
5. **Loose kubectl token regex** (likely) — `_TOKEN_RE` in `kube.py` permits commas, so `get pods,secrets` would pass validation if a future caller supplied it. No current router does; add an explicit resource allowlist (`namespaces`, `pods`).
6. **No lockfiles committed** (confirmed) — `terraform/.terraform.lock.hcl` and `frontend/package-lock.json` do not exist, so provider and npm versions float on first run. Generate and commit both after `verify-local.sh` passes. The npm pins (Vite 8, vitest 5, plugin-react 6, TS 5.9) have never been installed together.
7. **RUNBOOK inconsistencies** (confirmed) — step 3 says to start the backend "after step 4" though the steps run the other way, and it asserts Python 3.14 works for the portal, which is untested. Reorder or reword, and recommend 3.12/3.13 only.

</details>

<details>
<summary>Details</summary>

## Read-only enforcement in `kube.py`

`run_kubectl` is the only code that spawns kubectl. It rejects any verb outside `{"get"}`, any flag outside `-n`, `-A`, `--all-namespaces`, and any non-plain token, then appends `-o json` itself. The only test touching this directly is the constant check in `test_guard.py`; `test_api.py` monkeypatches `subprocess.run` for success and failure mapping, and nothing proves that `apply` or an injected argument is refused. The code reads correct, so this is a test gap, not a defect.

The token regex permits commas, so a Phase 3 author could widen what `get` reaches (for example `pods,secrets`) without tripping validation. An explicit resource allowlist closes that.

## ArgoCD token scope

The token is a session token for the `admin` user, minted from the initial admin password. The backend only issues GET requests, but the credential in its environment is not read-only. Combined with an unauthenticated backend (documented, meant to run on 127.0.0.1), any local process that can reach port 8000 can read cluster and ArgoCD state, and any process that can read the backend's environment can administer ArgoCD. Acceptable for a single-user laptop tool; it must change before multi-user hosting or any write endpoint.

## Orphan-recovery destroy and untagged state bucket

In the orphan-recovery path (no registry entry), `destroy.sh` falls back to `ENVIRONMENT="${ENVIRONMENT:-dev}"`, which picks up any `ENVIRONMENT` already exported in the user's shell and feeds it to Terraform's validated `environment` variable. A value outside dev/staging/prod fails the destroy at the moment teardown matters most.

The S3 state bucket created in RUNBOOK step 1 is untagged and left behind on purpose (documented). It is the one resource outside the `Project` tag, so the tag-based leftovers check will not list it.

## Terraform inputs unvalidated

Module input names were checked against upstream `variables.tf` by reading only. `terraform validate` was never run, so a wrong v21 input name would surface at first `init`/`validate`, and the missing lockfile means provider versions are resolved fresh on first run.

</details>

<details>
<summary>File map</summary>

- `terraform/{provider,variables,locals,data,vpc,main,outputs}.tf`: single-stack VPC + EKS, S3 partial backend, account pin, tags
- `scripts/provision.sh`, `scripts/destroy.sh`: paired lifecycle with typed confirmation, account guard, registry bookkeeping
- `scripts/common.sh`: shared helpers, DRY_RUN support, CIDR and name validation
- `scripts/argocd-portforward.sh`, `scripts/argocd-token.sh`: loopback-only ArgoCD access and session token
- `scripts/verify-local.sh`: read-only local verification (no terraform plan/apply, aws or kubectl)
- `registry/registry.py`: atomic, locked, schema-validated cluster registry CLI
- `backend/app/services/{kube,pods,argocd,registry}.py`: read-only kubectl, pod shaping, ArgoCD REST, registry reads
- `backend/app/routers/*.py`, `backend/app/main.py`: five GET endpoints and error handlers
- `backend/app/agent_tools.py`, `backend/app/_toolshim.py`: guarded, unmounted read-only CrewAI wrappers
- `backend/tests/*`: API, pods, ArgoCD and static-guard tests (no `test_kube.py`)
- `frontend/src/**`: React dashboard, API client, tone/format helpers
- `README.md`, `RUNBOOK.md`: scope, safety stance, user-run commands

</details>
