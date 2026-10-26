# Phase 1 IDP: verification record

Repo: `c:\Devops\Repository\Developer-friendly-infra`

## Summary

**Nothing was verified by execution.** The shell tool (`execute_bash`) returned `Exit Code: -1` with empty
output for every call in this session (`echo`, `pwd`, `git --version`, `ls`, `git status`). No command ran.
All files were written with the file tools only. No validation output below is fabricated; every check
is listed as NOT RUN.

## Not done because there was no shell (all UNVERIFIED)

| Item | Status |
|------|--------|
| `git init -b main`, initial `.gitignore`/`.gitattributes` commit on `main` | NOT RUN |
| `git checkout -b phase1-idp` and per-item commits | NOT RUN. **No commit exists; the folder is not a git repo** |
| `git update-index --chmod=+x scripts/*.sh` | NOT RUN |
| `terraform fmt -check -recursive` in `terraform/` | NOT RUN |
| `terraform init -backend=false` and `terraform validate` | NOT RUN (so `.terraform.lock.hcl` was not generated) |
| `python -m py_compile` on backend `.py` files | NOT RUN |
| `python -m pytest registry/tests` and `backend/` | NOT RUN |
| `npm install`, `npm test`, `npm run build` in `frontend/` | NOT RUN (no `package-lock.json` either) |
| `bash -n scripts/*.sh`, `shellcheck` | NOT RUN |
| Sandbox dry run of `provision.sh` / `destroy.sh` with stub PATH | NOT RUN |
| `bash scripts/verify-local.sh` | NOT RUN |

No cloud-affecting command was attempted (no terraform apply/plan, aws, kubectl, argocd).

## Re-check of the shell (after the parent's go-ahead)

`git --version` was run once more and again returned `Exit Code: -1` with empty output. The shell is still
down for this step. Everything in the table above remains **UNVERIFIED** (not run), and nothing has been
committed: there is no git repository in the folder. The user must run the commands at the bottom of this file.

## Known gap: one test file is missing (decision: skipped)

`backend/tests/test_kube.py`: **not written, write was refused.** Both attempts were refused by the permission
layer ("Permission flow exceeded 20 approval rounds; the call still requires approval for ...test_kube.py").
The user decided to skip it; I did not retry or work around it. It would have covered: write verbs rejected,
injected arguments rejected, bad context rejected, argv list with `shell=False`, nonzero exit/timeout/
missing binary/invalid JSON mapped to `KubectlError`. Coverage that does exist: `test_api.py` (404/422/502/
500/empty registry/health), `test_pods.py`, `test_argocd.py`, `test_guard.py` (static guard on `app/`).
`test_guard.py::test_read_only_verbs_is_exactly_get` covers the verb allowlist constant only.

## What I did check (by reading, not running)

- Looked up current versions from public registries via web fetch:
  - Terraform modules: `terraform-aws-modules/eks/aws` 21.29.0 (latest), `terraform-aws-modules/vpc/aws` 6.7.3 (latest GitHub release).
  - EKS variable names used in `terraform/main.tf` (`name`, `kubernetes_version`, `addons` incl. `before_compute`, `endpoint_public_access`, `endpoint_private_access`, `endpoint_public_access_cidrs`, `enabled_log_types`, `create_cloudwatch_log_group`, `kms_key_deletion_window_in_days`, `enable_cluster_creator_admin_permissions`, `eks_managed_node_groups`, `subnet_ids`, `tags`) were confirmed against `variables.tf` at tag `v21.29.0`.
  - Kubernetes 1.35 is in EKS standard support until 2027-03-27 (AWS docs page).
  - ArgoCD latest release `v3.5.6` (GitHub API), used as the pinned default.
  - PyPI: fastapi 0.161.1, uvicorn 0.54.0, httpx 0.28.1, pytest 9.1.1. npm: react/react-dom 19.3.1, vite 8.3.5, @vitejs/plugin-react 6.1.2, vitest 5.0.5, @types/react 19.3.0, @types/react-dom 19.3.0.
  - TypeScript: npm latest is 7.0.2; I pinned **5.9.3** instead, because I could not test `tsc -b` with 7.x and the Vite template config is known on 5.x. This is a deliberate, untested deviation from "latest".
  - Hourly cost components (0.10 + 0.045 + 2 x 0.0416) were recalled, NOT re-checked against the AWS pricing pages.
- Compatibility of the npm set (Vite 8 + plugin-react 6 + vitest 5 + TS 5.9) is unverified.

## Things most likely to fail on first run

1. `terraform fmt -check`: I aligned `=` by hand; run `terraform fmt -recursive` if it complains.
2. `terraform validate`: provider constraint `>= 6.59, < 7.0` and module inputs are from docs, not a real init.
3. `npm run build`: strict TS, `noUnusedLocals`, pinned versions never installed together.
4. `pytest`: `backend/tests` imports `.conftest` (package-style tests with `__init__.py`).
5. Shell scripts: never executed, not even `bash -n`. Paths under Git Bash with native Windows Python
   (`REGISTRY_PATH` is converted with `cygpath -w` when available).

## Run this yourself (all read-only, no AWS)

```
cd /c/Devops/Repository/Developer-friendly-infra
git init -b main
git add .gitignore .gitattributes && git commit -m "chore: initial gitignore"
git checkout -b phase1-idp
(cd terraform && terraform fmt -recursive && terraform init -backend=false && terraform validate)
python -m pip install -r backend/requirements-dev.txt
bash scripts/verify-local.sh
git add -A && git commit -m "feat: phase 1 IDP portal (terraform, scripts, registry, backend, frontend, docs)"
```

Check `git config user.name` / `user.email` first; I did not set or invent an identity.
