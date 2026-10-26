# Phase 1 Implementation Plan: Developer-Friendly Infra (self-service IDP portal, foundation)

Deliverable repo: `c:\Devops\Repository\Developer-friendly-infra` (brand new, empty, no git history).
Shell: Git Bash on Windows. Use absolute paths in all tool calls.
Fixed facts: AWS account `589389425618`, region `us-east-1`, Terraform latest, kubectl latest.

This plan was produced from code actually read in the three reference repos (findings below). Nothing in the target folder exists yet.

---

## 0. HARD RULES for the build agent and the reviewer (read first)

### 0.1 Never create cloud resources or spend money
The build agent and reviewer MUST NEVER run any of these, in any form, even "just to test":

- `terraform apply`, `terraform destroy`, `terraform plan` (plan needs live AWS creds and a backend), `terraform import`, `terraform init` WITH a backend (use `-backend=false` only)
- `aws ...` of any kind (including `aws sts`, `aws eks update-kubeconfig`, `aws s3 ...`)
- `kubectl ...` of any kind (including `kubectl apply/get/config`), `argocd ...`
- `./scripts/provision.sh` or `./scripts/destroy.sh` without `DRY_RUN=1` AND the stub-PATH sandbox described in item 4
- `uvicorn` pointed at a real kubeconfig (tests use monkeypatched subprocess; do not start the server against real clusters)

Allowed read-only validation only:
`terraform fmt -check -recursive`, `terraform init -backend=false`, `terraform validate`, `python -m py_compile`, `python -m pytest`, `npm install` / `npm run build` / `npm test`, `bash -n`, `shellcheck` (if installed), `git` local commands, registry/doc web lookups for version numbers.

The USER runs every live command, in their own terminal (see RUNBOOK.md, item 8).

### 0.2 No mock or fake data in the product
- No fabricated clusters, pods, apps, costs, or sample rows anywhere the portal can serve or render. Empty or error states render honestly ("No clusters registered yet", "ArgoCD not configured").
- Unit-test fixtures (e.g. a `kubectl get pods -o json` shaped input) are allowed ONLY under `tests/` directories, labelled as test inputs, and must never be importable by `app/` or `src/` runtime code.
- `registry/clusters.json` is runtime state written by `provision.sh`. Do NOT commit a sample or seeded one.

