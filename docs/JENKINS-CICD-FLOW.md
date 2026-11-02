# Jenkins CI/CD Pipeline Flow

A single picture of the full pipeline, then the steps to add each tool.

Project facts used below: AWS account `589389425618`, region `us-east-1`, ECR repos
`order-service` / `payment-service` / `user-service`, cluster `expense-dev`, GitOps via ArgoCD.

## The flow in one picture

```
                              JENKINS CI JOB
  +-----------------------------------------------------------------------------+
  |                                                                             |
  |   GitHub ---- pull code ----> Jenkins CI ---- dependency ----> OWASP        |
  |     ^                              |          (dependency check)  |         |
  |     |                              |                              |         |
  |     | push code                   | docker build & push    code + quality  |
  |     |                             v                         gate analysis   |
  |  Developer                      Docker <---- build/push ----> SonarQube     |
  |                                    ^                                        |
  |                                    | image                                  |
  |                                 Trivy  (filesystem / image scan)            |
  +-----------------------------------|-----------------------------------------+
                                      | trigger Jenkins CD job
                                      v
                              JENKINS CD JOB
  +-----------------------------------------------------------------------------+
  |                                                                             |
  |   Jenkins CD --- update image tag ---> GitHub --- pull ---> Argo CD         |
  |                                                                 |           |
  |                                                                 | deploy    |
  |                                                                 v           |
  |   Email <-- notify -- Grafana <-- Prometheus <-- monitor -- Kubernetes      |
  |                                                                             |
  +-----------------------------------------------------------------------------+
```

Read it as two jobs:

- **CI job:** build, scan, and push a trusted image. It never touches the cluster.
- **CD job:** write the new image tag to Git. ArgoCD (pull based) deploys it. Prometheus and
  Grafana watch the result, and an email reports the outcome.

The handover is the key idea: **CI ends by committing the image tag to Git, and ArgoCD starts by
reading that Git change.** Push based CI, pull based CD. Jenkins never runs `kubectl apply`.

## What each tool does

| Tool | Job | Stops the pipeline on failure? |
|------|-----|--------------------------------|
| OWASP Dependency-Check | Finds known-vulnerable libraries in your dependencies | Optional (set a CVSS threshold) |
| SonarQube | Code quality and a pass/fail quality gate | Yes, on gate fail |
| Docker | Builds the image and pushes it to ECR | Yes, on build or push error |
| Trivy | Scans the image for HIGH and CRITICAL vulnerabilities | Yes, when set to exit 1 |
| ArgoCD | Pulls the Git change and deploys the Helm chart to EKS | n/a (runs after Jenkins) |
| Prometheus | Scrapes metrics from pods and nodes | n/a |
| Grafana | Dashboards and alerts | n/a |
| Email | Notifies success or failure | n/a |

## Steps to add each piece

### 1. OWASP Dependency-Check

Install the "OWASP Dependency-Check" plugin (Manage Jenkins -> Plugins), then add a tool
installation named `OWASP-DC` under Manage Jenkins -> Tools.

```groovy
stage('OWASP Dependency Check') {
  steps {
    dependencyCheck additionalArguments: '--scan ./ --format XML --format HTML', odcInstallation: 'OWASP-DC'
    dependencyCheckPublisher pattern: '**/dependency-check-report.xml'
  }
}
```

First run is slow because it downloads the CVE database. Later runs reuse the cached data.

### 2. SonarQube quality gate

Add the server under Manage Jenkins -> System -> SonarQube servers (name `SonarQube`), add the
token as a Secret text credential, and install the SonarQube Scanner plugin.

```groovy
stage('SonarQube Analysis') {
  steps {
    dir("app/${env.SERVICE_NAME}") {
      withSonarQubeEnv('SonarQube') {
        sh 'sonar-scanner -Dsonar.projectKey=${SERVICE_NAME} -Dsonar.sources=.'
      }
    }
  }
}
stage('Quality Gate') {
  steps {
    timeout(time: 5, unit: 'MINUTES') {
      waitForQualityGate abortPipeline: true
    }
  }
}
```

`abortPipeline: true` is what makes a bad gate stop the build before the image is made.

### 3. Docker build and push to ECR

The agent needs Docker and the AWS CLI, and credentials that can push to ECR.

