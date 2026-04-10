pipeline {
    agent any

    options {
        timeout(time: 10, unit: 'MINUTES')
        timestamps()
    }

    stages {
        stage('Syntax: app.py') {
            steps {
                bat "python -m py_compile app.py"
            }
        }
        stage('Syntax: modules/*.py') {
            steps {
                bat "FOR %%f IN (modules\\*.py) DO python -m py_compile \"%%f\""
            }
        }
        stage('HTTP: / returns 200') {
            steps {
                bat "curl -sf --max-time 10 http://localhost:5000/ > NUL"
            }
        }
        stage('HTTP: /devices returns 200') {
            steps {
                bat "curl -sf --max-time 10 http://localhost:5000/devices > NUL"
            }
        }
        stage('HTTP: /ai/providers returns 200') {
            steps {
                bat "curl -sf --max-time 10 http://localhost:5000/ai/providers > NUL"
            }
        }
    }

    post {
        always {
            echo "Pipeline finished: ${currentBuild.currentResult}"
        }
        success {
            echo 'All CI checks passed.'
        }
        failure {
            echo 'One or more CI checks FAILED - check stage output above.'
        }
    }
}
