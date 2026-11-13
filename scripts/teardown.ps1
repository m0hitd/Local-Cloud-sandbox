<#
.SYNOPSIS
    Shuts down the local multi-cloud sandbox.

.DESCRIPTION
    Removes the Kubernetes workloads, destroys Terraform-managed resources while
    the emulators are still running, stops the emulator containers, and stops
    Minikube. Use -Purge to also delete the Minikube cluster, emulator volumes,
    and local Terraform state for a clean slate.

.PARAMETER Purge
    Delete the Minikube cluster, remove emulator volumes, and clear local Terraform state.
#>
[CmdletBinding()]
param(
    [switch]$Purge
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

# Teardown keeps going when a step fails, for example if Minikube is already stopped
function Invoke-Optional {
    param(
        [Parameter(Mandatory)][scriptblock]$Command,
        [Parameter(Mandatory)][string]$Description
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "$Description exited with code $LASTEXITCODE. Continuing."
    }
}

Write-Step "Removing Kubernetes workloads"
Invoke-Optional { kubectl delete -f workloads/k8s/ --ignore-not-found } "kubectl delete"

# Destroy while the emulators are still up so the providers can reach them
Write-Step "Destroying Terraform-managed resources"
Invoke-Optional { terraform -chdir=terraform destroy -auto-approve -input=false } "terraform destroy"

Write-Step "Stopping the emulator mesh"
if ($Purge) {
    Invoke-Optional { docker compose down -v } "docker compose down -v"
} else {
    Invoke-Optional { docker compose down } "docker compose down"
}

if ($Purge) {
    Write-Step "Deleting Minikube cluster and local Terraform state"
    Invoke-Optional { minikube delete } "minikube delete"
    Remove-Item -Recurse -Force "terraform/.terraform" -ErrorAction SilentlyContinue
    Remove-Item -Force "terraform/terraform.tfstate", "terraform/terraform.tfstate.backup" -ErrorAction SilentlyContinue
} else {
    Write-Step "Stopping Minikube"
    Invoke-Optional { minikube stop } "minikube stop"
}

Write-Host ""
Write-Host "Sandbox is down." -ForegroundColor Green
