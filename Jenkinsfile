pipeline {
  agent any
  options {
    timeout(time: 30, unit: 'MINUTES')
    disableConcurrentBuilds(abortPrevious: true)
  }
  stages {
    stage('Install') {
      steps {
        sh 'uv sync --all-groups --frozen'
        sh 'pnpm install --frozen-lockfile'
      }
    }
    stage('Provider-neutral CI') {
      steps {
        sh 'uv run python -m tools.treta ci'
      }
    }
  }
}
