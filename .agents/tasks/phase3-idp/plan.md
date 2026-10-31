# Implementation Plan: Phase 3 IDP (registry, add-ons, visibility, sample app, portal, docs)

Project folder (work directly here, no git worktree): `c:\Devops\Repository\Developer-friendly-infra`
Artifact folder: `c:\Devops\Repository\devops-microservices-platform\.agents\tasks\phase3-idp\`

This plan was written from reading the existing project. Nothing in the project has ever been run.
The shell has returned `Exit Code: -1` for a long time. Every item below lists a read-only verification command.
If the coder's shell still returns `Exit Code: -1`, the coder must mark that check UNVERIFIED in `verification.md`, write
the exact command next to it, and re-read the written file instead. Never claim a check passed that was not run.

## 0. Ground rules for every item (from the authoritative task)

1. Read-only validation only: `terraform fmt -check`, `terraform init -backend=false` then `terraform validate`,
   `python -m py_compile`, `python -m pytest`, `npm install/test/build`, `bash -n`, `helm lint`, `helm template`.
   Never run `terraform apply/destroy`, mutating `aws`, `kubectl apply/delete/patch`, `helm install/upgrade`,
   `argocd app create/sync`, `docker push`, or anything that costs money.
2. Never invent a version, chart version, digest, ARN, account id, repo name or URL. Use only values in the table in
   section 2, or fetch from an official source. Otherwise write `CHECK-LATEST-FROM-<source-url>` and add it to the
   table "Values to confirm before first run" at the top of `VERSIONS.md`.
   Known facts that may be used: account `589389425618`, region `us-east-1`.
3. Do not weaken or remove any existing protection: the get-only wrapper `backend/app/services/kube.py`
   (`run_kubectl` keeps refusing `logs`), account guard, typed confirmations in `provision.sh` and `destroy.sh`,
   registry locking, cost safety, the deploy gate (plan hash, TTL, typed phrase, two actors for prod, audit), the
   8-name resource allow-list plus `pods.metrics.k8s.io`, and the invariants in `backend/tests/test_guard.py`.
   No rollback, restart, delete, prune, force or new write path. The only portal write stays ArgoCD refresh or sync.
4. Cost safety: anything that bills is off by default or clearly labelled. Sample Ingress defaults to `enabled: false`.
   Add-ons must fit 2 x `t3.medium` (AWS VPC CNI limit is 17 pods per t3.medium node, so 34 pods in total; keep the
   add-on footprint small: one replica where the chart allows it).
5. Runtime code uses real data only. Sample JSON is allowed only under test folders.
6. Do not run git and do not claim any repo or commit exists. Put exact git commands in the final `SUMMARY.md`.
7. Use absolute paths with a lowercase drive letter, for example `c:\Devops\Repository\...`.
8. Large single writes were interrupted before. Create a file with `fs_write` (about 150 to 250 lines), then append
   further pieces by reading the file and using `str_replace` on an end marker, or by writing the next chunk to a
   second file name and noting it. If a write is refused, retry once with a smaller chunk or another file name,
   then stop and report exactly what was refused. Do not work around a refusal.
9. Style for docs and comments: plain language, short sentences, no em dashes, no exclamation points.
10. Secrets: never write a real or example-looking secret. Never put a Kubernetes Secret manifest with a value in
    Git. Reference existing Secrets by name only. Test strings that must look like secrets (redaction tests) are
    built at runtime from fragments (for example `"AK" + "IA" + "A" * 16`) so the repo secret scan in
    `scripts/verify-local.sh` does not match the test file itself.
11. Search tooling in this environment is unreliable. Prefer `read_file` on known paths. A "no matches" result from
    `grep_search` or `file_search` is not evidence.

## 1. Design decisions (made here, so the coder does not choose)

| # | Decision | Why |
|---|----------|-----|
| D1 | New stack `terraform-shared/` uses state key `developer-friendly-infra/_shared/terraform.tfstate`, not `.../shared/...`. | `validate_name` in `scripts/common.sh` allows a cluster called `shared`, which would collide with the key. A leading underscore can never match a cluster name. |
| D2 | LBC and EBS CSI use **EKS Pod Identity**, not IRSA. | The stack already installs the `eks-pod-identity-agent` add-on. The module `terraform-aws-modules/eks` v21.29.0 add-on object supports `pod_identity_association = [{ role_arn, service_account }]` (read in the module's `main.tf` at tag v21.29.0). LBC gets an `aws_eks_pod_identity_association` resource. With Pod Identity no role ARN goes into Helm values. |
| D3 | Do **not** use the `terraform-aws-modules/eks-pod-identity` sub-module. Write the IAM role, policy and association with plain resources. | Avoids a new module version to pin, and keeps the LBC policy file explicit and tied to the chart version. |
| D4 | Add-on ArgoCD Applications (`gitops/platform-addons/`) point at the **official Helm repos** and use automated sync with `prune: false`, `selfHeal: true`. | They have no dependency on the user's Git repo URL, so `provision.sh` can apply them before the user has pushed anything. They are installed by the provisioning script, not by the portal. The sample apps stay manual-sync. |
| D5 | Placeholders in the add-on manifests are `__CLUSTER_NAME__`, `__VPC_ID__`, `__REGION__`. `provision.sh` substitutes them with bash parameter expansion on a value read from the file (`${text//__X__/$value}`), after regex-validating each value, and pipes the result to `kubectl apply -f -`. | No `eval`, no `sed` delimiter problems, no unquoted expansion. |
| D6 | `run_kubectl_logs` adds one fixed internal flag, `--limit-bytes=262144`, besides the grammar in the task. The caller can never pass it. | `subprocess.run(capture_output=True)` reads the whole output into memory. A server-side byte bound keeps memory small. `--limit-bytes` is read-only. Confirm the flag with `kubectl logs --help` (value to confirm). |
| D7 | Redaction lives in a new pure module `backend/app/services/redact.py` and is called **inside** `run_kubectl_logs`, so no code path can return unredacted log text. | One choke point. Easy to test. |
| D8 | New routers `logs.py` and `containers.py` are added to `main.py`. The exact-line assertion in `test_guard.py::test_main_mounts_exactly_the_expected_routers` is updated on purpose. `/api/argocd/apps/{name}` goes into the existing `routers/argocd.py`. | A separate `logs.py` makes the "single place" rule easy to read and test. |
| D9 | ArgoCD detail mapping is a pure module `backend/app/services/argocd_detail.py` (no httpx). `argocd_client.py` gets one new read function `get_app_detail` that reuses `_call`. | Keeps `client.get(` count at 1 and `client.post(` at 1, keeps the two-write-function invariant, and keeps the word `kubectl` and `subprocess` out of `argocd_client.py` (a test forbids them). |
| D10 | Inline Helm `values` / `valuesObject` from an ArgoCD app are **not returned**. Return `inline_values_present` and top-level key names only. Helm `parameters` are returned "as written", with the value replaced by `***masked***` when the key matches a secret-looking pattern. | Inline YAML can hold secrets and cannot be masked reliably. |
| D11 | Sample ArgoCD Applications are **single-source** (`spec.source`) with `path: sample-app/charts/web-service` and `helm.valueFiles: ["../../../gitops/values/<app>.yaml"]`. | `valueFiles` paths are relative to `path`. Three levels up from `sample-app/charts/web-service` is the repo root. `services/argocd.py::_map_app` already reads `spec.source` first. |
| D12 | Sample app names: ArgoCD apps `sample-frontend` and `sample-backend`, Helm `fullnameOverride` the same, namespace `dfi-sample`, ECR repos `dfi-frontend` and `dfi-backend`. | Stable Service names (`sample-backend`) so nginx can reach the backend. |
| D13 | Sample frontend nginx proxies `/api/` to `BACKEND_URL` (default `http://sample-backend:8000`) using a variable `proxy_pass` plus `resolver` so nginx starts even if the backend is absent. A start script writes `/tmp/config/config.json` and `/tmp/nginx-conf/api-proxy.conf` from env. The chart mounts an `emptyDir` on `/tmp` so `readOnlyRootFilesystem: true` works. | The app works through `kubectl port-forward` alone (no ALB, no cost). With the ALB on, the `/api` path rule reaches the backend first. |
| D14 | CI workflow: three jobs. `detect` (git diff per app), `build` (matrix, `id-token: write`, `contents: read`), `bump` (one job, `contents: write`, no `id-token`). Plain `docker build` and `docker push`, no third-party build actions. Trivy scans the local image **before** push. Third-party actions are pinned to **full commit SHAs** resolved from the official repos, with the version in a trailing comment. | A March 2026 incident force-pushed malicious tags of `aquasecurity/trivy-action` (GitHub advisory GHSA-69fq-xp46-6x23), so tag pins are not safe for that action. Fewer third-party actions means a smaller supply-chain surface. |
| D15 | CI writes the new tag with `sed -E` on one anchored line (`^  tag: `) after checking the tag matches `^[0-9a-f]{40}$`, then re-reads the file to confirm it changed. | No extra tool dependency, no injection path. |
| D16 | ECR tags are IMMUTABLE and CI never uses `latest`. Re-running the workflow for the same commit fails at push. This is documented, not worked around. | Matches the task. `ecr:DescribeImages` is not granted, to stay inside "push/pull on those two repos". |

## 2. Values to confirm before first run

Rows marked **seen** were read from an official source while this plan was written (dates in the source files are
2026). The coder re-reads the source when writing the file, copies the value, and lists it in the table at the top of
`VERSIONS.md`. Rows marked **placeholder** could not be confirmed offline. Write the placeholder text literally and
list the row in the final summary.

| Value | Status | Source to read | Used in |
|-------|--------|----------------|---------|
| `aws-load-balancer-controller` Helm chart `3.6.2` (appVersion `v3.6.2`), repo `https://aws.github.io/eks-charts` | seen in `index.yaml` | https://aws.github.io/eks-charts/index.yaml | `gitops/platform-addons/aws-load-balancer-controller.yaml` |
| LBC IAM policy JSON at tag `v3.6.2` | seen (file exists; the fetch tool truncates at 4096 bytes in truncated mode, so fetch with `mode: full`) | https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v3.6.2/docs/install/iam_policy.json | `terraform/policies/aws-load-balancer-controller-iam-policy.json` |
| `metrics-server` Helm chart `3.14.0` (appVersion `0.9.0`), repo `https://kubernetes-sigs.github.io/metrics-server/` | seen in `index.yaml` and `Chart.yaml` | https://kubernetes-sigs.github.io/metrics-server/index.yaml | `gitops/platform-addons/metrics-server.yaml` |
| `terraform-aws-modules/eks/aws` `21.29.0` add-on input `pod_identity_association = [{ role_arn, service_account }]` | seen in module `main.tf` at tag v21.29.0 | https://raw.githubusercontent.com/terraform-aws-modules/terraform-aws-eks/v21.29.0/main.tf | `terraform/main.tf` |
| EBS CSI controller service account name `ebs-csi-controller-sa`, namespace `kube-system`, managed policy `arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy` | **placeholder until read** | https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html | `terraform/ebs-csi.tf`, `terraform/main.tf` |
| EBS CSI add-on version | not pinned on purpose: the module resolves it through `aws_eks_addon_version` at plan time | module `main.tf` | `VERSIONS.md` note |
| Pod Identity trust: principal `pods.eks.amazonaws.com`, actions `sts:AssumeRole` and `sts:TagSession` | **placeholder until read** | https://docs.aws.amazon.com/eks/latest/userguide/pod-id-association.html | `terraform/ebs-csi.tf`, `terraform/lbc.tf` |
| `aws_iam_openid_connect_provider`: whether `thumbprint_list` is optional in provider `>= 6.59, < 7.0`; `client_id_list = ["sts.amazonaws.com"]`; issuer `https://token.actions.githubusercontent.com` | **placeholder until read** | https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_openid_connect_provider | `terraform-shared/main.tf` |
| `aquasecurity/trivy-action` `v0.36.0` (release published 2026-04-22) and its **full commit SHA** | version seen; SHA **placeholder** `CHECK-LATEST-FROM-https://github.com/aquasecurity/trivy-action/releases` | `https://api.github.com/repos/aquasecurity/trivy-action/git/ref/tags/v0.36.0` (an annotated tag needs one more call to `.../git/tags/<sha>` to reach the commit) | `.github/workflows/build-push.yml` |
| `aws-actions/configure-aws-credentials` `v6.3.0` and SHA | version seen; SHA **placeholder** | https://api.github.com/repos/aws-actions/configure-aws-credentials/releases/latest | workflow |
| `aws-actions/amazon-ecr-login` `v2.1.7` and SHA | version seen; SHA **placeholder** | https://api.github.com/repos/aws-actions/amazon-ecr-login/releases/latest | workflow |
| `actions/checkout` `v7.0.1` and SHA | version seen; SHA **placeholder** | https://api.github.com/repos/actions/checkout/releases/latest | workflow |
| Python base image tag `python:3.13.18-slim-bookworm` | tag seen on Docker Hub (2026-10-28). Do not record a digest | https://hub.docker.com/v2/repositories/library/python/tags?name=slim | `sample-app/backend/Dockerfile` |
| `nginxinc/nginx-unprivileged` tag (a `X.Y.Z-alpine` style tag) | **placeholder** `CHECK-LATEST-FROM-https://hub.docker.com/r/nginxinc/nginx-unprivileged/tags`. Pick one real tag from the Docker Hub tag API and record it; if the fetch fails, keep the placeholder | https://hub.docker.com/v2/repositories/nginxinc/nginx-unprivileged/tags?page_size=25&name=alpine | `sample-app/frontend/Dockerfile` |
| Sample backend pins: reuse `fastapi==0.161.1`, `uvicorn[standard]==0.54.0` from `backend/requirements.txt`; confirm each with `https://pypi.org/pypi/<name>/json` (`info.version`) | **placeholder** if PyPI cannot be read: `CHECK-LATEST-FROM-https://pypi.org/project/fastapi/` | PyPI JSON | `sample-app/backend/requirements.txt` |
| `kubectl logs --limit-bytes` flag exists and bounds output | **placeholder until read** | https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/ | `kube.py`, `docs/safety-model.md` |
| ArgoCD Application fields `helm.valueFiles`, `helm.parameters`, `helm.valuesObject`, `status.summary.images`, `status.history[]` | **placeholder until read** | https://argo-cd.readthedocs.io/en/stable/operator-manual/application-specification/ | `argocd_detail.py`, gitops apps |
| ArgoCD pinned release `v3.5.6` | existing value in `scripts/common.sh`, not re-checked | https://github.com/argoproj/argo-cd/releases | unchanged |
| Cost numbers for ALB, ECR storage, EBS | recalled, **not checked** | AWS pricing pages | README and RUNBOOK cost tables, labelled estimates |

If a value is a **placeholder**, never let it look real. Use the exact text `CHECK-LATEST-FROM-<url>`.

## 3. Ordered items

Each item is one coder pass. Items are ordered by dependency. Each leaves the project in a consistent state.
"Read first" lists files to open before writing. All paths below are absolute. `$P` means
`c:\Devops\Repository\Developer-friendly-infra`.

### Part A. Shared registry and CI trust stack

- [ ] 1. Create the skeleton of the new stack `$P\terraform-shared\`: provider, variables, backend example.
      Read first: `$P\terraform\provider.tf`, `$P\terraform\variables.tf`, `$P\terraform\backend.hcl.example`, `$P\terraform\locals.tf`.
      Files to create:
      - `$P\terraform-shared\provider.tf`: same `required_version >= 1.11`, same AWS provider constraint `>= 6.59, < 7.0`,
        `backend "s3" { region = "us-east-1", use_lockfile = true, encrypt = true }` (partial config), provider block with
        `allowed_account_ids = ["589389425618"]` and `default_tags` from a `locals` block (`Project = "developer-friendly-infra"`,
        `Stack = "shared"`, `ManagedBy = "terraform"`). Comment that the key is passed with `-backend-config` and is
        `developer-friendly-infra/_shared/terraform.tfstate` (decision D1).
      - `$P\terraform-shared\variables.tf`: `region` (default `us-east-1`); `repository_names` (list(string), default
        `["dfi-frontend", "dfi-backend"]`, validation regex `^[a-z0-9]+([._-][a-z0-9]+)*$`, non-empty, unique via `length(distinct(...))`);
        `keep_last_images` (number, default 20, validation `>= 1`); `untagged_expire_days` (number, default 7, `>= 1`);
        `github_org` and `github_repo` (string, **no default**, validation regex `^[A-Za-z0-9-]{1,39}$` and `^[A-Za-z0-9._-]{1,100}$`);
        `github_branch` (string, default `main`, validation: no `*`, no `?`, regex `^[A-Za-z0-9._/-]+$`);
        `create_github_oidc_provider` (bool, default `false`); `ci_role_name` (string, default `dfi-github-actions-ecr`).
      - `$P\terraform-shared\backend.hcl.example`: same style as `terraform\backend.hcl.example`, key
        `developer-friendly-infra/_shared/terraform.tfstate`. `.gitignore` already ignores `backend.hcl`.
      Verify: `cd $P/terraform-shared && terraform fmt -check`. Full `validate` comes after item 2 (the stack has no resources yet).

- [ ] 2. Add ECR repositories, lifecycle policies, GitHub OIDC role, outputs and README to `$P\terraform-shared\`.
      Read first: `c:\Devops\Repository\Automated-Devops-flow-end-to-end\terraform\github-oidc.tf` and `ecr.tf` (reuse the idea, fix
      the differences below), the provider doc row in section 2.
      Files to create:
      - `$P\terraform-shared\main.tf`:
        - `aws_ecr_repository` with `for_each = toset(var.repository_names)`: `image_tag_mutability = "IMMUTABLE"`,
          `image_scanning_configuration { scan_on_push = true }`, `encryption_configuration { encryption_type = "AES256" }`,
          `force_delete = false`.
        - `aws_ecr_lifecycle_policy` per repo using `jsonencode`: rule priority 1 expires `untagged` images after
          `untagged_expire_days` days (`countType = "sinceImagePushed"`, `countUnit = "days"`); rule priority 2 uses
          `tagStatus = "any"`, `countType = "imageCountMoreThan"`, `countNumber = var.keep_last_images`. The `any` rule must
          have the highest priority number (ECR requirement).
        - `aws_iam_openid_connect_provider.github` with `count = var.create_github_oidc_provider ? 1 : 0` (issuer and client id from
          the doc row in section 2; omit `thumbprint_list` only if the doc says it is optional) and
          `data "aws_iam_openid_connect_provider" "github"` with `count = var.create_github_oidc_provider ? 0 : 1`.
          A local picks the ARN from whichever exists. Comment: the provider is an account singleton, so creating a
          second one fails with `EntityAlreadyExists`.
        - Trust policy: `sts:AssumeRoleWithWebIdentity`, condition `StringEquals` on `token.actions.githubusercontent.com:aud` =
          `sts.amazonaws.com` and `StringEquals` (not `StringLike`) on `...:sub` =
          `repo:${var.github_org}/${var.github_repo}:ref:refs/heads/${var.github_branch}`.
        - Role `aws_iam_role` named `var.ci_role_name`. Inline policy: `ecr:GetAuthorizationToken` on `*`; and on only the
          repository ARNs from the `aws_ecr_repository` resources: `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`,
          `ecr:BatchGetImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`.
          No other action, no `ecr:*`, no `DescribeImages` (decision D16).
      - `$P\terraform-shared\outputs.tf`: `ecr_repository_urls` (map name to URL), `ci_role_arn`, `github_oidc_provider_arn`,
        `github_secret_name` (constant string `AWS_DEPLOY_ROLE_ARN`), and `github_secret_instruction` (text: set repo secret
        `AWS_DEPLOY_ROLE_ARN` to the value of `ci_role_arn`).
      - `$P\terraform-shared\README.md`: why a separate stack (ECR and the CI role are shared by all clusters, a second cluster
        would collide); the state key and why `_shared`; commands (`terraform init -reconfigure -backend-config=...`, `plan -out`, `apply`)
        with `github_org` and `github_repo` passed as `-var` or `TF_VAR_*`; how to choose `create_github_oidc_provider`
        (check first with `aws iam list-open-id-connect-providers`; leave `false` if
        `token.actions.githubusercontent.com` is already listed, set `true` only if it is not); cost note (ECR storage only,
        estimate to check against AWS pricing); destroy note (`force_delete = false` means destroy fails while images exist, delete
        the images yourself first on purpose).
      Verify: `cd $P/terraform-shared && terraform fmt -check && terraform init -backend=false -input=false && terraform validate`
      (expect `Success! The configuration is valid.`). Then read both files once more against the list above.

### Part B. Cluster add-ons (per-cluster Terraform, GitOps manifests, scripts)

- [ ] 3. Add the EBS CSI add-on and its IAM role to `$P\terraform\`.
      Read first: `$P\terraform\main.tf`, `$P\terraform\locals.tf`, `$P\terraform\outputs.tf`, the EBS CSI doc rows in section 2 (fetch them).
      Files:
      - Create `$P\terraform\ebs-csi.tf`: `data "aws_iam_policy_document"` trust for `pods.eks.amazonaws.com`
        (`sts:AssumeRole`, `sts:TagSession`), `aws_iam_role.ebs_csi` named `${local.name}-ebs-csi`, and
        `aws_iam_role_policy_attachment` of the AWS managed `AmazonEBSCSIDriverPolicy` (use the ARN confirmed from the doc).
        The role must not reference `module.eks`, so there is no dependency cycle with the add-on that uses it.
      - Edit `$P\terraform\main.tf` `addons` map: add
        `aws-ebs-csi-driver = { pod_identity_association = [{ role_arn = aws_iam_role.ebs_csi.arn, service_account = "ebs-csi-controller-sa" }] }`
        (service account name as confirmed). Leave `before_compute` at its default so the add-on installs after the node group.
        Add a short comment: the controller runs 2 replicas by default; reducing it needs `configuration_values` and a check with
        `aws eks describe-addon-configuration`, which is not done here.
      - Edit `$P\terraform\outputs.tf`: add `ebs_csi_role_arn`. (`vpc_id` already exists, do not duplicate it.)
      Verify: `cd $P/terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate`.

- [ ] 4. Add the AWS Load Balancer Controller IAM role, policy file and Pod Identity association to `$P\terraform\`.
      Read first: `$P\terraform\ebs-csi.tf` (pattern from item 3), `$P\terraform\main.tf`.
      Files:
      - Create `$P\terraform\policies\aws-load-balancer-controller-iam-policy.json`: fetch the file at tag `v3.6.2` with
        `web_fetch` `mode: full`. Write it in two or three chunks. After writing, re-read the whole file and check: it starts
        with `{`, has `"Version": "2012-10-17"`, braces and brackets balance, and the statement count matches the source.
        If the shell works, also run `python -c "import json,sys; json.load(open(sys.argv[1]))" <file>`.
        **If the file cannot be fetched in full, do not invent it.** Write a file whose content is one line of plain text
        starting `PLACEHOLDER-NOT-VALID-JSON:` followed by the download command below, so `terraform validate` fails on the
        invalid policy JSON with a readable hint. Record this in `verification.md` and the summary.
        Download command (also goes into RUNBOOK.md in item 17):
        `curl -fsSL https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v3.6.2/docs/install/iam_policy.json -o terraform/policies/aws-load-balancer-controller-iam-policy.json`
      - Create `$P\terraform\lbc.tf`: `aws_iam_policy.lbc` named `${local.name}-aws-lbc` with `policy = file("${path.module}/policies/aws-load-balancer-controller-iam-policy.json")`;
        `aws_iam_role.lbc` named `${local.name}-aws-lbc` (Pod Identity trust as in item 3); attachment; and
        `aws_eks_pod_identity_association.lbc` with `cluster_name = module.eks.cluster_name`, `namespace = "kube-system"`,
        `service_account = "aws-load-balancer-controller"`, `role_arn = aws_iam_role.lbc.arn`. Comment: IAM names carry the cluster
        name because IAM is account-global and several clusters share the account.
      - Edit `$P\terraform\outputs.tf`: add `lbc_role_arn`.
      Verify: same three Terraform commands as item 3. If the placeholder file was used, `terraform validate` is expected to fail with the
      JSON message; record that as the expected result, not as a pass.

- [ ] 5. Create the GitOps add-on manifests in `$P\gitops\platform-addons\`.
      Read first: `c:\Devops\Repository\eks-cluster-argocd\eks-cluster-argocd\app-of-apps.yaml` and its `applications\` folder (shape only),
      the chart rows in section 2 (re-read both `index.yaml` files).
      Files to create:
      - `$P\gitops\platform-addons\metrics-server.yaml`: ArgoCD `Application` in namespace `argocd`, project `default`,
        `source.repoURL: https://kubernetes-sigs.github.io/metrics-server/`, `chart: metrics-server`, `targetRevision: 3.14.0`, inline
        `helm.valuesObject` (replicas 1, small `resources.requests` such as `cpu: 50m`, `memory: 64Mi`; use only keys that exist in the chart's
        `values.yaml`, which you must read at
        `https://raw.githubusercontent.com/kubernetes-sigs/metrics-server/master/charts/metrics-server/values.yaml`),
        destination `https://kubernetes.default.svc` namespace `kube-system`, `syncPolicy.automated { prune: false, selfHeal: true }`.
      - `$P\gitops\platform-addons\aws-load-balancer-controller.yaml`: same shape; `repoURL: https://aws.github.io/eks-charts`,
        `chart: aws-load-balancer-controller`, `targetRevision: 3.6.2`; values `clusterName: __CLUSTER_NAME__`, `region: __REGION__`,
        `vpcId: __VPC_ID__`, `replicaCount: 1`, `serviceAccount { create: true, name: aws-load-balancer-controller }` (no role annotation,
        Pod Identity needs none), small `resources.requests`; read the chart `values.yaml`
        (`https://raw.githubusercontent.com/aws/eks-charts/master/stable/aws-load-balancer-controller/values.yaml`) and use only existing keys.
        Check how the chart ships its CRDs; if ArgoCD needs `ServerSideApply=true` under `syncOptions`, add it and say why in a comment.
      - `$P\gitops\platform-addons\README.md`: what the two apps are, the three placeholders and that `provision.sh` fills them, why the
        chart versions are pinned, how to bump a version (edit `targetRevision`, then re-read the chart `values.yaml`), pod budget note
        (17 pods per `t3.medium`), and that these Applications do not read the user's Git repo.
      Verify: `bash -c 'python -c "import yaml,sys; [list(yaml.safe_load_all(open(f))) for f in sys.argv[1:]]" $P/gitops/platform-addons/*.yaml'`
      (YAML parses; PyYAML is already a backend dependency). If `helm` exists, nothing to render here (the charts are remote).
      Re-read each file and check that each placeholder appears exactly where expected.

- [ ] 6. Extend the scripts: add-on step 6b in `provision.sh`, a render helper in `common.sh`, Ingress cleanup in `destroy.sh`.
      Read first: all of `$P\scripts\provision.sh`, `$P\scripts\common.sh`, `$P\scripts\destroy.sh` (the inline comments explain real
      decisions), and `$P\gitops\platform-addons\README.md`.
      Files:
      - Edit `$P\scripts\common.sh`: add `ADDONS_DIR="$ROOT/gitops/platform-addons"`, `INSTALL_ADDONS="${INSTALL_ADDONS:-1}"`, a validator
        that `INSTALL_ADDONS` is `0` or `1`, `VPC_ID_REGEX='^vpc-[0-9a-f]{8,17}$'`, and `render_addon <file>` which: reads the file with
        `$(<file)`, checks `NAME`, `REGION` and the VPC id against their regexes (die on mismatch), replaces `__CLUSTER_NAME__`,
        `__REGION__`, `__VPC_ID__` with `${text//__X__/$value}`, dies if any `__[A-Z_]*__` placeholder is left, and prints the result with
        `printf '%s\n'`. No `eval`, no `sed`, all expansions quoted, no GNU-only flags.
      - Edit `$P\scripts\provision.sh`: after the ArgoCD wait lines and before step 7, add "6b. platform add-ons". Skip with a log line when
        `INSTALL_ADDONS=0`. Under `DRY_RUN=1` print what would be applied and do not read terraform output. Otherwise read
        `VPC_ID="$(tf output -raw vpc_id)"`, then for each `*.yaml` in `ADDONS_DIR` run `render_addon "$f" | kc apply -f -`, then
        `kc -n argocd wait --for=jsonpath='{.status.health.status}'=Healthy application/<name> --timeout=600s` for each Application (confirm
        `--for=jsonpath` support in the kubectl docs; if unsure use `retry` with `kc get application ... -o jsonpath=...` instead). Failure of
        6b must go through the existing `on_error` trap. Keep every existing step and message. Update the header comment and the closing banner
        to mention `INSTALL_ADDONS` and the new cost-free (no ALB until an Ingress exists) status.
      - Edit `$P\scripts\destroy.sh` `preflight_cleanup`: before the LoadBalancer Service block, list Ingresses
        (`kc get ingress -A --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name`), print them, delete each with
        `kc -n "$ns" delete ingress "$name" --wait=false`, then wait up to 5 minutes for the list to become empty (same loop style as the Service
        wait). The AWS Load Balancer Controller must still be running at that point to delete the ALB, so this block runs before anything else is
        removed. Log a warning, not a failure, if Ingresses remain after the wait. Keep the typed confirmation, `reg_safe` calls and the final
        leftovers text unchanged; add a third leftovers command to the printed list:
        `aws elbv2 describe-load-balancers --query "LoadBalancers[].LoadBalancerArn"` (printed, not run). Update the header comment.
      Verify: `bash -n $P/scripts/provision.sh $P/scripts/destroy.sh $P/scripts/common.sh`; then
      `DRY_RUN=1 REGISTRY_PATH=/tmp/r.json PUBLIC_ACCESS_CIDRS=203.0.113.7/32 TF_STATE_BUCKET=dummy bash scripts/provision.sh dev-eu staging`
      (needs terraform, aws, kubectl on PATH; prints steps only; it will wait at the typed confirmation, so feed the name with
      `echo dev-eu | ...`). Also `echo dev-eu | DRY_RUN=1 REGISTRY_PATH=/tmp/r.json TF_STATE_BUCKET=dummy bash scripts/destroy.sh dev-eu`.
      If the shell is down, mark UNVERIFIED and re-read the three scripts for quoting.

### Part C. Read-only visibility upgrades in the backend

Common rules for items 7 to 10: read `$P\backend\app\services\kube.py`, `$P\backend\tests\test_kube.py`, `$P\backend\tests\test_guard.py`,
`$P\backend\tests\conftest.py` and `$P\backend\tests\test_diagnose_api.py` first (they show the fake-subprocess and
`dependency_overrides` patterns). Do not use any of these string constants in `backend/app` code, because `test_guard.py` forbids them as exact constants:
`apply delete patch rollout exec scale create replace edit label annotate cordon drain taint set run`. Do not write `--force`, `kubectl apply`,
`rollout undo` or `rollout restart` anywhere under `backend/app`. Test fixtures go under `$P\backend\tests\fixtures\phase3\` (new folder, plus a
short `README.md` saying they are test inputs). Run tests from `$P\backend`.

- [ ] 7. Add the redaction module and `run_kubectl_logs` to `services/kube.py`, with unit tests.
      Files:
      - Create `$P\backend\app\services\redact.py`: pure functions, no I/O. `redact_text(text: str) -> tuple[str, int]` returns the cleaned text and a
        replacement count. Work line by line and cap each line at 10,000 characters before matching (keeps regex time bounded). Patterns, each with a
        fixed replacement such as `***redacted***`, with no nested quantifiers:
        (a) `Bearer <token>`; (b) key/value pairs where the key matches `password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|client[_-]?secret|authorization|auth`
        (case-insensitive) followed by `=` or `:` and a value, keep the key and replace the value (handle quoted values and JSON `"key": "value"`);
        (c) AWS access key id `\b(AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA)[A-Z0-9]{16}\b`; (d) a bare 40-character base64-looking string only when it contains at
        least one uppercase letter, one lowercase letter and one digit (so 40-hex Git SHAs stay readable); (e) JWT-looking
        `eyJ...` three-part strings; (f) `scheme://user:password@host` credentials; (g) PEM private key blocks (`-----BEGIN ... PRIVATE KEY-----` to the end marker, also
        a begin line without an end marker redacts to the end of the text).
      - Edit `$P\backend\app\services\kube.py`: add module constants `LOG_TAIL_MIN = 1`, `LOG_TAIL_MAX = 500`, `LOG_MAX_BYTES = 262144`, regexes
        `_POD_RE = [a-z0-9]([-a-z0-9.]*[a-z0-9])?` (max 253 chars) and `_CONTAINER_RE = [a-z0-9]([-a-z0-9]*[a-z0-9])?` (max 63), both used with `fullmatch`.
        Add `run_kubectl_logs(cluster, pod, namespace, container, tail, previous) -> dict` returning
        `{"text", "truncated", "redactions", "bytes"}`. It validates: cluster with the existing `_CONTEXT_RE`; namespace with the existing namespace
        regex and length; pod and container with the regexes above; `tail` must be an `int` (reject `bool`, floats, strings) in 1..500; `previous` must be a `bool`.
        Any failure raises `ReadOnlyViolation` before `subprocess.run` is reached. The argv is exactly:
        `[kubectl_bin, "--context", cluster, f"--request-timeout={n}s", "logs", pod, "-n", namespace, "-c", container, f"--tail={tail}", "--limit-bytes=262144"]`
        plus `"--previous"` only when `previous` is true. Shell off, `text=True` with `errors="replace"`, `timeout=kubectl_timeout_s + 5`, same error mapping as
        `run_kubectl` (`KubectlError`). Cap the returned text at `LOG_MAX_BYTES` (encode, cut, decode with `errors="replace"`), set `truncated` when the cap or the
        server limit was hit, then call `redact_text`. Pass kubectl error text through `redact_text` as well before raising `KubectlError`.
        Keep `READ_ONLY_VERBS = frozenset({"get"})` and keep `run_kubectl` and `_check_args` untouched. Update the module docstring: say that `logs` is allowed
        in exactly one function, name the grammar, and point to `docs/safety-model.md`. Keep the comment that adding resources needs a test and a doc line.
      - Create `$P\backend\tests\test_redact.py`: one test per pattern; non-secret lines unchanged (a 40-hex Git SHA, a normal INFO line, a URL without
        credentials); idempotence (redacting twice equals once); a 10,000+ character line returns quickly; replacement count correct. Build secret-looking inputs
        from fragments at runtime (rule 10 in section 0).
      - Create `$P\backend\tests\test_kube_logs.py`: accepted shape and exact argv list (with and without `previous`); `shell is False`; timeout present;
        rejected shapes never reach the fake subprocess: tail 0, 501, -1, `True`, `"10"`, `10.0`; bad pod and container names (empty, uppercase, leading dash, `--all-containers`,
        `a b`, `a;b`, `a$(id)`, trailing newline, 254-char pod, 64-char container); bad namespace; bad cluster; `previous="yes"`; output over 262,144 bytes is cut and `truncated` is true;
        secrets in returned text are redacted; a non-zero exit becomes `KubectlError`; missing binary and timeout map to `KubectlError`.
      - Edit `$P\backend\tests\test_kube.py`: keep every existing test. Add one test that `run_kubectl("dev-eu", ["logs", "x", "-n", "default", "-c", "y", "--tail=5"])` still raises
        `ReadOnlyViolation` and never reaches the fake.
      - Edit `$P\backend\tests\test_guard.py` deliberately: (1) add `test_logs_verb_exists_only_in_kube_py`, an AST scan asserting the exact string constant `"logs"` appears only in
        `services/kube.py`; (2) add a test that `kube.run_kubectl_logs` exists and `READ_ONLY_VERBS` is still exactly `{"get"}` (the existing test stays); (3) leave
        `test_only_kube_imports_subprocess` and the allow-list test untouched; (4) the router line assertion changes in item 8, not here. Read every file under
        `backend/app` that you know may contain the constant `"logs"` (for example `diagnose\` tips) before adding test (1), and say in `verification.md` how you checked.
      Verify: `cd $P/backend && python -m pytest tests/test_redact.py tests/test_kube_logs.py tests/test_kube.py tests/test_guard.py -q`.

- [ ] 8. Add `GET /api/logs`, wire the router, update guard test and docs.
      Files:
      - Create `$P\backend\app\routers\logs.py`: `GET /logs?cluster=&namespace=&pod=&container=&tail=&previous=` using `cluster_param`, `namespace_param`, `pod_param` from
        `routers/deps.py`. Add a `container_param` to `deps.py` (pattern as `_CONTAINER_RE`, max 63, same style as `pod_param`). `tail: int = Query(100, ge=1, le=500)`,
        `previous: bool = Query(False)`. Return `{cluster, namespace, pod, container, tail, previous, text, truncated, bytes, redacted: true, redactions, note}` where `note` is the fixed
        sentence "Redaction is best effort. Do not treat this output as safe to share." Errors already map: `KubectlError` to 502, `ReadOnlyViolation` to 400.
      - Edit `$P\backend\app\main.py`: import `logs` (and `containers`, added in item 9 together with its router file; if you do item 8 first, add only `logs` now and add `containers` in
        item 9) and extend the router tuple. The tuple order must match the line you write into the test.
      - Edit `$P\backend\tests\test_guard.py`: update the exact line in `test_main_mounts_exactly_the_expected_routers` to the new tuple. Add `/api/logs` to nothing else: the GET-only
        route test already covers it.
      - Create `$P\backend\tests\test_logs_api.py`: use `registry_file`, `make_entry`, a fake `kube.subprocess.run`; assert 200 shape; `tail=0` and `tail=501` give 422; bad pod and bad container
        give 422; unknown cluster gives 404; kubectl failure gives 502 with `kind: kubectl_error`; the fake saw exactly one call whose argv contains `logs` and `--tail=100`; text with a
        Bearer token comes back redacted; `previous=true` adds `--previous`; no query value can add another flag.
      - Edit `$P\docs\safety-model.md`: add a new subsection "Bounded logs (a deliberate widening of layer 1)" with the grammar, why it was added (people need to see
        why a pod fails), the risk (logs can hold sensitive data, redaction is best effort and not a guarantee, the backend has no login and must stay on `127.0.0.1`), the limits (tail 1..500,
        256 KiB, timeouts, no follow, no label selector, no all-containers), the `--limit-bytes` note, and the fact that `run_kubectl` still refuses `logs`. Add a row to the layer
        table or update row 1's text. Do not remove any existing sentence.
      - Edit `$P\backend\README.md`: add the `/api/logs` row to the endpoint table, add `logs.py` to the layout block, and add one bullet to the read-only guarantee section.
      Verify: `cd $P/backend && python -m pytest tests/test_logs_api.py tests/test_guard.py tests/test_kube_logs.py -q`.

- [ ] 9. Add `GET /api/containers`.
      Read first: `$P\backend\app\services\pods.py` (status derivation style), `$P\backend\app\diagnose\engine.py` (how `PodNotFound` is raised), `$P\backend\app\routers\pods.py`.
      Files:
      - Create `$P\backend\app\services\containers.py`: pure `container_rows(pod: dict) -> list[dict]`. One row per init container (`kind: "init"`) and main container (`kind: "main"`), merged with
        `status.initContainerStatuses` and `status.containerStatuses` by name. Fields: `name`, `kind`, `image` (as written), `image_tag` (text after the last `:` of the name part
        when no `@`, else `null`), `image_digest` (text after `@`, else `null`; an image without tag and digest has both `null`; take care with registry ports like `host:5000/app`),
        `ready`, `restart_count`, `state` (`{phase: running|waiting|terminated|unknown, reason, exit_code, message(capped 300), started_at, finished_at}`), `last_state` (same shape or `null`),
        `resources` (`{requests: {...}|{}, limits: {...}|{}}` copied as written, only keys `cpu`, `memory`, `ephemeral-storage`), `probes`
        (`{liveness, readiness, startup}` each `null` or `{type: http_get|tcp_socket|exec|grpc|unknown}`). Missing or `null` parts give `null` or empty values and never raise.
        Do not copy environment variables, command arguments or volume contents into the row.
      - Create `$P\backend\app\routers\containers.py`: `GET /containers?cluster=&namespace=&pod=` using the three deps. Calls `kube.run_kubectl(cluster["name"], ["get", "pods", "-n", namespace])`,
        finds the pod by `metadata.name`, raises `PodNotFound` (import from `..diagnose.engine`) when absent. Returns `{cluster, namespace, pod, phase, containers: [...]}`.
      - Edit `$P\backend\app\main.py`: add `containers` to the imports and the router tuple (now `health, clusters, namespaces, pods, containers, logs, argocd, diagnose, deploy, audit`
        or the order you chose in item 8; keep one order everywhere).
      - Edit `$P\backend\tests\test_guard.py`: update the router tuple line again if needed.
      - Create fixtures under `$P\backend\tests\fixtures\phase3\`: `pod_multi_container.json` (a pod list with one init container that finished, a main container running with probes, a
        sidecar waiting in `CrashLoopBackOff` with `lastState.terminated` OOMKilled exit 137, one image with a digest, one with a tag, one with a registry port),
        `pod_minimal.json` (a bare pod with no statuses yet), plus `README.md`. These are recorded-shape test inputs only.
      - Create `$P\backend\tests\test_containers.py`: pure-parser tests on each fixture (every field above), a missing-status pod, image parsing table (including `host:5000/app`, `app@sha256:...`,
        `app:1.2`, `app`), and an API test with the fake subprocess (200 shape, 404 `pod_not_found`, 502 when kubectl fails, argv is `get pods -n <ns> -o json` only, no `logs`).
      - Edit `$P\backend\README.md`: add the endpoint row and `containers.py` to the layout.
      Verify: `cd $P/backend && python -m pytest tests/test_containers.py tests/test_guard.py -q`.

- [ ] 10. Add `GET /api/argocd/apps/{name}` (ArgoCD and Helm detail), read-only.
      Read first: `$P\backend\app\services\argocd_client.py` (the header comment lists invariants), `$P\backend\app\services\argocd.py`, `$P\backend\tests\test_argocd_client.py`,
      `$P\backend\tests\test_guard.py`, the ArgoCD spec doc row in section 2 (fetch it and confirm field names).
      Files:
      - Create `$P\backend\app\services\argocd_detail.py` (no `httpx`, no `subprocess`): `map_app_detail(item: dict) -> dict` returning
        `name`, `project`, `destination` (`server`, `namespace`), `sources` (list; from `spec.sources` or `[spec.source]`; each `{type, repo_url, chart, path, target_revision, helm: {value_files, parameters, inline_values_present, inline_values_keys} | null}`
        where `type` is `helm` when `chart` or `helm` is set, `kustomize` when `kustomize` is set, `directory` for a plain path, `plugin` when `plugin` is set, else `unknown`), `images`
        (`status.summary.images`, list of strings, or `[]`), `sync` (`status`, `revision`), `health` (`status`, `message`), `operation` (`phase`, `message` capped 500, `started_at`, `finished_at`, `revision` from
        `syncResult`), `history` (last 10 of `status.history`, newest first: `id`, `deployed_at`, `revision`, `source_repo_url`, `source_target_revision`), `conditions`, `out_of_sync_resources` (reuse the logic of
        `argocd_client.map_detail`; import that function or copy its rule, and say which). Parameter masking: if the parameter name matches `(?i)(pass|secret|token|key|credential|auth|cert|private)`, the value becomes `***masked***`. Do not return `valuesObject` or `values`.
      - Edit `$P\backend\app\services\argocd_client.py`: add `get_app_detail(cluster, app_name, transport=None)` next to `get_app`. It uses `check_app_name`, `_call` with the read token (`resolve_token`)
        and `_read_help`, then `argocd_detail.map_app_detail`. Same status mapping as `get_app` (`ok`, `not_configured`, `unreachable`, `unauthorized`, `not_found`, `error`) and `app: None` on failure. Do not add another
        `client.get(` or `client.post(`. Do not add the words `kubectl` or `subprocess` to the file. Keep `refresh_app` and `sync_app` exactly as they are. Update the header comment: reads now include the detail view.
      - Edit `$P\backend\app\routers\argocd.py`: add `GET /argocd/apps/{name}` with `name: str = Path(..., min_length=1, max_length=63, pattern=APP_NAME pattern)`, `cluster` from `cluster_param`, and the
        `argocd_transport` dependency from `deps.py`. Always HTTP 200 for expected states with the `status` field. Update the module docstring.
      - Create fixture `$P\backend\tests\fixtures\phase3\argocd_app_helm.json` (a Helm app with `valueFiles`, parameters including one named like a secret, inline `values` containing a fake secret-looking string built to
        be obviously fake, `status.summary.images`, `status.history` with 12 entries, a failed last operation) and `argocd_app_directory.json` (plain path app).
      - Create `$P\backend\tests\test_argocd_detail.py`: mapper tests on both fixtures (source type, value files, masked parameter, no inline values leaked, images, history capped at 10 and newest first, operation, out-of-sync list); client tests with the
        `Fake` transport pattern from `test_argocd_client.py` (read token only, path `/api/v1/applications/<name>`, no `refresh` query, status mapping, bad name raises `InvalidAppName` before any request); API tests with
        `argocd_override`-style `dependency_overrides[deps.argocd_transport]` (200 shape, 422 for a bad name, `not_configured` without a token and no request made).
      - Edit `$P\backend\tests\test_guard.py`: no change expected to the two-write-function test; confirm by reading that it still passes with the new code. Add a test that `argocd_detail.py` imports neither `httpx` nor `subprocess`.
      - Edit `$P\backend\README.md`: add the endpoint row and layout entry.
      Verify: `cd $P/backend && python -m pytest tests/test_argocd_detail.py tests/test_argocd_client.py tests/test_argocd.py tests/test_guard.py -q`, then the whole suite: `cd $P/backend && python -m pytest -q`.

### Part D. Sample app, generic Helm chart, GitOps apps, CI

Common rules for items 11 to 14: read `c:\Devops\Repository\platform-developer-need\generator.py`, `platform.py` and `README.md` first, for the shape of the
Dockerfile, chart (values, deployment, service, ingress, hpa) and ArgoCD Application. Reuse the ideas, not the files. Everything lives under
`$P\sample-app\`, `$P\gitops\` and `$P\.github\`. No Secret object with a value anywhere. Resource names follow decision D12.

- [ ] 11. Create the sample backend `$P\sample-app\backend\`.
      Files:
      - `sample_api\__init__.py` and `sample_api\main.py`: FastAPI app with `GET /healthz` (liveness), `GET /readyz` (readiness), `GET /api/hello` (JSON with a greeting string and the value of env `GREETING`,
        default `hello`, which the chart supplies from a ConfigMap), `GET /api/version` (JSON `{version: APP_VERSION env, default "unknown"}`). Read env on every request, not at import time (the repo rule in
        `backend/app/settings.py`). No database, no outbound calls, no secrets.
      - `requirements.txt`: `fastapi` and `uvicorn[standard]` pins per section 2 (reuse the repo pins; confirm on PyPI or write `CHECK-LATEST-FROM-...` placeholders). `requirements-dev.txt`: `pytest` and `httpx`
        with the pins already used in `backend/requirements-dev.txt` and `backend/requirements.txt` (read both).
      - `tests\test_main.py`: FastAPI `TestClient` tests for the four routes, env override of `GREETING` and `APP_VERSION`.
      - `Dockerfile`: multi-stage. Stage `builder` (`python:3.13.18-slim-bookworm`, from section 2) installs requirements into a virtualenv at `/opt/venv` with `--no-cache-dir`; stage `runtime` copies only the venv and the
        package, creates a non-root user with a fixed numeric UID and GID (10001), sets `USER 10001`, `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1`, `EXPOSE 8000`,
        `CMD ["uvicorn", "sample_api.main:app", "--host", "0.0.0.0", "--port", "8000"]`. No `HEALTHCHECK` using curl (the image has no curl); the chart uses Kubernetes probes. No `latest` tags. Works with a read-only root filesystem.
      - `.dockerignore`: `__pycache__`, `*.pyc`, `tests`, `.pytest_cache`, `.venv`, `venv`, `.git`, `*.md`, `Dockerfile`.
      Verify: `cd $P/sample-app/backend && python -m pytest -q` (needs `fastapi`, `httpx`, `pytest`, already installed for the main backend). Note: do not run `docker build` (no cost, but Docker may be missing; if Docker exists a local
      `docker build` is read-only for the cloud and is allowed, but never `docker push`). Mark the build UNVERIFIED if not run.

- [ ] 12. Create the sample frontend `$P\sample-app\frontend\`.
      Files:
      - `public\index.html` and `public\app.js` (plain HTML and JavaScript, no npm, no build tool): fetch `/config.json` (shows `podName`, `appVersion`, `environment`) and `/api/hello` and `/api/version`,
        render the results with `textContent` only (no `innerHTML`), and show a clear error line when a call fails. Dark, minimal style in `public\style.css`.
      - `nginx\default.conf`: server on port `8080`; `root /usr/share/nginx/html`; `location = /config.json { alias /tmp/config/config.json; add_header Cache-Control "no-store"; }`; `location /api/` that uses
        `include /tmp/nginx-conf/*.conf;` for the proxy lines written at start (decision D13: `resolver kube-dns.kube-system.svc.cluster.local valid=10s;`, `set $backend ...; proxy_pass $backend;`
        in the generated file); security headers (`X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `Referrer-Policy no-referrer`); `location /` with `try_files $uri /index.html`.
        Check that `nginx -t` accepts an `include` glob that matches no file.
      - `docker-entrypoint.d\40-write-config.sh` (LF endings, mode noted in the README because Windows cannot set it; the Dockerfile runs `chmod +x`): writes `/tmp/config/config.json` from env `POD_NAME`, `APP_VERSION`, `ENVIRONMENT`
        using a here-doc with values validated against `^[A-Za-z0-9._:/-]{0,128}$` (else the value is written as `"invalid"`), and writes `/tmp/nginx-conf/api-proxy.conf` from `BACKEND_URL` (default
        `http://sample-backend:8000`, validated against `^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?$`). Never use `eval`.
      - `Dockerfile`: multi-stage. Stage `check` (`FROM nginxinc/nginx-unprivileged:<tag from section 2>`) copies the config and runs `nginx -t -c` against it so a bad config fails the build; stage `runtime` copies files from
        the same base, `USER 101` (confirm the user id used by the image from its Docker Hub page or Dockerfile; it is the image's built-in user), `EXPOSE 8080`. If the nginx tag is a placeholder, write it as `ARG NGINX_TAG=CHECK-LATEST-FROM-https://hub.docker.com/r/nginxinc/nginx-unprivileged/tags`
        and say in the README that the build fails until it is replaced.
      - `.dockerignore`, and `README.md` for the folder (files, what the start script does, how to run it locally with `docker run -p 8080:8080` for the user to try).
      Verify: `bash -n $P/sample-app/frontend/docker-entrypoint.d/40-write-config.sh`; if `node` exists, `node --check $P/sample-app/frontend/public/app.js`. Re-read `default.conf` for balanced braces and semicolons. No `docker build` unless
      Docker is available (then it is allowed, never push).

- [ ] 13. Create the generic Helm chart `$P\sample-app\charts\web-service\`.
      Files: `Chart.yaml` (`apiVersion: v2`, `name: web-service`, `type: application`, `version: 0.1.0`, `appVersion: "0.1.0"`), `.helmignore`, `values.yaml`, `templates\_helpers.tpl`, `templates\deployment.yaml`,
      `templates\service.yaml`, `templates\configmap.yaml`, `templates\serviceaccount.yaml`, `templates\ingress.yaml`, `templates\hpa.yaml`, `templates\NOTES.txt`.
      Behavior:
      - `fullnameOverride` and `nameOverride` supported through `_helpers.tpl`. Standard labels `app.kubernetes.io/name`, `instance`, `version`, `managed-by`, `part-of: developer-friendly-infra`.
      - Deployment: `replicaCount: 1`; image `{repository, tag, pullPolicy: IfNotPresent}` and fail the render with `required` if `image.repository` or `image.tag` is empty; `containerPort` and named port `http`; liveness and readiness probes from values
        (`httpGet` paths and timings, default `/healthz` and `/readyz`, port `http`); `resources` requests `cpu: 50m`, `memory: 64Mi`, limits `cpu: 200m`, `memory: 128Mi`; pod `securityContext` (`runAsNonRoot: true`, `runAsUser` and `fsGroup` from
        values, `seccompProfile: RuntimeDefault`); container `securityContext` (`allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities.drop: [ALL]`); `writableDirs` list (default `["/tmp"]`) turned into `emptyDir` volumes and mounts;
        `env` list (raw entries, supports `valueFrom`), `envFrom.configMap` toggle (the generated ConfigMap), `envFrom.secretRef.name` and `existingSecret` **by name only** (no Secret template in the chart); `podAnnotations`, `nodeSelector`, `tolerations`, `affinity` passthroughs;
        `automountServiceAccountToken: false` unless set.
      - ConfigMap: data from `config:` map in values (a plain key/value map).
      - Service: type `ClusterIP`, `port`, `targetPort: http`.
      - Ingress: rendered only when `ingress.enabled` is true; **default `enabled: false`**; `ingressClassName: alb`; `annotations` map from values; `hosts` and `paths` lists (`path`, `pathType`); no TLS block unless values give one. Comment at the top of the block: enabling this creates an
        AWS Application Load Balancer, which bills hourly.
      - HPA: only when `autoscaling.enabled` (default `false`), `autoscaling/v2`, CPU target. Comment: needs metrics-server (installed by the add-ons step).
      - ServiceAccount: created by default, `automountServiceAccountToken: false`.
      Verify: if `helm` is on PATH, `helm lint $P/sample-app/charts/web-service --set image.repository=x --set image.tag=y` and `helm template t $P/sample-app/charts/web-service --set image.repository=x --set image.tag=y`, then again with
      `--set ingress.enabled=true --set autoscaling.enabled=true`, and again with `-f` each of the two gitops values files after item 14. Check that the default render contains no `kind: Ingress`. If `helm` is missing, mark UNVERIFIED with the exact commands and re-read
      every template for indentation and `{{- }}` trim marks.

- [ ] 14. Create GitOps values and apps, catalog comments, CI workflow and the sample-app README.
      Read first: `$P\config\components.yaml`, `$P\scripts\verify-local.sh` (secret scan style), `c:\Devops\Repository\End-End-Project-Automate\output\fdp-mobile-bff\.github\workflows\ci-cd.yml`
      (copy the OIDC, Trivy and GitOps-bump ideas; do not copy static keys, `latest` tags, or the Slack step), the action rows in section 2 (resolve each version to a full commit SHA with the GitHub API).
      Files:
      - `$P\gitops\values\frontend.yaml` and `$P\gitops\values\backend.yaml`: `fullnameOverride`, `image.repository: 589389425618.dkr.ecr.us-east-1.amazonaws.com/dfi-frontend` (and `dfi-backend`), `image.tag` on **one line exactly like**
        `  tag: "REPLACE-AFTER-FIRST-CI-RUN"` (two-space indent, because the CI `sed` anchors on `^  tag: `), `containerPort` (8080 and 8000), `service.port`, `config` (backend `GREETING`), `env` (frontend `POD_NAME` from the downward API
        `fieldRef: metadata.name`, `APP_VERSION`, `ENVIRONMENT`, `BACKEND_URL`; backend `APP_VERSION` and `POD_NAME`), `ingress: { enabled: false, className: alb, annotations: {...}, hosts: [...] }` with `paths` `/` for the frontend and `/api` for the backend,
        and the ALB annotations as comments or values (`alb.ingress.kubernetes.io/scheme: internet-facing`, `target-type: ip`, a shared `group.name` so both apps use one ALB and not two). Add the two-line comment that a shared group means one ALB.
      - `$P\gitops\apps\frontend.yaml` and `$P\gitops\apps\backend.yaml`: ArgoCD `Application` named `sample-frontend` and `sample-backend`, `repoURL: REPLACE-WITH-YOUR-GIT-REPO-URL`, `targetRevision: main`, `path: sample-app/charts/web-service`,
        `helm.valueFiles: ["../../../gitops/values/<app>.yaml"]` (decision D11), destination `https://kubernetes.default.svc` namespace `dfi-sample`, `syncOptions: [CreateNamespace=true]`, **no `automated` block** (a comment explains the manual sync through the
        portal's gated deploy), `project: default`.
      - `$P\gitops\README.md`: layout of `apps\`, `values\`, `platform-addons\`; how CI edits `values\<app>.yaml`; how to create the Applications (`kubectl apply -f` is the user's own command, the portal cannot create apps); the repo-credentials note
        (public repo or an ArgoCD repo credential created by the user outside Git).
      - Edit `$P\config\components.yaml`: keep `components: []` as the only live line. Add two commented entries (`sample-frontend`, `sample-backend`; `argocd_app` equal to the Application names; `chart: web-service`; `chart_version: ""` with a comment that the
        Git branch name is not a chart version; `cluster_environments: [dev, staging]`) and a short "to enable: remove the leading `# ` from the two entries and replace `components: []` with `components:`" block. Do not break the existing comments.
      - `$P\.github\workflows\build-push.yml`: per decision D14 and D15. Triggers: `push` to `main` with `paths: ["sample-app/backend/**", "sample-app/frontend/**"]`. Top-level `permissions: {}` then per job. `concurrency: { group: build-push, cancel-in-progress: false }`.
        Job `detect`: `actions/checkout` (pinned SHA, `fetch-depth: 2`, `persist-credentials: false`), `git diff --name-only` between `github.event.before` and `github.sha` (build both apps when `before` is the all-zero SHA), outputs `backend` and `frontend` as `true` or `false`.
        Job `build` (matrix `app: [backend, frontend]`, `if` on the detect outputs, `permissions: { id-token: write, contents: read }`, `environment`-less): checkout, `aws-actions/configure-aws-credentials` with `role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}` and `aws-region: us-east-1`, `amazon-ecr-login`
        (step id `login`), `docker build` with tag `${{ steps.login.outputs.registry }}/dfi-<app>:${{ github.sha }}`, Trivy scan of that local image (severity `CRITICAL,HIGH`, `exit-code: '1'`, `ignore-unfixed: true`), then `docker push`. Never `latest`. Pass the SHA and app through `env:`
        and quote it in `run:`. Job `bump` (`needs: [detect, build]`, `if: always() && needs.build.result == 'success'`, `permissions: { contents: write }`): checkout with the default token, validate the SHA matches `^[0-9a-f]{40}$`, run the anchored `sed -E` on each changed app's values file, confirm with `grep` that the line holds the new SHA,
        configure the git user as `github-actions[bot]`, commit with a message ending in `[skip ci]`, `git pull --rebase` then `git push`. No ArgoCD call anywhere. Add a header comment: the secret name, that the ECR repos and role come from `terraform-shared`, branch protection note (the default token cannot push to a protected branch), and that a re-run for the same commit fails at push (immutable tags).
        Any SHA you cannot resolve is written as `CHECK-LATEST-FROM-<url>` in the `uses:` line (the workflow is then intentionally invalid until replaced) and listed in `VERSIONS.md`.
      - `$P\sample-app\README.md`: the flow in five short steps (edit code, push to main, CI builds and scans and pushes by SHA, CI edits `gitops/values`, you refresh and sync from the portal), the folder map, how to run locally, and the first-run note about the placeholder tag.
      Verify: `python -c "import yaml,sys; [list(yaml.safe_load_all(open(f, encoding='utf-8'))) for f in sys.argv[1:]]" $P/gitops/values/*.yaml $P/gitops/apps/*.yaml $P/.github/workflows/build-push.yml $P/config/components.yaml`; if `helm` exists, re-run the item 13
      renders with `-f $P/gitops/values/frontend.yaml` and `-f $P/gitops/values/backend.yaml`; `python -c "import yaml; print(yaml.safe_load(open(r'$P/config/components.yaml'))['components'])"` must print `[]`. If `actionlint` is on PATH, run it on the workflow (optional). Read the workflow once more to confirm: no static AWS keys, no `latest`, no `${{ }}` inside `run:` except the two safe fixed values passed through `env`.

### Part E. Portal frontend

Common rules for items 15 and 16: read `$P\frontend\src\api.ts`, `types.ts`, `useLoadable.ts`, `tone.ts`, `format.ts`, `styles.css`, `components\ClusterDetail.tsx`, `PodTable.tsx`, `ArgoPanel.tsx`, `EmptyState.tsx`, `ErrorBanner.tsx`, `StatusPill.tsx`,
`components\FindingsPanel.test.tsx` and `fixtures-boundary.test.ts`, and `$P\frontend\tsconfig.app.json` (strict options such as `noUncheckedIndexedAccess` are on: index into arrays with `?? fallback`). Tests use `renderToStaticMarkup` in a `node` vitest environment
(no jsdom, effects do not run). So every new component is split in two: a **pure presentational component** that takes data as props (tested), and a **thin container** that calls `useLoadable` (not rendered in tests). Test fixtures go in
`$P\frontend\src\test-fixtures\` and are imported only by `*.test.ts(x)` files. Keep the dark theme, the severity pills and the "no fabricated rows" rule. Do not add npm packages.

- [ ] 15. Pod detail panel: containers table and log viewer.
      Files:
      - Edit `$P\frontend\src\types.ts`: add `ContainerRow`, `ContainersResponse`, `LogsResponse` mirroring the backend shapes from items 7 to 9 (use the exact field names written there).
      - Edit `$P\frontend\src\api.ts`: add `containers(cluster, namespace, pod)` and `logs(cluster, namespace, pod, container, tail, previous)` with `encodeURIComponent` through the existing `q` helper.
      - Create `$P\frontend\src\components\ContainersTable.tsx` (pure): one row per container with kind (init or main), name, image tag (or short digest, or "none"), ready, restarts, state pill with reason and exit code, last-state chip, requests/limits text, and probe presence (L, R, S letters with a
        `title`/text label for accessibility). Empty list shows an `EmptyState`. Add `containerTone` to `tone.ts` if a new mapping is needed (running green, waiting yellow, terminated red or grey by exit code).
      - Create `$P\frontend\src\components\LogsView.tsx` (pure): props are the load state (`idle|loading|error|ready`), the log response, and no callbacks for fetching. Shows the fixed note "Logs are redacted best-effort. Do not treat them as safe to share.", a monospace `<pre>` for the text, a
        "truncated" line when `truncated` is true, and explicit states: empty text ("The container has written no log lines."), error (uses `ErrorBanner`), loading, and idle ("Pick a container").
      - Create `$P\frontend\src\components\PodDetail.tsx` (container): loads `api.containers`, shows `ContainersTable`, a container `<select>` (init and main names), a tail `<select>` with 50, 100, 200, 500, a "Previous container" checkbox, a Refresh button, and `LogsView`. Logs load only after the user picks a
        container, and on Refresh. The previous toggle is disabled with a hint when the chosen container has `restart_count` 0. A Close button calls `onClose`.
      - Edit `$P\frontend\src\components\PodTable.tsx`: add a "Details" button column that calls a new `onOpenDetails(name)` prop. Keep the existing columns and the Diagnose button and their `aria-label`s.
      - Edit `$P\frontend\src\components\ClusterDetail.tsx`: add `detailPod` state, reset it when the cluster or namespace changes (same pattern as `open`), render `PodDetail` under the pods table when set. Do not change the diagnose flow.
      - Edit `$P\frontend\src\styles.css`: only the classes the new components need (`.logs`, `.container-state` and similar), reusing existing colour variables.
      - Create fixtures `$P\frontend\src\test-fixtures\containers.sample.json` and `logs.sample.json`, and tests `ContainersTable.test.tsx` and `LogsView.test.tsx`: state pills and exit codes render, probe letters render, an image with a digest renders a short form, empty list, the redaction note always appears,
        the empty-log state, the error state, the truncated line, `<pre>` content is escaped (a log line containing `<script>` appears as `&lt;script&gt;`).
      - Edit `$P\frontend\src\fixtures-boundary.test.ts`: add one more `it` asserting no runtime file refers to `containers.sample`, `logs.sample` or `argocd-detail.sample`. Keep the existing tests unchanged.
      Verify: `cd $P/frontend && npm install && npm test && npm run build` (`npm run build` runs `tsc -b`, which is the type check). Mark UNVERIFIED if npm cannot run.

- [ ] 16. ArgoCD detail rows with Helm help text.
      Files:
      - Edit `$P\frontend\src\types.ts` and `api.ts`: add `ArgoAppDetail`, `ArgoAppDetailResponse` and `api.argoAppDetail(cluster, name)` (path `/api/argocd/apps/<name>?cluster=<cluster>`, name encoded).
      - Create `$P\frontend\src\components\ArgoAppDetailView.tsx` (pure): sections Source (type, repo URL, chart or path, target revision, value files, parameters as written with masked values shown as masked), Images (list), Sync and health (status pills and message), Last operation (phase pill, message, finished time),
        History (up to 10 rows: id, deployed time, revision shortened to 8 characters with the full value in `title`, source revision), and Out-of-sync resources (kind/namespace/name/status; or a plain "None" line). Always show the help text "ArgoCD renders Helm charts itself, so there is no `helm list` here.
        This view is the release state." Empty and missing fields show "n/a", never invented values.
      - Create `$P\frontend\src\components\ArgoAppRow.tsx` (container): an expandable row/button in `ArgoPanel` that loads `api.argoAppDetail` when expanded and shows `ArgoAppDetailView`, with `ErrorBanner` and a Retry; non-`ok` statuses (`not_configured`, `unreachable`, `unauthorized`, `not_found`, `error`) show an `EmptyState`
        with the backend message.
      - Edit `$P\frontend\src\components\ArgoPanel.tsx`: add an "Details" toggle per application row (keep the existing columns and states). Use a second `<tr>` with `colSpan` for the expanded content. Do not change the existing empty/error branches.
      - Edit `$P\frontend\src\styles.css` for the new classes only.
      - Create `$P\frontend\src\test-fixtures\argocd-detail.sample.json` and `ArgoAppDetailView.test.tsx`: Helm source rendering, masked parameter text, history limited to 10 and ordered as given, the Helm help text present, an app with no history and no images shows the n/a lines, out-of-sync list, status pills use `syncTone` and `healthTone`.
      Verify: `cd $P/frontend && npm test && npm run build`.

### Part F. Docs and verification script

Common rules for items 17 to 19: read the current `$P\README.md`, `$P\RUNBOOK.md`, `$P\VERSIONS.md`, `$P\docs\safety-model.md`, `$P\backend\README.md`, `$P\terraform-shared\README.md`, `$P\gitops\README.md`, `$P\sample-app\README.md`, and (for wording only)
`c:\Devops\Repository\Prepare-now\K8-Namespace-deployment.md` and `c:\Devops\Repository\Self-study-before-interview\K8-Real-scenario-debug.md`. Keep every existing honesty statement ("written, never run"). Every status cell for new work says `not run`. Cost tables are labelled
"estimates, recalled, not checked against AWS pricing; check the pricing pages and the Billing console".

- [ ] 17. `VERSIONS.md`, `scripts\verify-local.sh`, and the RUNBOOK download command.
      Files:
      - Edit `$P\VERSIONS.md`: insert at the **top**, directly under the title and intro paragraph, a table "Values to confirm before first run" built from section 2 of this plan (value, status, where it is used, source URL, and whether the placeholder text is still in the repo, which the coder checks by reading the files).
        Add the new pinned rows to "What is pinned and where": AWS LBC chart, metrics-server chart, EBS CSI (resolved at plan time), `terraform-shared` provider constraint, sample-app image tags, the pinned action versions with a note that SHAs are used.
      - Edit `$P\scripts\verify-local.sh`: after the existing Terraform step add `terraform-shared` (`terraform fmt -check -recursive`, `terraform init -backend=false -input=false`, `terraform validate`, each with `PASS/FAIL` via the existing `ok`/`bad`). Add a "helm" step: if `helm` is on PATH,
        run `helm lint` and `helm template` on `sample-app/charts/web-service` with `--set image.repository=x --set image.tag=y` and then with each `gitops/values/*.yaml`; else `skip "helm not installed"`. Add the sample-app backend tests as a separate invocation
        `(cd sample-app/backend && "${PY[@]}" -m pytest -q)` (its own process, so the two backends never share one pytest run). Add a YAML parse check for `gitops` and the workflow using Python. Keep the existing hygiene scan and extend the file list
        to include the new folders (it already scans all tracked files). Keep the guard header comment (no `terraform plan/apply/destroy`, no `aws`, no `kubectl` calls). `bash -n` already covers `scripts/*.sh`; also run `bash -n` on `sample-app/frontend/docker-entrypoint.d/*.sh`.
      Verify: `bash -n $P/scripts/verify-local.sh`; then `bash $P/scripts/verify-local.sh` if the shell works (it is read-only by design).

- [ ] 18. `README.md` and `docs\end-to-end.md`.
      Files:
      - Edit `$P\README.md`: replace the architecture box with (or add below it) an ASCII end-to-end diagram: developer push, GitHub Actions (OIDC, build, Trivy, push by SHA), ECR, CI edits `gitops/values/<app>.yaml`, portal Refresh then Plan then Sync (gate), ArgoCD,
        EKS, and the portal showing pods, containers, logs and ArgoCD/Helm state. Update the "Honest status" and "Phase status" tables with new rows (terraform-shared, add-ons, logs, containers, ArgoCD detail, sample app, chart, CI workflow, frontend additions), all `not run`, and the sentence that **nothing is verified**.
        Add "What this adds to the bill" (table: ECR storage and lifecycle policy, IAM and OIDC free, EBS CSI driver free but volumes bill, metrics-server and LBC free but use node capacity, the ALB only when the sample Ingress is enabled, NAT data transfer when images are pulled from ECR through the NAT; give rough figures and label them estimates). Extend "What is in scope", "Layout"
        and the "Phases" list (Phase 3 is this work; authentication moves to Phase 4). Do not remove the existing safety stance bullets; add one for logs and one for CI trust. Link to `docs/end-to-end.md`.
      - Create `$P\docs\end-to-end.md` (write in chunks): walkthrough from an empty account to a running sample app: prerequisites; (1) offline checks; (2) state bucket (link RUNBOOK step 3); (3) `terraform-shared` apply first, with the OIDC choice and the `-var github_org/github_repo`; (4) `provision.sh` (add-ons step, `INSTALL_ADDONS`); (5) push the repo to GitHub and set the secret
        `AWS_DEPLOY_ROLE_ARN`; (6) first CI run and the tag bump; (7) create the two ArgoCD Applications after replacing `REPLACE-WITH-YOUR-GIT-REPO-URL` and adding repo credentials if private; (8) add the catalog entries and the RBAC lines for the deploy account (`p, role:dfi-deploy, applications, get|sync, default/sample-frontend, allow` and the same for backend);
        (9) first deploy through the portal (Refresh, Plan, typed phrase, Sync); (10) look at pods, containers, logs and ArgoCD detail in the portal; (11) reach the app with `kubectl port-forward` first (free), then the optional ALB by setting `ingress.enabled: true` in the values file (cost note, ALB hourly charge, how long to wait, how to turn it off again);
        (12) teardown order: set `ingress.enabled: false` and sync (or delete the Ingress), delete the ArgoCD sample apps, `./scripts/destroy.sh <name>` per cluster, then optionally `terraform destroy` in `terraform-shared` (delete ECR images first on purpose). Include a short "how Kubernetes objects relate" paragraph (Deployment, ReplicaSet, Pod, Service, Ingress, ConfigMap)
        in plain words, with wording taken from the two study files, and one line per place the 15 diagnose checks help. Every command is the user's to run and is marked as such; each costly step is marked **COSTS MONEY**.
      Verify: read both files fully once; confirm every file path and script name they mention exists (use `read_file` on each path). If `python` works, run a small script that extracts relative links `](...)` from the two markdown files and checks each target exists.

- [ ] 19. `RUNBOOK.md`, `docs\safety-model.md` and final consistency pass.
      Files:
      - Edit `$P\RUNBOOK.md`: update "Order at a glance" with new steps (shared stack before the cluster; add-ons are part of step 4; CI and sample app after step 6). Add a section for the shared stack (init, plan, apply, outputs, secret), the OIDC choice (how to check, which to set), the LBC policy download and compare command from item 4, the `INSTALL_ADDONS` flag,
        the add-ons check commands (`kubectl --context <name> -n argocd get applications`, `kubectl --context <name> get apiservices | grep metrics`), the sample app steps, the optional ALB, teardown additions (Ingress first), and a "what this adds to the bill" table (same numbers as the README). Update step 8 (metrics-server now comes from the add-ons step unless `INSTALL_ADDONS=0`), step 11 (settings table: `INSTALL_ADDONS`; the log limits are constants,
        not settings) and step 12 (troubleshooting rows: ECR push `denied` or immutable tag exists, OIDC `Not authorized to perform sts:AssumeRoleWithWebIdentity`, Ingress without an address, `ImagePullBackOff` on the placeholder tag, LBC pod not Ready, `/api/logs` shows 502, ArgoCD app `ComparisonError`).
      - Edit `$P\docs\safety-model.md`: add layer rows or sections for "Cluster add-ons" (installed through ArgoCD from pinned official charts, Pod Identity roles, IAM policy file is a pinned copy), "CI trust" (OIDC role limited to one repo and one branch, ECR push/pull on two repos only, immutable tags, no static keys, Trivy before push, actions pinned to commit SHAs and why, the bump job holds `contents: write` but not `id-token`, CI never calls ArgoCD),
        and extend "What does not exist, on purpose" and "Known limits" (log redaction is best effort, ECR and the OIDC role are not live-checked, the default token cannot push to a protected branch, the sample apps use manual sync). Do not remove or soften any existing text. `docs\diagnose-checks.md` is not changed (no check's behavior changes); say so in `verification.md`.
      - Final consistency pass (read, then fix): every name used in more than one file matches (`sample-frontend`, `sample-backend`, `dfi-sample`, `dfi-frontend`, `dfi-backend`, `AWS_DEPLOY_ROLE_ARN`, `INSTALL_ADDONS`, `_shared`, chart `3.6.2`, `3.14.0`); no em dashes or exclamation points in new prose; no real-looking secrets; `config/components.yaml` still ships `components: []`.
      Verify: `cd $P/backend && python -m pytest -q`; `cd $P/frontend && npm test`; `bash $P/scripts/verify-local.sh`. If the shell is down, UNVERIFIED with these exact commands.

## 4. Deliverables in the artifact folder

All under `c:\Devops\Repository\devops-microservices-platform\.agents\tasks\phase3-idp\`.

| File | Written by | Content |
|------|------------|---------|
| `plan.md` | planner (this file) | the plan |
| `verification.md` | each coder appends a `## FEAT-00N` section | every check with the exact command and `PASSED` or `UNVERIFIED` (never invent a pass), plus the placeholders that remain |
| `review.md`, `review.json` | reviewer | `review.json` shape: `{ "verdict": "APPROVED" or "CHANGES_REQUESTED", "reviewDoc": "<path to review.md>", "findings": ["..."] }` |
| `SUMMARY.md` | finalize step | what was built per part, what ran (probably nothing), the table "Values to confirm", the UNVERIFIED command list, exact git commands for the user, known limits |

Git commands for the user (the finalize step prints these, it does not run them):

```
cd c:\Devops\Repository\Developer-friendly-infra
git status
git init                       # only if the folder is not already a repository
git add -A
git commit -m "Phase 3: shared registry stack, add-ons, logs/containers/ArgoCD detail, sample app, CI, portal views, docs"
```

Lockfiles to generate before committing: `terraform/.terraform.lock.hcl` and `terraform-shared/.terraform.lock.hcl` (`terraform init`), and `frontend/package-lock.json` (`npm install`).

## 5. Coverage check against the task

| Task part | Plan items |
|-----------|-----------|
| A registry and CI trust | 1, 2 |
| B add-ons (Terraform, GitOps, scripts) | 3, 4, 5, 6 |
| C1 logs | 7, 8 |
| C2 containers | 9 |
| C3 ArgoCD and Helm detail | 10 |
| D sample app, chart, gitops, CI | 11, 12, 13, 14 |
| E frontend | 15, 16 |
| F docs and verify-local | 17, 18, 19 |

