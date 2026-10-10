// Jenkins BUILD & Quality Gate for ACEest Fitness & Gym.
//
// Every run starts from an empty workspace, pulls the latest code from GitHub,
// builds a fresh Python environment, lints, runs the test suite with a coverage
// gate, then builds the Docker images and smoke-tests the runtime container.
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
        skipDefaultCheckout(true)
    }

    // The lab VM is not reachable from GitHub webhooks, so poll for new commits.
    triggers {
        pollSCM('H/5 * * * *')
    }

    environment {
        IMAGE_NAME     = 'aceest-fitness'
        IMAGE_TAG      = "${env.BUILD_NUMBER}"
        SMOKE_NAME     = "aceest-smoke-${env.BUILD_NUMBER}"
        COVERAGE_MIN   = '90'
        PIP_NO_CACHE_DIR = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                deleteDir()
                checkout scm
                sh 'git log -1 --pretty="Building %h: %s (%an)"'
            }
        }

        stage('Setup Environment') {
            steps {
                sh '''
                    python3 --version
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    . .venv/bin/activate
                    python -m compileall -q app.py aceest tests
                    flake8
                '''
            }
        }

        stage('Unit Tests & Coverage Gate') {
            steps {
                sh '''
                    . .venv/bin/activate
                    pytest -v \
                        --junitxml=reports/junit.xml \
                        --cov=aceest \
                        --cov-report=term-missing \
                        --cov-report=xml:reports/coverage.xml \
                        --cov-fail-under=${COVERAGE_MIN}
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    docker build --pull --target test -t ${IMAGE_NAME}:test-${IMAGE_TAG} .
                    docker build --target runtime \
                        -t ${IMAGE_NAME}:${IMAGE_TAG} -t ${IMAGE_NAME}:latest .
                    docker images ${IMAGE_NAME}
                '''
            }
        }

        stage('Container Tests') {
            steps {
                sh 'docker run --rm ${IMAGE_NAME}:test-${IMAGE_TAG}'
            }
        }

        stage('Container Smoke Test') {
            steps {
                // No port is published, so this cannot clash with an app already
                // running on the host; Docker's HEALTHCHECK hits /health internally.
                sh '''
                    docker run -d --name ${SMOKE_NAME} -e SECRET_KEY=jenkins-smoke ${IMAGE_NAME}:${IMAGE_TAG}
                    for i in $(seq 1 30); do
                        status=$(docker inspect -f '{{.State.Health.Status}}' ${SMOKE_NAME})
                        echo "Health: ${status}"
                        [ "${status}" = "healthy" ] && break
                        [ "${status}" = "unhealthy" ] && break
                        sleep 2
                    done
                    docker logs ${SMOKE_NAME}
                    [ "${status}" = "healthy" ]
                    [ "$(docker exec ${SMOKE_NAME} whoami)" = "app" ]
                '''
            }
        }
    }

    post {
        always {
            sh '''
                docker rm -f ${SMOKE_NAME} >/dev/null 2>&1 || true
                docker rmi ${IMAGE_NAME}:test-${IMAGE_TAG} >/dev/null 2>&1 || true
            '''
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
        }
        success {
            echo "BUILD PASSED: ${IMAGE_NAME}:${IMAGE_TAG} is ready."
        }
        failure {
            echo 'BUILD FAILED: see the stage logs above.'
        }
    }
}
