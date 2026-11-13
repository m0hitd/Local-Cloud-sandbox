<#
.SYNOPSIS
    Brings up the full local multi-cloud sandbox.

.DESCRIPTION
    Starts the emulator mesh, waits for LocalStack, installs host Python
    dependencies, creates the SQS queue, applies the Terraform blueprints,
    provisions the BigQuery, GCS, and Pub/Sub emulators, deploys the Lambda
    when requested, starts Minikube, builds the workload images inside
    Minikube's Docker daemon, and applies the Kubernetes manifests.

.PARAMETER DeployLambda
    Also package and deploy the serverless Lambda and its SQS trigger.

.PARAMETER LocalStackTimeoutSeconds
    How long to wait for LocalStack to report SQS as available. Default: 120.
#>
[CmdletBinding()]
param(
    [switch]$DeployLambda,
    [int]$LocalStackTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)][scriptblock]$Command,
        [Parameter(Mandatory)][string]$Description
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

# Dummy credentials for the AWS CLI, Terraform, and boto3 when targeting LocalStack
$env:AWS_ACCESS_KEY_ID     = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION    = "us-east-1"

Write-Step "Checking prerequisites"
foreach ($cmd in @("docker", "minikube", "kubectl", "aws", "terraform", "python")) {
    Assert-Command $cmd
}

Write-Step "Starting the emulator mesh"
Invoke-Native { docker compose up -d } "docker compose up"

Write-Step "Waiting for LocalStack to report SQS as available"
$deadline = (Get-Date).AddSeconds($LocalStackTimeoutSeconds)
$ready = $false
do {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:4566/_localstack/health" -TimeoutSec 5
        $ready = $health.services.sqs -in @("available", "running")
    } catch {
        $ready = $false
    }
    if (-not $ready) { Start-Sleep -Seconds 3 }
} until ($ready -or (Get-Date) -gt $deadline)

if (-not $ready) {
    throw "LocalStack did not report SQS as available within $LocalStackTimeoutSeconds seconds."
}

Write-Step "Installing host-side Python dependencies"
Invoke-Native { python -m pip install -r requirements-dev.txt } "pip install"

Write-Step "Creating the SQS queue used by the Kubernetes consumer"
Invoke-Native {
    aws --endpoint-url=http://localhost:4566 sqs create-queue --queue-name order-queue | Out-Null
} "SQS queue creation"

Write-Step "Applying Terraform blueprints (EC2, S3, GCS, DynamoDB, Secrets Manager)"
Invoke-Native { terraform -chdir=terraform init -input=false } "terraform init"
Invoke-Native { terraform -chdir=terraform apply -auto-approve -input=false } "terraform apply"

Write-Step "Provisioning BigQuery, GCS, and Pub/Sub emulator resources"
Invoke-Native { python scripts/init_gcp_emulators.py } "GCP emulator provisioning"

if ($DeployLambda) {
    Write-Step "Deploying the serverless Lambda and its SQS trigger"
    Invoke-Native { python services/serverless-lambda/deploy_lambda.py } "Lambda deployment"
}

Write-Step "Starting Minikube"
Invoke-Native { minikube start --driver=docker } "minikube start"

Write-Step "Pointing Docker at Minikube's daemon"
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

Write-Step "Building producer and consumer images inside Minikube"
Invoke-Native { docker build -t order-producer:v2 ./workloads/producer } "producer image build"
Invoke-Native { docker build -t order-consumer:v1 ./workloads/consumer } "consumer image build"

Write-Step "Deploying workloads to Kubernetes"
Invoke-Native { kubectl apply -f workloads/k8s/ } "kubectl apply"
Invoke-Native {
    kubectl rollout status deployment/order-producer-deployment --timeout=120s
} "producer rollout"
Invoke-Native {
    kubectl rollout status deployment/order-consumer-deployment --timeout=120s
} "consumer rollout"

Write-Host ""
Write-Host "Sandbox is running. Tail the consumer with:" -ForegroundColor Green
Write-Host "  kubectl logs -f deployment/order-consumer-deployment"