### 0.3 Read-only portal, no agent-driven writes
- Phase 1 backend performs ONLY read operations. Enforce this deterministically in code (item 5): `kube.run_kubectl` has an allowlist of verbs (`get` only) and rejects anything else. A unit test proves `apply`, `delete`, `rollout`, `patch`, `exec` are rejected.
- Do NOT import or reuse anything from `devops-microservices-crewAi/app/tools/deploy_tools.py` (it contains `rollback_deployment` / `restart_deployment`, which execute from an LLM call with no approval gate; the repo's own notes flag this as its biggest gap).
- Phase 3 deploy is OUT of scope. Structure only so it is a clean add later (routers/services split, item 5). Do not add stub deploy endpoints.

### 0.4 Cost safety is first-class
Paired provision/destroy, small node group, single NAT, tags on everything, reliable teardown, orphan-proof registry. Details in items 2 and 4.

### 0.5 If the shell is unavailable
The orchestrator shell has been unreliable (the reference-repo exploration for this plan could not run `ls`; files were read with file tools). If a coder step has no shell:
- still write all files,
- do not claim anything was verified,
- list every verification command as "NOT RUN" in the step's report/`findings`,
- `scripts/verify-local.sh` (item 9) exists so the user can run the whole read-only verification in one command.

---

## 1. What I read and what it means (grounding)

### 1.1 Terraform reference: `c:\Devops\Repository\terraform-aws-eks\terraform-aws-eks-main\{00-vpc,10-sg,40-eks}`
Files read: `00-vpc/{vpc.tf,parameters.tf,variables.tf,provider.tf,outputs.tf}`, `10-sg/{sg.tf,variables.tf,provider.tf,data.tf}`, `40-eks/{main.tf,variables.tf,provider.tf,locals.tf,data.tf}`. (`40-eks/outputs.tf`, `00-vpc/main.tf|locals.tf|data.tf`, `10-sg/main.tf|locals.tf` do not exist.)

Conventions observed:
- Module-based, not raw resources. 40-eks uses `terraform-aws-modules/eks/aws ~> 20.0`; 00-vpc and 10-sg use private git modules (`DAWS-82S/terraform-aws-vpc`, `.../terraform-aws-securitygroup`).
- File split: `provider.tf` (terraform block + backend + provider), `variables.tf`, `locals.tf`, `data.tf`, `outputs.tf`; resource files named by purpose (`vpc.tf`, `sg.tf`, `main.tf`).
- Banner comment header on every file (`# ───...`), `common_tags` map merged with `Name` tag, `project_name` + `environment` vars, `local.name = "${project_name}-${environment}"`.
- S3 backend with `use_lockfile = true`, one state key per stack. They ALSO still set `dynamodb_table` (redundant; dynamo locking is deprecated).
- Cross-stack wiring via SSM Parameter Store (`/${project}/${env}/vpc_id` ...).
- 40-eks facts: `cluster_version = "1.32"`, **private-only endpoint (needs a bastion)**, `eks_managed_node_groups.green` with `t3.medium` min2/max10/desired2, add-ons coredns / eks-pod-identity-agent / kube-proxy / vpc-cni / metrics-server, `enable_cluster_creator_admin_permissions = true`, extra IAM policies (EBS/EFS CSI, ELB), SSH key pair from `~/.ssh/eks.pub`, provider `aws ~> 5.0` while 00-vpc pins `6.28.0` (inconsistent).

Implications / deviations (each is recorded in Decisions, section 2):
1. Private-only endpoint will not work for a laptop-run portal and `kubectl`. Phase 1 needs a public endpoint restricted to the user's IP.
2. 1.32 is now in EKS **extended support** (extra per-hour cost). Checked AWS docs: standard support currently = 1.34, 1.35, 1.36, 1.37; extended = 1.31-1.33. Pick a standard-support version.
3. The 3-stack + SSM split is for a long-lived shared environment. A throwaway cost-sensitive cluster needs ONE stack that `destroy` tears down in one command.
4. `dynamodb_table` is redundant with `use_lockfile`; do not copy it. SSH key pair, EBS/EFS/ELB node policies, database subnets, VPC peering and bastion SGs are not needed in Phase 1; do not copy them.

### 1.2 ArgoCD reference: `c:\Devops\Repository\eks-cluster-argocd\eks-cluster-argocd`
Files read: `argocd.sh`, `app-of-apps.yaml`, `applications/namespaces.yaml`, `namespaces/expense.yaml`. (Directory listing was not possible, so `applications/` beyond `namespaces.yaml` was not enumerated; `backend.yaml` / `frontend.yaml` / `README.md` do not exist.)

Facts:
- `argocd.sh` (5 lines): `kubectl create namespace argocd` (not idempotent: fails if it exists), `kubectl apply -n argocd -f .../argo-cd/stable/manifests/install.yaml` (unpinned `stable`, client-side apply), downloads the Linux `argocd` CLI and `sudo install`s it to `/usr/local/bin` (invalid on Git Bash/Windows), then installs the EBS CSI driver via `kubectl apply -k github.com/...ref=release-1.47`.
- `app-of-apps.yaml`: Application `platform-root` in `argocd` ns pointing at `https://github.com/ShivaKrishna44/eks-cluster-argocd.git` path `applications`, automated prune+selfHeal, `CreateNamespace`, `ServerSideApply`, `PruneLast`. `applications/namespaces.yaml` uses `sync-wave: "0"`, path `namespaces`.

What Phase 1 carries over, and what it does not:
- Carry over: install into namespace `argocd` from the official `install.yaml`; the `argocd` namespace name; the later app-of-apps + sync-wave pattern is documented as the Phase 2/3 entry point.
- Change: idempotent namespace create; **pin the ArgoCD version** instead of `stable`; **`--server-side` apply** (ArgoCD CRDs, notably ApplicationSet, exceed the client-side annotation size limit); no `sudo`/CLI download (the portal talks to the ArgoCD REST API; the CLI is optional and the user may install it themselves).
- Skip: EBS CSI (ArgoCD needs no PVs; the driver also needs node IAM that Phase 1 does not grant); applying `app-of-apps.yaml` (it deploys someone else's GitHub repo's apps, which adds pods and possible cost with no Phase 1 benefit).

### 1.3 Python tools: `c:\Devops\Repository\devops-microservices-crewAi\app\tools\`
Files read: `k8s_tools.py`, `eks_tools.py`, `health_tools.py`, `incident_tools.py`, `deploy_tools.py`, `_toolshim.py`.

Facts that decide the reuse strategy:
- `k8s_tools.py`, `incident_tools.py`, `deploy_tools.py` do `from crewai.tools import tool` at import time (hard CrewAI dependency, so they crash without CrewAI) and `from config import logger` (needs the crewAi app's `config.py` on `sys.path`).
- Every tool returns a human-readable **string** ("K8s ALERT: ...") parsed from `kubectl --no-headers` columns. The portal needs **structured JSON** including `lastState.terminated.reason` (OOMKilled), which `--no-headers` output does not contain.
- Every `_run_kubectl` uses `subprocess.run(f"kubectl {cmd}", shell=True)` with the namespace interpolated into the command string. For a web API taking `?namespace=` from a URL this is a **shell-injection vector**. Must not be copied.
- `eks_tools.py` / `health_tools.py` show the good pattern: `try: from crewai.tools import tool except: from _toolshim import tool`, bounded timeouts, "ERROR:" prefix, never raise. `_toolshim.py` is a ready-made no-op decorator.
- `deploy_tools.py` has write tools (`rollback_deployment`, `restart_deployment`) with no gate.

**Reuse decision:** reuse the *patterns* (bounded timeout, never-hang, error-string discipline, `_toolshim` try/except guard, `kubectl get pods` column semantics, status-derivation logic) but NOT the modules. Backend gets its own `kube.py` using `subprocess.run([...argv list...], shell=False)`, `-o json`, `--context`, and a read-only verb allowlist. A guarded-CrewAI module (`agent_tools.py`, item 6) exposes only the new read-only functions as tools for later phases. Record this deviation in `backend/README.md`: "reuse" means pattern reuse, deliberately, because of the injection risk and structured-data needs.

---

## 2. Decisions (made here; do not re-decide in implementation)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Terraform uses official `terraform-aws-modules/vpc/aws` and `terraform-aws-modules/eks/aws`, pinned to exact versions: **vpc `6.7.3`**, **eks `21.29.0`** (latest from the Terraform registry when this plan was written; the coder re-checks `https://registry.terraform.io/v1/modules/terraform-aws-modules/<m>/aws` and uses the newest at implementation time). | The reused 40-eks uses the official EKS module (module style, not raw resources), so matching style means modules. The reused private git VPC module is not reachable/auditable, and the official VPC module gives subnet tags, single NAT and AZ handling. User asked for Terraform latest, and reused 00-vpc already pins aws provider 6.x. |
| D2 | EKS module v21 input names are used (not the v20 names in the reused file): `name`, `kubernetes_version`, `addons`, `endpoint_public_access`, `endpoint_public_access_cidrs`, `eks_managed_node_groups`. Provider constraint `>= 6.59, < 7.0` (module `versions.tf` requires `aws >= 6.59`, Terraform `>= 1.5.7`); root `required_version = ">= 1.11"` for GA S3 `use_lockfile`. | Verified against `variables.tf` / `versions.tf` at tag v21.29.0. The coder must still confirm every other input name (`enabled_log_types`, `create_cloudwatch_log_group`, `kms_key_deletion_window_in_days`, etc.) against the module's `variables.tf` at the pinned tag; `terraform validate` will catch mistakes. |
| D3 | `kubernetes_version` default `"1.35"`. | In standard support (to 2027-03-27) so there is no extended-support surcharge; not the newest, so add-on/ArgoCD compatibility risk is lower. Verify the table at https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html again when implementing; if 1.35 is no longer in standard support, pick the newest-minus-one that is. Do not use 1.32 (the reused repo's value). |
| D4 | Public API endpoint **enabled**, restricted via required variable `public_access_cidrs` (no default; validation rejects `0.0.0.0/0`). `provision.sh` fills it with the caller's `/32` from `https://checkip.amazonaws.com`, overridable via `PUBLIC_ACCESS_CIDRS`. Private endpoint also on. | Laptop-run `kubectl` and portal backend cannot reach a private-only endpoint (the reused design needs a bastion). Open-to-world is the unsafe default to avoid. Re-running `provision.sh` after an IP change updates the CIDR (idempotent). |
| D5 | One root stack in `terraform/`: VPC + EKS together, module-created security groups, no SSM hand-off. | Single apply, single destroy, no cross-stack dependency ordering; cheapest and most reliable teardown. Deviation from the reused 3-stack layout, documented in `terraform/README.md`. |
| D6 | State: `backend "s3" {}` partial config in `provider.tf` (region, `use_lockfile = true`, `encrypt = true`; NO `dynamodb_table`). Bucket and key supplied by scripts via `-backend-config`. Key = `developer-friendly-infra/<cluster_name>/terraform.tfstate`. A documented `backend.hcl.example` holds placeholders. Scripts run `terraform init -reconfigure` each time (switching between clusters changes the key). | Matches the reused `use_lockfile = true` style, supports several clusters from one codebase, and avoids hard-coding a bucket name in git. |
| D7 | Network: VPC `10.0.0.0/16`, exactly 2 AZs (`slice(data.aws_availability_zones.available.names, 0, 2)`), 2 public + 2 private subnets via `cidrsubnet`, `enable_nat_gateway = true`, `single_nat_gateway = true`, `one_nat_gateway_per_az = false`, DNS hostnames on. No database subnets, no peering. Subnet tags: public `kubernetes.io/role/elb = 1`, private `kubernetes.io/role/internal-elb = 1`, both `kubernetes.io/cluster/<name> = shared`. Each cluster gets its own VPC (identical CIDRs are fine, no peering). | Spec: 2 AZs, single NAT, EKS subnet tags. Single NAT is the main fixed-cost saving (trade-off: AZ-level NAT SPOF, acceptable for a lab). |
| D8 | One managed node group `default`: `t3.medium`, `ON_DEMAND`, `AL2023_x86_64_STANDARD`, desired 2 / min 2 / max 3, private subnets. Default node IAM policies only. Add-ons: `coredns`, `kube-proxy`, `vpc-cni` (`before_compute = true`), `eks-pod-identity-agent` (`before_compute = true`). `enable_cluster_creator_admin_permissions = true`. No `metrics-server` add-on in Phase 1 (nothing uses it yet). Control-plane logging off (`enabled_log_types = []`, no CloudWatch log group) to avoid log cost/leftovers; KMS secrets key kept (security) with `kms_key_deletion_window_in_days = 7`. | Spec sizing. t3.medium caps at 17 pods per node (ENI limit); ArgoCD (~7 pods) + system pods fit comfortably in 2 nodes (about 14 of 34 slots). |
| D9 | Tags: provider `default_tags` = `{ Project = "developer-friendly-infra", Environment = var.environment, ClusterName = var.cluster_name, ManagedBy = "terraform" }`, plus `tags = local.tags` passed to both modules (so EC2 instances from the node group carry them). Naming `local.name = var.cluster_name`. | Spec: everything tagged `Project=developer-friendly-infra`; mirrors the reused `common_tags` + `Name` pattern. |
| D10 | ArgoCD: official `install.yaml` at a **pinned release tag** (`ARGOCD_VERSION` default set by the coder to the latest stable GitHub release at implementation time; look it up at https://github.com/argoproj/argo-cd/releases), applied with `kubectl apply --server-side --force-conflicts -n argocd`. Exposed ONLY via `kubectl port-forward` (no LoadBalancer, no Ingress). | No NLB/ALB cost, no public attack surface. Pinning fixes the reproducibility gap in the reused script. |
| D11 | ArgoCD access from the portal: registry stores `argocd_url = https://localhost:<port>`; port allocated by the registry helper starting at 8081, unique per cluster. User runs `scripts/argocd-portforward.sh <name>` in a separate terminal. Backend verifies TLS normally, EXCEPT it skips verification when the host is `localhost`/`127.0.0.1` (self-signed cert on a loopback port-forward); `ARGOCD_VERIFY_TLS=true` forces verification. | Avoids modifying ArgoCD config (`server.insecure`) just for the portal; skipping verify is limited to loopback. |
| D12 | ArgoCD token: backend reads `ARGOCD_TOKEN_<NAME>` (cluster name upper-cased, `-` to `_`) then `ARGOCD_TOKEN`. `scripts/argocd-token.sh <name>` obtains a short-lived session token via `POST /api/v1/session` with the admin password (over the port-forward) and prints an `export ...` line. Token is never written to the registry, logs, or API responses. | Satisfies "token via env var" without enabling long-lived admin apiKey. Session tokens expire (default about 24h; documented). |
| D13 | Registry helper in Python stdlib (`registry/registry.py`), not `jq`. Atomic write (temp file in same dir + `os.replace`), schema validated on load. Default path resolved from the script's own location, not from an env var, to avoid MSYS `/c/...` vs `C:\...` path conversion bugs between Git Bash and native Python; `REGISTRY_PATH` env override is for tests only. `registry/clusters.json` is git-ignored runtime state; `registry/README.md` documents the schema. | `jq` is not guaranteed on Windows Git Bash; Python is required for the backend anyway. |
| D14 | Registry statuses: `provisioning`, `active`, `failed`, `destroying`, `destroy_failed`. `provision.sh` inserts the entry (status `provisioning`, `created_at` = now UTC) BEFORE `terraform apply`, so a half-built cluster that is already costing money is still visible in the portal and discoverable by `destroy.sh`; ERR trap sets `failed` and prints the destroy command. `created_at` is therefore a slight over-estimate of billed time (cluster takes about 10-15 min to create): conservative for cost. | Orphaned-but-billing infra is the worst failure mode of a one-click tool. |
| D15 | Backend: FastAPI + uvicorn, `httpx` for ArgoCD. Bound to `127.0.0.1:8000` by default. kubectl invoked as argv list with `--context <cluster-name> --request-timeout=...`; context name = cluster name (provision uses `aws eks update-kubeconfig --alias <name>`). The `cluster` query param is validated against the registry (allowlist; unknown = 404), `namespace` against RFC-1123 regex. **No authentication in Phase 1** (single-user localhost tool): must be stated plainly in the backend README and top README; do not bind to 0.0.0.0. | Security: the allowlist + argv list + regex remove injection; localhost binding bounds exposure; auth is a later-phase item (must exist before Phase 3 deploy). |
| D16 | Error contract: unknown cluster 404; invalid namespace 422; kubectl failure/timeout/unreachable cluster 502 `{ "detail": ..., "kind": "kubectl_error" }`; ArgoCD always HTTP 200 with a `status` field (`ok` / `not_configured` / `unreachable` / `unauthorized`) because "not configured" is an expected state. | Frontend can render honest empty/error states without inspecting HTTP codes for the expected cases. |
| D17 | Frontend: Vite + React + TypeScript, plain CSS (CSS variables, dark theme), no UI framework, `vitest` for pure-function tests. All dependencies pinned exact (`npm install --save-exact`, versions looked up with `npm view <pkg> version` at implementation time). Dev server on 5173 proxies `/api` to `http://127.0.0.1:8000` (override with `VITE_API_TARGET`). | TS gives a typed API contract that Phase 3 will extend; no CORS needed because of the proxy. |
| D18 | Cost indicator is computed server-side in `/api/clusters` from `created_at` and an env-configurable hourly estimate `ESTIMATED_HOURLY_USD` (default `0.23`: EKS control plane about 0.10 + NAT about 0.045 + 2 x t3.medium about 0.083, us-east-1 on-demand, excludes data transfer/EBS). Response carries `running_seconds`, `estimated_cost_usd`, and a `cost_note`; the UI labels it "est." with the note. Coder must re-verify the three unit prices against the AWS pricing pages and adjust the default/comment. | One source of truth; honest "estimate" labelling is not fake data, but prices drift. |
| D19 | Git: `git init -b main`, one initial commit containing only `.gitignore` / `.gitattributes` on `main`, then `git checkout -b phase1-idp` and do all work on that branch. **No worktree** (greenfield repo, one folder, no concurrent work; a worktree would add a sibling dir for no benefit). One local commit per plan item (Conventional Commits). **Never push**, no remote configured. Do not edit git config; if `user.name`/`user.email` are unset, stop and report instead of inventing an identity. | Matches the requirement; keeps `main` as a clean base for review diffs. |
| D20 | Names like `dev-eu` are just labels: all clusters are created in `us-east-1` (fixed requirement). Call this out in RUNBOOK.md so nobody expects an EU region. Cluster-name validation: `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`; environment must be one of `dev`, `staging`, `prod`. | Avoids a surprising mismatch and invalid EKS/S3/tag names. |

Cost reference for docs (approximate, us-east-1; the coder verifies and states "approximate"): about $0.23 per cluster-hour, about $5.50 per cluster-day, about $11 per day for two clusters. This is why `destroy.sh` is a first-class citizen.

---

## 3. Target layout

```
Developer-friendly-infra/
  .gitignore  .gitattributes  README.md  RUNBOOK.md
  terraform/      provider.tf variables.tf locals.tf data.tf vpc.tf main.tf outputs.tf
                  backend.hcl.example  terraform.tfvars.example  README.md
  scripts/        common.sh provision.sh destroy.sh argocd-portforward.sh argocd-token.sh verify-local.sh
  registry/       registry.py  README.md  (clusters.json = runtime, git-ignored)  tests/test_registry.py
  backend/        requirements.txt requirements-dev.txt README.md
                  app/{__init__,main,settings,_toolshim,agent_tools}.py
                  app/services/{registry,kube,pods,argocd}.py
                  app/routers/{health,clusters,namespaces,pods,argocd}.py
                  tests/ (+ tests/fixtures labelled test-input-only)
  frontend/       package.json vite.config.ts tsconfig*.json index.html README.md
                  src/{main.tsx,App.tsx,api.ts,types.ts,format.ts,tone.ts,styles.css}
                  src/components/{ClusterList,ClusterCard,ClusterDetail,PodTable,StatusPill,ArgoPanel,EmptyState,ErrorBanner}.tsx
                  src/*.test.ts
```

API contract (frontend and backend both build to this; keep in `backend/README.md`):

- `GET /api/health` -> `{ status:"ok", version, kubectl_available:bool, registry_readable:bool, crewai_available:bool }` (never contacts a cluster).
- `GET /api/clusters` -> `{ clusters:[{ name, region, environment, cluster_endpoint, argocd_url, created_at, status, running_seconds, estimated_cost_usd }], cost_note }`. Missing registry file = `clusters: []`. Corrupt registry = 500 with a clear message (not silently empty).
- `GET /api/namespaces?cluster=` -> `{ cluster, namespaces:[{ name, status }] }`.
- `GET /api/pods?cluster=&namespace=` -> `{ cluster, namespace, pods:[{ name, ready:"1/2", status, restarts:int, start_time, last_state:null|{ reason, exit_code, finished_at } }] }`.
- `GET /api/argocd/apps?cluster=` -> `{ cluster, status:"ok"|"not_configured"|"unreachable"|"unauthorized", message, apps:[{ name, project, destination_namespace, sync_status, health_status, repo_url, target_revision, path, last_synced_at }] }`.

---

## 4. Ordered tasks

Every item ends with a local commit on `phase1-idp` (do not push). Each item leaves the repo buildable. Verification uses only the read-only commands from 0.1.

- [ ] 1. Initialise the repo and branch.
      `git init -b main` in `c:\Devops\Repository\Developer-friendly-infra`; write `.gitignore` (`.terraform/`, `*.tfstate*`, `*.tfplan`, `tfplan`, `terraform.tfvars`, `*.auto.tfvars*`, `.env`, `.env.*` except `.env.example`, `registry/clusters.json`, `registry/*.tmp`, `__pycache__/`, `.venv/`, `venv/`, `.pytest_cache/`, `node_modules/`, `dist/`) and `.gitattributes` (`*.sh text eol=lf`, `*.py text eol=lf`; without LF endings Git Bash scripts break on Windows with `\r` errors). Commit only these two files on `main` ("chore: initial gitignore"), then `git checkout -b phase1-idp`. Confirm `git config user.name` and `user.email` are set (read-only check); if not, stop and report.
      Files: `.gitignore`, `.gitattributes`
      Verify: `git -C c:/Devops/Repository/Developer-friendly-infra branch --show-current` prints `phase1-idp`; `git log --oneline main` shows exactly 1 commit; `git status --short` is clean.

- [ ] 2. Terraform stack (depends on 1). Implement D1-D9 in `terraform/`, following the reused file split and banner-comment style:
      - `provider.tf`: `terraform { required_version = ">= 1.11"; required_providers { aws = { source = "hashicorp/aws", version = ">= 6.59, < 7.0" } }; backend "s3" { region = "us-east-1"; use_lockfile = true; encrypt = true } }` with a comment block documenting the placeholders `TF_STATE_BUCKET` and the key convention; `provider "aws" { region = var.region; default_tags {...} }`. Include the account guard `allowed_account_ids = ["589389425618"]` on the provider (deterministic wrong-account protection).
      - `variables.tf`: `cluster_name` (validated, no default), `environment` (validated dev/staging/prod, no default), `region` (default `us-east-1`), `kubernetes_version` (default per D3), `vpc_cidr`, `node_instance_type` (default `t3.medium`), `node_desired_size`/`node_min_size`/`node_max_size` (2/2/3), `public_access_cidrs` (no default; each element `can(cidrnetmask(...))`; reject `0.0.0.0/0`).
      - `locals.tf`: `name`, `azs` (2), `public_subnets`/`private_subnets` via `cidrsubnet`, `tags`.
      - `data.tf`: `aws_availability_zones` (state `available`, filter `opt-in-not-required`), `aws_caller_identity` (used only for an output sanity string).
      - `vpc.tf`: official vpc module (pinned) per D7.
      - `main.tf`: official eks module (pinned) per D8, `endpoint_public_access = true`, `endpoint_private_access = true`, `endpoint_public_access_cidrs = var.public_access_cidrs`, node group `default`.
      - `outputs.tf`: `cluster_name`, `cluster_endpoint`, `region`, `oidc_provider_arn`, plus `vpc_id` and `update_kubeconfig_command` (`aws eks update-kubeconfig --name <n> --region us-east-1 --alias <n>`).
      - `backend.hcl.example` (placeholders `bucket = "REPLACE_WITH_YOUR_STATE_BUCKET"`, `key = "developer-friendly-infra/<cluster_name>/terraform.tfstate"`), `terraform.tfvars.example` (placeholders only), `README.md` (module choice + the deviations from section 1.1, cost table, the "no real values committed" note).
      Files: `terraform/*`
      Verify (read-only, no AWS access needed): in `terraform/` run `terraform fmt -check -recursive`, then `terraform init -backend=false`, then `terraform validate`; all must succeed. If `validate` flags an input name, fix against the module's `variables.tf` at the pinned tag. Add a `terraform/.terraform.lock.hcl` to git (provider lock is meant to be committed).
      Do NOT run `terraform plan/apply`.

- [ ] 3. Registry helper and tests (depends on 1; independent of 2).
      `registry/registry.py` (stdlib only, argparse CLI + importable functions): `list`, `get <name>`, `upsert --name --region --environment [--cluster-endpoint --argocd-url --status --created-at]` (preserves existing `created_at` on update), `set-status <name> <status>`, `remove <name>`, `next-port` (lowest free port >= 8081 not used by any `argocd_url`). Atomic write via temp file + `os.replace`; creates `{"version":1,"clusters":[]}` if missing; refuses to overwrite a corrupt file (error, nonzero exit, no data loss); validates name regex, environment enum, status enum, ISO-8601 UTC timestamps; schema fields exactly `name, region, environment, cluster_endpoint, argocd_url, created_at, status`. Prints JSON to stdout, errors to stderr. `registry/README.md` documents the schema and statuses (documentation only; no sample entries in `clusters.json`). Tests in `registry/tests/test_registry.py` with `tmp_path` + `REGISTRY_PATH` override: upsert/preserve created_at, atomic replace leaves no `.tmp`, corrupt file refused, remove idempotent, next-port allocation, invalid inputs rejected.
      Files: `registry/registry.py`, `registry/README.md`, `registry/tests/test_registry.py`
      Verify: `python -m py_compile registry/registry.py` and `python -m pytest registry/tests -v` pass (install `pytest` into a venv per backend README if missing).

- [ ] 4. Scripts (depends on 2 and 3).
      `scripts/common.sh` (sourced): `set -euo pipefail` is set in each entry script; helpers `log`, `die`, `require_cmd`, `PY` detection (`python3` then `python` then `py -3`), `ROOT` from `BASH_SOURCE`, a `run` wrapper that echoes and (when `DRY_RUN=1`) does NOT execute, `registry()` wrapper around `registry/registry.py`, `validate_name`/`validate_env`, `detect_public_cidr` (curl `https://checkip.amazonaws.com`, must match IPv4, append `/32`, else honour `PUBLIC_ACCESS_CIDRS`, else die), `tf_backend_args` (`-backend-config=bucket=$TF_STATE_BUCKET -backend-config=key=developer-friendly-infra/$NAME/terraform.tfstate`), `tf_var_args`. Run terraform from inside `terraform/` (subshell `cd`) instead of `-chdir` to avoid MSYS path-conversion issues.

      `scripts/provision.sh <name> <environment>` (`set -euo pipefail`):
        1. validate args, require `terraform aws kubectl curl` and `TF_STATE_BUCKET`; call `aws sts get-caller-identity` and abort unless account == `EXPECTED_ACCOUNT_ID` (default `589389425618`); print caller ARN.
        2. print the cost warning (approx $0.23/h per cluster) and require the user to type the cluster name to proceed.
        3. `registry upsert ... --status provisioning` (D14) and install `trap` on ERR to `set-status failed` and print the exact destroy command.
        4. `terraform init -reconfigure $backend_args`, `terraform plan -out=tfplan $var_args`, show the summary, `terraform apply tfplan` (plan file removed afterwards).
        5. `aws eks update-kubeconfig --name <n> --region us-east-1 --alias <n>`.
        6. ArgoCD (D10, replaces `argocd.sh`): idempotent namespace (`kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -`), `kubectl apply --server-side --force-conflicts -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml`, wait: `kubectl -n argocd wait --for=condition=Available deployment --all --timeout=300s` and `kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=300s`.
        7. registry `upsert` with `cluster_endpoint` (from `terraform output -raw cluster_endpoint`), `argocd_url=https://localhost:<next-port>`, `--status active`.
        8. Final output (do NOT print the password): cost warning again, the exact destroy command (`./scripts/destroy.sh <name>`), the port-forward command (`./scripts/argocd-portforward.sh <name>`), the password retrieval command (`kubectl --context <n> -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d`), and `./scripts/argocd-token.sh <name>`.
      Re-running with the same name must be safe (idempotent): terraform converges, ArgoCD apply converges, registry upsert preserves `created_at` and port.

      `scripts/destroy.sh <name>` (`set -euo pipefail`): validate; require `terraform aws kubectl`, `TF_STATE_BUCKET`; account guard as above; show registry entry if any; require typing the cluster name (no `--yes` flag); `registry set-status destroying`; **pre-flight orphan cleanup**: if the cluster is reachable (kubeconfig context exists), list `Service type=LoadBalancer` and PVCs outside `kube-system`, print them, and delete the LoadBalancer Services so ELBs/ENIs cannot block VPC deletion, then wait for them to disappear (bounded 5 min); `terraform init -reconfigure`, `terraform destroy -auto-approve` (the typed confirmation has already happened), then **only on success** `registry remove` and remove the kube context (`kubectl config delete-context`/`delete-cluster`/`delete-user` for that alias); on failure `registry set-status destroy_failed`, keep the entry, print "cluster may still be billing: re-run ./scripts/destroy.sh <name>" and exit nonzero. Finish by printing how to confirm nothing is left: `aws ec2 describe-instances --filters Name=tag:Project,Values=developer-friendly-infra Name=instance-state-name,Values=running,pending --query "Reservations[].Instances[].InstanceId"` and `aws ec2 describe-nat-gateways --filter Name=tag:Project,Values=developer-friendly-infra Name=state,Values=available` (printed only, not run).

      `scripts/argocd-portforward.sh <name>`: reads the port from the registry, runs `kubectl --context <name> -n argocd port-forward svc/argocd-server <port>:443` in the foreground (tells the user to leave it running; Ctrl+C to stop).
      `scripts/argocd-token.sh <name>`: starts a bounded temporary port-forward on a free local port, reads the initial admin password into a shell variable only, `curl` POSTs `/api/v1/session`, kills the port-forward, and prints only `export ARGOCD_TOKEN_<NAME>='<token>'` plus a note that it is short-lived. Never writes the token or password to disk.

      Files: `scripts/common.sh`, `scripts/provision.sh`, `scripts/destroy.sh`, `scripts/argocd-portforward.sh`, `scripts/argocd-token.sh` (all `chmod +x` via `git update-index --chmod=+x` too).
      Verify (the scripts must NEVER touch real AWS during verification):
        a. `bash -n scripts/*.sh` passes; `shellcheck scripts/*.sh` passes if shellcheck is installed (else say it was not run).
        b. Sandbox dry run: create a temp dir containing executable stubs named `terraform`, `aws`, `kubectl`, `curl` that each print `REAL CALL ATTEMPTED: <name>` to stderr and `exit 99`; run `PATH="<tmpdir>:$PATH" DRY_RUN=1 TF_STATE_BUCKET=dummy PUBLIC_ACCESS_CIDRS=203.0.113.7/32 REGISTRY_PATH=<tmp>/r.json ./scripts/provision.sh dev-eu staging` (type the name when prompted, or feed it via stdin) and the same for `destroy.sh dev-eu`. Expected: exit 0, the printed plan lists every step in order, no `REAL CALL ATTEMPTED` text appears, and the temp registry ends with the entry removed after destroy. Also check bad inputs fail fast: missing `TF_STATE_BUCKET`, bad name, bad environment, wrong confirmation text. Delete the temp dir afterwards.
        c. In dry-run mode the account guard and checkip calls are skipped (document this in the script comment) so no network or credential is needed.

- [ ] 5. Backend core (depends on 3). Build the FastAPI app skeleton and the read-only Kubernetes path.
      - `requirements.txt` (runtime: `fastapi`, `uvicorn[standard]`, `httpx`; exact versions looked up from PyPI at implementation time) and `requirements-dev.txt` (`-r requirements.txt`, `pytest`). Python: the portal itself needs no CrewAI, so any 3.10+ works; recommend a 3.12/3.13 venv (consistent with the CrewAI 3.10-3.13 limit in the other repos; on Git Bash call `venv/Scripts/python.exe` directly if `source venv/Scripts/activate` is unreliable).
      - `app/settings.py`: env-driven (registry path default from file location, `KUBECTL_BIN`, `KUBECTL_TIMEOUT_S` default 20, `ESTIMATED_HOURLY_USD` default per D18, `ARGOCD_VERIFY_TLS`, `ARGOCD_TIMEOUT_S`). No secrets logged.
      - `app/services/registry.py`: read-only loader, schema validation, `get_cluster(name)` (404 helper), cost fields.
      - `app/services/kube.py`: `run_kubectl(cluster, args)` using argv list, `shell=False`, `--context <cluster>`, `--request-timeout`, `timeout=`, `READ_ONLY_VERBS = {"get"}` enforced (raise `ReadOnlyViolation` otherwise), returns parsed JSON or raises `KubectlError` (with stderr trimmed, never includes env). Mirror the "bounded, never hang, never raise raw" discipline from `eks_tools.py::_run`.
      - `app/services/pods.py`: pure function `pod_rows(pod_list_json)`: `ready` = readyContainers/totalContainers; `restarts` = sum of containerStatuses restartCount; `status` derivation order like kubectl: `deletionTimestamp` -> `Terminating`; init-container waiting/terminated reasons (`Init:...`); container `state.waiting.reason` (CrashLoopBackOff, ImagePullBackOff, ErrImagePull, ContainerCreating, CreateContainerConfigError); `state.terminated.reason` (Error, OOMKilled, Completed); `status.reason` (Evicted); else `status.phase`. `last_state` from the first container with `lastState.terminated` (reason, exitCode, finishedAt) so OOMKilled shows even when the pod is currently Running. `start_time` = `status.startTime`.
      - `app/routers/{health,clusters,namespaces,pods}.py` + `app/main.py` (include routers under `/api`, `127.0.0.1` default in README run command, no CORS needed because of the Vite proxy). Namespace regex `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$` (max 63) -> 422 on mismatch. Router/service split so a future `routers/deploy.py` + `services/kube_write.py` + approval/audit layer can be added without touching the read path.
      - `app/_toolshim.py` copied from `crewAi/app/tools/_toolshim.py` (CrewAI optional).
      - Tests in `backend/tests/` (pytest; `monkeypatch` `subprocess.run`; FastAPI `TestClient`): `pod_rows` against a test-input JSON in `tests/fixtures/` (header comment: "TEST INPUT ONLY, shaped like `kubectl get pods -o json`") covering Running, Pending, CrashLoopBackOff, Running-with-previous-OOMKilled, Completed, Terminating; read-only enforcement (`apply`, `delete`, `rollout`, `patch`, `exec`, `get` with injected `; rm` in args are rejected or passed as a single argv element); unknown cluster 404; bad namespace 422; kubectl failure 502; missing registry -> empty list; corrupt registry -> 500; `/api/health` works with no kubectl and no CrewAI; a guard test that fails if any file under `app/` imports `deploy_tools`, `crewai` at module top level (except inside `agent_tools.py`'s try/except), contains `shell=True`, or contains the verbs `apply|delete|patch|rollout|exec|scale` in kubectl-argument position.
      Files: `backend/requirements*.txt`, `backend/app/**`, `backend/tests/**`
      Verify: from `backend/` in a venv: `pip install -r requirements-dev.txt`, `python -m compileall app`, `python -m pytest -v` all pass; `python -c "import app.main"` succeeds in a venv WITHOUT crewai installed.

- [ ] 6. Backend ArgoCD route, guarded CrewAI tools, backend README (depends on 5).
      - `app/services/argocd.py`: resolve token (`ARGOCD_TOKEN_<NAME>` then `ARGOCD_TOKEN`); no token or no `argocd_url` -> `status:"not_configured"` with a message naming the exact env var; call `GET {argocd_url}/api/v1/applications` with `Authorization: Bearer`; TLS rule per D11; timeout per settings; map `items[]` to the contract fields (`status.sync.status`, `status.health.status`, `spec.source.repoURL/targetRevision/path`, `spec.destination.namespace`, `status.operationState.finishedAt`); connection/timeout errors -> `unreachable` (message suggests starting `argocd-portforward.sh`); 401/403 -> `unauthorized`. Never return real-looking placeholder apps. Token never logged or returned.
      - `app/routers/argocd.py` mounted at `/api/argocd/apps`.
      - `app/agent_tools.py`: `try: from crewai.tools import tool / except Exception: from ._toolshim import tool` (same pattern as `eks_tools.py`), exposing ONLY read-only wrappers (`list_pods`, `list_namespaces`, `list_argocd_apps`) each with at least one parameter (Groq rejects empty-property tool schemas per the crewAi notes); not imported by `main.py`; docstring says write tools require the Phase 3 approval gate.
      - Tests (httpx `MockTransport`, test-only): ok mapping; not configured; unreachable; unauthorized; per-cluster env var precedence; loopback TLS-skip rule; token absent from any response/log (`caplog`).
      - `backend/README.md`: venv setup incl. Python note, run command `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, env var table, endpoint contract (section 3), the **"no authentication, localhost only"** warning, read-only guarantee and how it is enforced, the reuse decision (section 1.3), and how Phase 3 would add a confirm-gated deploy endpoint.
      Files: `backend/app/services/argocd.py`, `backend/app/routers/argocd.py`, `backend/app/agent_tools.py`, `backend/tests/test_argocd.py`, `backend/README.md`
      Verify: `python -m pytest -v` (all backend tests) and `python -m compileall app` pass; `python -c "import app.agent_tools"` succeeds without CrewAI installed.

- [ ] 7. Frontend (depends on the contract in section 3; can be built against the contract in parallel with 5-6 but commit after them).
      Scaffold Vite + React + TS by hand (no interactive generator): `package.json` (scripts `dev`, `build` = `tsc -b && vite build`, `test` = `vitest run`), `vite.config.ts` (proxy `/api` -> `VITE_API_TARGET || http://127.0.0.1:8000`), `tsconfig*.json`, `index.html`. Pin everything exact (D17).
      - `src/types.ts`, `src/api.ts`: typed `fetchJson` wrappers for the five endpoints; HTTP errors normalised to `{ status, message }`.
      - `src/format.ts` (+ test): `formatRunningSince(seconds)` ("3h 12m"), `formatCreatedAt(iso)`; `src/tone.ts` (+ test): `podTone(status)` -> green (Running, Completed, Succeeded), yellow (Pending, ContainerCreating, PodInitializing, `Init:*`, Terminating), red (CrashLoopBackOff, Error, ErrImagePull, ImagePullBackOff, OOMKilled, Failed, Evicted, CreateContainerConfigError), gray (unknown); `syncTone` (Synced green, OutOfSync yellow, Unknown gray) and `healthTone` (Healthy green, Progressing yellow, Degraded red, Missing/Suspended gray).
      - Components: `ClusterList` + `ClusterCard` (name, environment badge, region, registry status badge, created-at, "running since" and "est. $X so far" with the backend `cost_note` as tooltip/caption); `ClusterDetail` (opens on select: namespace `<select>` with a visible `<label>`, default `default` if present else first, `Refresh` button, "last updated" timestamp, `aria-live` status text); `PodTable` (columns name, ready, status pill, restarts, started, last state; a red "Last: OOMKilled (exit 137)" chip when `last_state` is set; `<caption>`); `StatusPill` (always includes the text label, never color-only); `ArgoPanel` (table with sync and health pills; separate states for `not_configured` (shows the exact `ARGOCD_TOKEN_<NAME>` env var and `./scripts/argocd-token.sh <name>` instruction), `unreachable` (shows `./scripts/argocd-portforward.sh <name>`), `unauthorized`); `EmptyState` / `ErrorBanner`.
      - Empty states, never fabricated rows: no clusters ("None registered yet. Run `./scripts/provision.sh <name> <env>`", see RUNBOOK.md), no namespaces, no pods in the namespace, cluster unreachable (502), backend down (fetch fails -> "Backend not reachable on :8000").
      - `src/styles.css`: dark theme with CSS variables, AA-contrast text on pills, visible focus outlines, responsive table scroll.
      - `frontend/README.md`: install/run/build, proxy, env override, what each panel shows, how states map to colors.
      Files: `frontend/**`
      Verify: from `frontend/`: `npm install`, `npm test` (vitest utils), `npm run build` all succeed with zero TypeScript errors. Do not start the dev server against real clusters.

- [ ] 8. Top-level docs (depends on 2-7 so commands/paths are exact).
      `README.md`: purpose; ASCII architecture:
      ```
      ./scripts/provision.sh  --terraform-->  VPC + EKS (us-east-1)  --kubectl-->  ArgoCD (argocd ns)
              |                                                                        |
              +--> registry/clusters.json  <-- read --  FastAPI backend  --kubectl/REST--+
                                                              ^
                                                     React portal (Vite)  <-- developer
      ```
      Phase 1 scope (in/out), the safety stance (read-only portal, real infra only, paired destroy, no auth yet = localhost only), cost table with "approximate" label, Phases 2-4 preview (2: cluster/app catalogue and templates + ArgoCD app-of-apps onboarding; 3: confirm-gated deploy flow with approval gate + audit; 4: auth/RBAC, multi-user hosting, cost dashboard), repo layout.
      `RUNBOOK.md`: exact ordered commands the USER runs in their own Git Bash terminal, each with the expected result and a "stop here if" line:
        0. Prerequisite verification: `aws sts get-caller-identity` (expect Account `589389425618`), `terraform version`, `kubectl version --client`, `python --version`, `node --version`.
        1. Create the S3 state bucket once (us-east-1: `aws s3api create-bucket --bucket <unique-name> --region us-east-1`, `put-bucket-versioning`, `put-public-access-block`, `put-bucket-encryption`) and `export TF_STATE_BUCKET=<unique-name>`.
        2. `./scripts/provision.sh dev-eu staging` (explain name is a label; region is us-east-1; about 15-20 min; cost warning), then a second cluster if wanted.
        3. Backend: venv, `pip install -r requirements.txt`, run uvicorn.
        4. ArgoCD access: terminal A `./scripts/argocd-portforward.sh dev-eu`; terminal B retrieve admin password with the printed command; `./scripts/argocd-token.sh dev-eu` and `export ARGOCD_TOKEN_DEV_EU=...` BEFORE starting the backend (or restart it).
        5. Frontend: `npm install`, `npm run dev`, open http://localhost:5173.
        6. What to look for (clusters, namespaces, pods incl. OOMKilled chip, ArgoCD badges), plus verification that tags exist (`aws ec2 describe-instances --filters Name=tag:Project,Values=developer-friendly-infra ...`).
        7. Teardown: `./scripts/destroy.sh dev-eu` (and each other cluster), then the printed leftovers check; reminder that the S3 bucket is intentionally left (pennies) and how to delete it.
        8. Troubleshooting table: wrong account abort, IP changed (re-run provision), kubectl context not found, ArgoCD unreachable/unauthorized, destroy stuck on ELB/ENI, CRLF script errors, Python 3.14 note.
      Files: `README.md`, `RUNBOOK.md`
      Verify: manually cross-check every command, script name, env var, port and path in both docs against the real files (read them back); run `bash -n` on any shell snippets you extracted to a temp file; `npm run build` and `python -m pytest` still pass.

- [ ] 9. One-command local verification and final gate (depends on all).
      `scripts/verify-local.sh`: read-only checks only: `terraform fmt -check -recursive` and `terraform init -backend=false && terraform validate` in `terraform/`; `bash -n` all scripts (+ `shellcheck` if present); `python -m compileall` and `python -m pytest` for `registry/` and `backend/`; `npm ci && npm test && npm run build` in `frontend/`; and a scan that FAILS if any tracked file contains an AWS access key pattern (`AKIA[0-9A-Z]{16}`), a `.env` with values, or a `clusters.json`. It must contain NO terraform plan/apply, aws, or kubectl calls (a guard line in the script header states this).
      Final reviewer checklist (reviewer re-reads files, does not run live commands): (a) no mock/fake data reachable at runtime; (b) backend has no write verb and no `shell=True`; (c) provision/destroy pairing, typed confirmations, account guard, `use_lockfile`, tags, single NAT, node group 2/2/3 `t3.medium`, 2 AZs, public CIDR never `0.0.0.0/0`; (d) registry entry exists before apply and survives failures; (e) docs match code; (f) `git log` shows one local commit per item on `phase1-idp`, nothing pushed, no remote.
      Files: `scripts/verify-local.sh`
      Verify: `bash scripts/verify-local.sh` exits 0 (if the shell/tools are unavailable, report each check as NOT RUN rather than passing it).

---

## 5. Gaps and assumptions (non-blocking)

- Cluster names (`dev-eu` etc.) are labels; everything is `us-east-1` (D20).
- `registry/clusters.json` is git-ignored runtime state; the schema is documented instead of committing sample data.
- Not verified from here: the shell was down, so directory listings of the reference repos were not possible. `00-vpc` has no `main.tf`; it uses `vpc.tf` + `parameters.tf`. `eks-cluster-argocd/applications/` contents beyond `namespaces.yaml` were not enumerated. This does not change the plan.
- Prices in D18 and the Kubernetes/ArgoCD/module versions are point-in-time; the coder re-verifies them at implementation time (module versions fetched from the Terraform registry on the planning date: vpc 6.7.3, eks 21.29.0).
- The `argocd` session token from `/api/v1/session` is short-lived; the Runbook tells the user to regenerate it and restart the backend when the portal shows "unauthorized". A longer-lived API-key account is a Phase 2 decision.
- Public EKS endpoint is IP-restricted to the user's `/32`; if their IP changes, re-run `provision.sh <name> <env>` (idempotent) to update it.
- The Phase 1 backend has no authentication by design (localhost only). It must gain auth before Phase 3 introduces any write endpoint.
- Several reference conventions are intentionally NOT copied (listed in 1.1/1.2/1.3): DynamoDB lock table, SSM hand-off, SSH key pair, extra node IAM policies, `shell=True`, unpinned `stable` ArgoCD, `sudo` CLI install, EBS CSI, k8s 1.32.
