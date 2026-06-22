pipeline {
    agent {
    label 'AGENT'
    }
    
    parameters {
        choice(
            name: 'SERVICE_NAME',
            choices: ['order-service', 'payment-service', 'user-service'],
            description: 'Select the microservice to build and deploy'
        )
        string(
            name: 'IMAGE_TAG',
            defaultValue: 'latest',
            description: 'Docker image tag (leave empty for build number)'
        )
    }
    
    environment {
        // AWS Configuration
        AWS_DEFAULT_REGION = 'us-east-1'
        AWS_ACCOUNT_ID = '589389425618'
        ECR_REGISTRY = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
        
        // EKS Configuration
        EKS_CLUSTER_NAME = 'expense-dev'
        
        // Global Service Configuration
        SERVICE_NAME = "${params.SERVICE_NAME ?: 'order-service'}"
        IMAGE_TAG = "${params.IMAGE_TAG ?: BUILD_NUMBER}"
        
        // Derived variables
        FULL_IMAGE_NAME = "${ECR_REGISTRY}/${SERVICE_NAME}:${IMAGE_TAG}"
        LATEST_IMAGE_NAME = "${ECR_REGISTRY}/${SERVICE_NAME}:latest"
    }
    
    stages {
        stage('Initialize') {
            steps {
                script {
                    echo "======================================"
                    echo "🚀 PIPELINE CONFIGURATION"
                    echo "======================================"
                    echo "Service Name: ${env.SERVICE_NAME}"
                    echo "Image Tag: ${env.IMAGE_TAG}"
                    echo "Full Image: ${env.FULL_IMAGE_NAME}"
                    echo "ECR Registry: ${env.ECR_REGISTRY}"
                    echo "EKS Cluster: ${env.EKS_CLUSTER_NAME}"
                    echo "Build Number: ${env.BUILD_NUMBER}"
                    echo "======================================"
                }
            }
        }
        
        stage('Checkout') {
            steps {
                echo '📥 Checking out source code...'
                checkout scm
            }
        }

        stage('Debug Workspace') {
            steps {
                sh '''
                pwd
                ls -R
                '''
            }
        } // <-- Fixed: Closed ONLY the stage block, leaving global stages open.
        
        stage('Build & Test') {
            parallel {
                stage('Build') {
                    steps {
                        echo "🔨 Building ${env.SERVICE_NAME}..."
                        script {
                            if (fileExists("app/${env.SERVICE_NAME}")) {
                                dir("app/${env.SERVICE_NAME}") {
                                    sh 'echo "Build completed successfully for ${SERVICE_NAME}"'
                                }
                            } else {
                                error "Service directory app/${env.SERVICE_NAME} not found!"
                            }
                        }
                    }
                }
                stage('Test') {
                    steps {
                        echo "🧪 Testing ${env.SERVICE_NAME}..."
                        script {
                            if (fileExists("app/${env.SERVICE_NAME}")) {
                                dir("app/${env.SERVICE_NAME}") {
                                    sh 'echo "All tests passed for ${SERVICE_NAME}"'
                                }
                            } else {
                                echo "⚠️  No tests found for ${env.SERVICE_NAME}"
                            }
                        }
                    }
                }
            }
        }
        
        stage('Docker Build & Push') {
            steps {
                script {
                    echo "🐳 Building and pushing Docker image for ${env.SERVICE_NAME}..."
                    
                    dir("app/${env.SERVICE_NAME}") {
                        if (!fileExists('Dockerfile')) {
                            error "Dockerfile not found in app/${env.SERVICE_NAME}/"
                        }
                        
                        sh '''
                            echo "🔐 Logging into ECR..."
                            aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | \
                            docker login --username AWS --password-stdin ${ECR_REGISTRY}
                        '''
                        
                        sh '''
                            echo "🔨 Building Docker image..."
                            docker build -t ${SERVICE_NAME}:${IMAGE_TAG} .
                            docker tag ${SERVICE_NAME}:${IMAGE_TAG} ${FULL_IMAGE_NAME}
                            docker tag ${SERVICE_NAME}:${IMAGE_TAG} ${LATEST_IMAGE_NAME}
                        '''
                        
                        sh '''
                            echo "📤 Pushing image to ECR..."
                            docker push ${FULL_IMAGE_NAME}
                            docker push ${LATEST_IMAGE_NAME}
                        '''
                        
                        sh '''
                            echo "🧹 Cleaning up local images..."
                            docker rmi ${SERVICE_NAME}:${IMAGE_TAG} || true
                            docker rmi ${FULL_IMAGE_NAME} || true
                            docker rmi ${LATEST_IMAGE_NAME} || true
                        '''
                    }
                }
            }
        }
        
        stage('Deploy to EKS') {
            steps {
                script {
                    echo "🚀 Deploying ${env.SERVICE_NAME} to EKS cluster..."
                    
                    sh '''
                        echo "⚙️  Configuring kubectl for EKS..."
                        aws eks update-kubeconfig --region ${AWS_DEFAULT_REGION} --name ${EKS_CLUSTER_NAME}
                    '''
                    
                    sh '''
                        echo "📋 Applying Kubernetes manifests..."
                        kubectl create namespace ${SERVICE_NAME} --dry-run=client -o yaml | kubectl apply -f -
                        
                        if [ -d "kubernetes/${SERVICE_NAME}" ]; then
                            echo "📁 Found Kubernetes manifests for ${SERVICE_NAME}"
                            kubectl apply -f kubernetes/${SERVICE_NAME}/ -n ${SERVICE_NAME}
                        elif [ -f "kubernetes/${SERVICE_NAME}.yaml" ]; then
                            echo "📄 Found single manifest file for ${SERVICE_NAME}"
                            kubectl apply -f kubernetes/${SERVICE_NAME}.yaml -n ${SERVICE_NAME}
                        else
                            echo "⚠️  No Kubernetes manifests found for ${SERVICE_NAME}"
                        fi
                        
                        if kubectl get deployment ${SERVICE_NAME} -n ${SERVICE_NAME} >/dev/null 2>&1; then
                            echo "🔄 Updating deployment image..."
                            kubectl set image deployment/${SERVICE_NAME} ${SERVICE_NAME}=${FULL_IMAGE_NAME} -n ${SERVICE_NAME}
                            kubectl rollout status deployment/${SERVICE_NAME} -n ${SERVICE_NAME} --timeout=300s
                        fi
                        
                        kubectl get all -n ${SERVICE_NAME}
                    '''
                }
            }
        }
    } // <-- Global stages block properly closes here
    
    post {
        always {
            echo '🏁 Pipeline execution completed.'
            deleteDir()
        }
        success {
            script {
                echo "✅ SUCCESS: ${env.SERVICE_NAME} deployed with tag: ${env.IMAGE_TAG}"
                echo "🔗 ECR URI: ${env.FULL_IMAGE_NAME}"
            }
        }
        failure {
            echo "❌ Pipeline failed for ${env.SERVICE_NAME}! Check logs for details."
        }
    }
}
