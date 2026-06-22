pipeline {
    agent {
        label 'agent-1'
    }

    stages {
        stage('Test') {
            steps {
                sh 'hostname'
                sh 'whoami'
            }
        }
    }
}