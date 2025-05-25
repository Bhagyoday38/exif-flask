pipeline {
    agent any
    
    environment {
        DOCKER_IMAGE = 'exif-flask-app'
        DOCKER_TAG = "${env.BUILD_NUMBER}"
        // Add this line to grab the branch name from the Generic Webhook Trigger
        BRANCH_NAME = "${env.branch ?: 'main'}"  // Use 'main' as default if branch is not set
    }
    
    stages {
        stage('Debug Information') {
            steps {
                // Add this stage to help debug webhook issues
                echo "Building branch: ${BRANCH_NAME}"
                echo "Build triggered by Generic Webhook Trigger"
                echo "Build number: ${env.BUILD_NUMBER}"
            }
        }
        
        stage('Setup') {
            steps {
                sh 'pip install --upgrade pip'
                sh 'pip install pytest pytest-cov'
                sh 'pip install -r requirements.txt || echo "Warning: Some dependencies may not have installed correctly. Continuing with build..."'
            }
        }
        
        stage('Test') {
            steps {
                sh 'mkdir -p test-reports'
                sh 'python -m pytest test_app.py -v --junitxml=test-reports/test-results.xml'
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-reports/*.xml'
                }
            }
        }
        
        stage('Build Docker Image') {
            steps {
                script {
                    // Add verbose output to debug Docker build issues
                    sh "docker build --no-cache -t ${DOCKER_IMAGE}:${DOCKER_TAG} ."
                    sh "docker tag ${DOCKER_IMAGE}:${DOCKER_TAG} ${DOCKER_IMAGE}:latest"
                }
            }
        }
        
        stage('Deploy Application') {
            steps {
                script {
                    // Stop and remove any existing containers
                    sh "docker stop ${DOCKER_IMAGE}-app || true"
                    sh "docker rm ${DOCKER_IMAGE}-app || true"
                    
                    // Deploy the new container
                    sh "docker run -d -p 5001:5001 --name ${DOCKER_IMAGE}-app ${DOCKER_IMAGE}:${DOCKER_TAG}"
                    
                    echo "Application deployed successfully to http://localhost:5001"
                }
            }
        }
    }
    
    post {
        success {
            echo 'Pipeline completed successfully! Your application is now available at http://localhost:5001'
        }
        failure {
            echo 'Pipeline failed! Check the logs for details.'
        }
        always {
            cleanWs()
        }
    }
}