```groovy
environment {
  REGISTRY = "589389425618.dkr.ecr.us-east-1.amazonaws.com"
}
stage('Docker Build & Push') {
  steps {
    sh '''
      aws ecr get-login-password --region us-east-1 \
        | docker login --username AWS --password-stdin ${REGISTRY}
      docker build -t ${REGISTRY}/${SERVICE_NAME}:${IMAGE_TAG} app/${SERVICE_NAME}
      docker push ${REGISTRY}/${SERVICE_NAME}:${IMAGE_TAG}
    '''
  }
}
```

Use a unique tag, such as the build number or the Git SHA. Do not push `latest`, because the ECR
repos are set to IMMUTABLE and a repeat `latest` push fails.

### 4. Trivy image scan

Install Trivy on the agent once:

```bash
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sudo sh -s -- -b /usr/local/bin
```

Then add the stage after the push:

```groovy
stage('Trivy Scan') {
  steps {
    sh 'trivy image --severity HIGH,CRITICAL --exit-code 1 --no-progress ${REGISTRY}/${SERVICE_NAME}:${IMAGE_TAG}'
  }
}
```

`--exit-code 1` fails the build when a HIGH or CRITICAL issue is found. Drop it to `0` if you only
want a report at first.

### 5. CD job: update the image tag in Git (the handover)

This is the only deploy action Jenkins takes. It edits the Helm values and pushes, then stops.

```groovy
stage('Update GitOps Repo') {
  steps {
    withCredentials([usernamePassword(credentialsId: 'github-pat', usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
      sh '''
        sed -i "s|tag:.*|tag: ${IMAGE_TAG}|" charts/microservice/values-${SERVICE_NAME#*-}.yaml
        git config user.email "ci@bot.local"
        git config user.name "ci-bot"
        git commit -am "deploy ${SERVICE_NAME} ${IMAGE_TAG} [skip ci]"
        git push https://${GH_USER}:${GH_TOKEN}@github.com/ShivaKrishna44/devops-microservices-platform.git HEAD:main
      '''
    }
  }
}
```

`[skip ci]` keeps this commit from starting a second build. The values file name uses `${SERVICE_NAME#*-}`,
so `order-service` maps to `values-order.yaml`.

### 6. ArgoCD deploys (no Jenkins stage)

Create the ArgoCD applications once. After that ArgoCD watches Git and syncs on its own.

```bash
kubectl apply -f kubernetes/argocd/apps/
kubectl get applications -n argocd
```

With auto-sync on, ArgoCD applies the new tag within a few minutes. To apply at once, hard-refresh
and sync in the ArgoCD UI, or `argocd app sync <name>`.

### 7. Prometheus and Grafana (install once)

Not a pipeline stage. Install the kube-prometheus-stack with Helm, as in `DEPLOYMENT-GUIDE.md`.
Grafana then shows pod and node metrics, and you add alert rules there (for example pod restarts,
node CPU, pod not ready).

### 8. Email notification

Set up email under Manage Jenkins -> System (SMTP), then add a `post` block so every run reports.

```groovy
post {
  success {
    mail to: 'you@example.com',
         subject: "BUILD OK: ${env.SERVICE_NAME} ${env.IMAGE_TAG} (#${env.BUILD_NUMBER})",
         body: "Image pushed and image tag updated in Git. ArgoCD will deploy it."
  }
  failure {
    mail to: 'you@example.com',
         subject: "BUILD FAILED: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
         body: "See ${env.BUILD_URL}console"
  }
}
```

## Stage order in the Jenkinsfile

```
Checkout
  -> OWASP Dependency Check
  -> SonarQube Analysis
  -> Quality Gate (abort on fail)
  -> Docker Build & Push (to ECR)
  -> Trivy Scan (fail on HIGH/CRITICAL)
  -> Update GitOps Repo (commit image tag to Git)
  -> [ArgoCD deploys from Git, outside Jenkins]
  -> post: email success or failure
```

## Interview points

- **Two jobs, one handover.** CI builds and proves the image. CD writes the tag to Git. ArgoCD pulls
  and deploys. Jenkins never deploys to the cluster directly.
- **Three gates before deploy.** OWASP for dependencies, SonarQube for code quality, Trivy for the
  image. Each can stop the pipeline, so bad code or a vulnerable image never reaches the cluster.
- **Push CI, pull CD.** The security benefit is that the cluster is not exposed to the CI system.
  ArgoCD reaches out to Git, not the other way round.
- **Immutable tags.** Unique image tags per build give clean rollbacks and a clear audit of what runs.
- **The agent runs the work.** Docker and the AWS CLI live on the Jenkins agent (an EC2 box here),
  not the controller.
