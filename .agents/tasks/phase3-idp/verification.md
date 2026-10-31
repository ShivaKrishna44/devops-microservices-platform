# Verification log: Phase 3 IDP

Each feature appends a section. PASSED means the command ran and succeeded.
UNVERIFIED means the command was not run (the shell returned Exit Code -1 with no output) and the exact command is listed so you can run it.

## FEAT-001

Shell state: `execute_bash` returned `Exit Code: -1` with no output (tried `which terraform python python3` and `ls`). No command could be run. The files were re-read after writing instead.

| # | Check | Exact command | Result |
|---|-------|---------------|--------|
| 1 | terraform-shared fmt, init, validate | `cd c:/Devops/Repository/Developer-friendly-infra/terraform-shared && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate` | UNVERIFIED |
| 2 | terraform fmt, init, validate | `cd c:/Devops/Repository/Developer-friendly-infra/terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate` | UNVERIFIED |
| 3 | LBC policy file is valid JSON | `python -c "import json,sys; json.load(open(sys.argv[1]))" c:/Devops/Repository/Developer-friendly-infra/terraform/policies/aws-load-balancer-controller-iam-policy.json` | UNVERIFIED |
| 4 | Manual re-read of the LBC policy file | read_file on the full file | PASSED by reading: starts with `{`, Version `2012-10-17`, 16 `"Effect": "Allow"` statements (the source at tag v3.6.2 has 16), braces and brackets balance, no leftover chunk marker |
| 5 | Manual re-read of new .tf files | read_file on each file | PASSED by reading: references resolve (`aws_iam_role.ebs_csi`, `aws_iam_role.lbc`, `aws_iam_policy.lbc`, `aws_ecr_repository.this`, `local.name`, `local.github_oidc_provider_arn`), alignment written to match `terraform fmt`. This is not a substitute for check 1 and 2. |

Note on `terraform init -backend=false`: it downloads providers and modules from the internet and writes `.terraform.lock.hcl`. Neither lock file exists yet.

### Real policy file, no placeholder

The LBC policy file is the real JSON fetched from
`https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v3.6.2/docs/install/iam_policy.json`
(8955 bytes). It is not a placeholder file.

### Placeholders left in FEAT-001 files

None. No `CHECK-LATEST-FROM-` text was needed.

### Deviation from plan.md section 2

The plan listed the EBS CSI managed policy as `arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy` (placeholder until read).
The current AWS doc (`https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html`) names `arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2`.
`terraform/ebs-csi.tf` uses the V2 ARN from the doc. If `terraform plan` reports the policy does not exist, switch to the older policy ARN.
This is an ARN taken from an official doc, not an invented value, but it has not been checked against IAM with a command.

### Values read from official sources for FEAT-001

- Pod Identity trust: principal `pods.eks.amazonaws.com`, actions `sts:AssumeRole` and `sts:TagSession` (AWS doc pod-id-association).
- EBS CSI service account `ebs-csi-controller-sa`, namespace `kube-system` (AWS doc ebs-csi).
- `aws_iam_openid_connect_provider`: `thumbprint_list` is optional (AWS provider docs), so it is omitted.
- Module `terraform-aws-modules/eks/aws` v21.29.0: add-on input `pod_identity_association` takes `role_arn` and `service_account` (module main.tf at that tag).

## FEAT-002

Shell state: `execute_bash` returned `Exit Code: -1` with no output (tried the bash -n / python command and a plain `echo hi`). No command could be run. The three scripts and the new manifests were re-read after writing instead.

| # | Check | Exact command | Result |
|---|-------|---------------|--------|
| 1 | bash syntax of the three scripts | `bash -n c:/Devops/Repository/Developer-friendly-infra/scripts/common.sh && bash -n c:/Devops/Repository/Developer-friendly-infra/scripts/provision.sh && bash -n c:/Devops/Repository/Developer-friendly-infra/scripts/destroy.sh` | UNVERIFIED |
| 2 | add-on YAML parses | `python -c "import yaml,sys; [list(yaml.safe_load_all(open(f, encoding='utf-8'))) for f in sys.argv[1:]]" c:/Devops/Repository/Developer-friendly-infra/gitops/platform-addons/metrics-server.yaml c:/Devops/Repository/Developer-friendly-infra/gitops/platform-addons/aws-load-balancer-controller.yaml` | UNVERIFIED |
| 3 | provision.sh dry run | `cd c:/Devops/Repository/Developer-friendly-infra && echo dev-eu \| DRY_RUN=1 REGISTRY_PATH=/tmp/r.json PUBLIC_ACCESS_CIDRS=203.0.113.7/32 TF_STATE_BUCKET=dummy bash scripts/provision.sh dev-eu staging` (needs terraform, aws, kubectl on PATH). Expect a line "DRY-RUN would apply add-on ... (renders without leftover placeholders)" for each of the two files. | UNVERIFIED |
| 3b | provision.sh with add-ons off | same as 3 with `INSTALL_ADDONS=0` added. Expect "Skipping platform add-ons". Also `INSTALL_ADDONS=2` must stop with "invalid INSTALL_ADDONS". | UNVERIFIED |
| 4 | destroy.sh dry run | `cd c:/Devops/Repository/Developer-friendly-infra && echo dev-eu \| DRY_RUN=1 REGISTRY_PATH=/tmp/r.json TF_STATE_BUCKET=dummy bash scripts/destroy.sh dev-eu` | UNVERIFIED |
| 5 | Manual re-read of the three scripts | read_file on the edited regions | PASSED by reading: every expansion is quoted, no eval, no sed, no GNU-only flag; `render_addon` uses `${text//__X__/$value}` after regex checks; a failed render happens before `kc apply`; wait failure ends in `false` so the existing `on_error` trap runs; destroy.sh uses its own `ing_waited` counter so the Service wait still starts at 0. This is not a substitute for checks 1 to 4. |
| 6 | Manual re-read of both manifests | read_file | PASSED by reading: chart versions 3.14.0 and 3.6.2, official repo URLs, only the three placeholders in the LBC file, no Secret value, no placeholder-looking text in comments. |

### Values re-read from official sources for FEAT-002

- `https://kubernetes-sigs.github.io/metrics-server/index.yaml`: chart `metrics-server` version 3.14.0, app version 0.9.0.
- `https://aws.github.io/eks-charts/index.yaml`: chart `aws-load-balancer-controller` version 3.6.2, app version v3.6.2.
- Chart `values.yaml` files (master branch) were read. Keys used exist: metrics-server `replicas`, `resources.requests`; controller `clusterName`, `region`, `vpcId`, `replicaCount`, `serviceAccount.create`, `serviceAccount.name`, `resources.requests`.
- The master `values.yaml` was used, not the file inside each tagged chart. The keys used are long-standing, but this was not diffed against the 3.14.0 and 3.6.2 packages.

### Not confirmed

- `kubectl wait --for=condition=Established crd/applications.argoproj.io` and `kubectl get application -o jsonpath` were not run against a cluster.
- The script polls Application health with `kubectl get ... -o jsonpath` in a retry loop (40 tries, 15 s apart) instead of `kubectl wait --for=jsonpath`, because `wait` behaviour on a not-yet-set status field was not checked.

### Placeholders left

No `CHECK-LATEST-FROM-` text. The manifests use `__CLUSTER_NAME__`, `__REGION__`, `__VPC_ID__` on purpose (filled by `render_addon`).
