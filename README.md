# Local Multi-Cloud Cloud-Native Sandbox

## Overview

The **Local Multi-Cloud Cloud-Native Sandbox** is a comprehensive, zero-cost cloud engineering environment designed to replicate an entire enterprise multi-cloud ecosystem locally. Rather than serving as a single application pipeline, this platform provides a modular foundation that locally emulates core **Amazon Web Services (AWS)**, **Google Cloud Platform (GCP)**, and **Cloud-Native** primitives—allowing engineers to provision virtual machines, object storage, serverless functions, NoSQL/SQL databases, secret managers, and Kubernetes clusters entirely offline.

Under the hood, the sandbox orchestrates a multi-service Docker Compose backend alongside a local **Minikube Kubernetes** cluster and **Terraform** Infrastructure-as-Code (IaC) blueprints. Cross-boundary networking (`host.minikube.internal`) seamlessly bridges isolated Kubernetes workloads with host-level cloud emulators (LocalStack, GCP BigQuery/GCS/PubSub Emulators, MinIO, and PostgreSQL). To demonstrate the sandbox in action, it includes a reference **Event-Driven ETL Microservice Pipeline** alongside standalone modules for testing compute, storage, and database integrations.

Created and architected by **Mohit Debnath** (Google Cloud Certified Associate Cloud Engineer), this project showcases end-to-end proficiency in multi-cloud architecture, container orchestration, Infrastructure-as-Code, and local-first environment engineering.

---

## Emulated Multi-Cloud Service Matrix

This sandbox locally imitates the following production cloud services across AWS, GCP, and Open-Source Cloud-Native stacks:

| Cloud Domain | Production Cloud Equivalent | Local Sandbox Emulator | Port / Endpoint |
| :--- | :--- | :--- | :--- |
| **Container Orchestration** | AWS EKS / Google GKE | **Minikube (Kubernetes v1.35+)** | K8s API (`6443`) |
| **Compute (VMs / Instances)** | AWS EC2 / Google Compute Engine | **LocalStack EC2 & QEMU/Docker VMs** | `localhost:4566` |
| **Serverless Compute** | AWS Lambda / Google Cloud Functions | **LocalStack Lambda** | `localhost:4566` |
| **Object Storage** | AWS S3 / Google Cloud Storage (GCS) | **LocalStack S3 & Fake-GCS-Server** | `4566` / `4443` |
| **Message Queues & Pub/Sub** | AWS SQS & SNS / Google Pub/Sub | **LocalStack SQS/SNS & GCP Pub/Sub** | `4566` / `8085` |
| **Data Warehousing** | Google BigQuery | **goccy/bigquery-emulator** | `localhost:9050` |
| **NoSQL & Key-Value DB** | AWS DynamoDB / Google Firestore | **LocalStack DynamoDB & Firestore Emulator** | `4566` / `8080` |
| **Relational DB (RDS)** | AWS RDS / Google Cloud SQL | **PostgreSQL 16 Container** | `localhost:5432` |
| **Secrets & IAM** | AWS Secrets Manager & IAM | **LocalStack SecretsManager & IAM** | `localhost:4566` |
| **Infrastructure as Code** | AWS CloudFormation / GCP Deployment Mgr | **Terraform (with Local Provider Endpoints)** | CLI / HCL |

---

## System Architecture

```
+---------------------------------------------------------------------------------+
|                           LOCAL WORKSTATION (HOST)                              |
|                                                                                 |
|  +---------------------------+           +-----------------------------------+  |
|  |   TERRAFORM & CLI LAYER   |           |    MINIKUBE KUBERNETES CLUSTER    |  |
|  | - Terraform (tflocal)     |           |                                   |  |
|  | - AWS CLI / gcloud CLI    |           |  +-----------------------------+  |  |
|  | - kubectl / Helm          |           |  | Reference Microservices:    |  |  |
|  +-------------+-------------+           |  | - Order Producer (v2)       |  |  |
|                |                         |  | - Order Consumer (v1)       |  |  |
|                | Provision & Configure   |  | - Serverless Event Workers  |  |  |
|                v                         |  +--------------+--------------+  |  |
|  +---------------------------------------+-----------------|-----------------+  |
|  |                 DOCKER COMPOSE MULTI-CLOUD EMULATOR MESH                     |
|  |                                                         |                    |
|  |  +--------------------------+  +------------------------v-----------------+  |
|  |  |   LOCALSTACK (AWS MOCK)  |  |           GCP & DATA EMULATORS           |  |
|  |  | - EC2 (Mock VMs)         |  | - BigQuery Emulator (:9050)              |  |
|  |  | - S3 (Object Buckets)    |  | - Fake GCS Server (:4443)                |  |
|  |  | - SQS / SNS (Messaging)  |  | - GCP Pub/Sub & Firestore (:8085/:8080)  |  |
|  |  | - Lambda & DynamoDB      |  | - PostgreSQL / Cloud SQL (:5432)         |  |
|  |  | - IAM & Secrets Manager  |  |                                          |  |
|  |  +--------------------------+  +------------------------------------------+  |
|  +------------------------------------------------------------------------------+
+---------------------------------------------------------------------------------+
```

---

## Repository Structure

```text
local-multicloud-sandbox/
├── docker-compose.yml                  # Core multi-cloud emulator stack (AWS, GCP, SQL)
├── requirements-dev.txt                # Host-side Python dependencies
├── terraform/                          # IaC blueprints configured for local endpoints
│   ├── main.tf                         # LocalStack & GCP provider overrides
│   ├── compute_ec2.tf                  # Provisions mock EC2 instances & security groups
│   ├── storage_s3_gcs.tf               # Provisions S3 buckets & GCS storage buckets
│   └── database_dynamodb.tf            # Provisions NoSQL tables & Secrets Manager entries
├── services/                           # Standalone service sandbox modules & demos
│   ├── vm-compute/                     # Scripts to launch, SSH-mock, and inspect EC2/VMs
│   ├── object-storage/                 # Multi-cloud S3 & GCS upload/lifecycle test scripts
│   ├── serverless-lambda/              # Local AWS Lambda function + SQS event trigger
│   └── databases/                      # DynamoDB & PostgreSQL schema/query sandboxes
├── workloads/                          # Kubernetes microservice workloads (Reference ETL)
│   ├── producer/                       # Containerized Python Producer (SQS publisher)
│   ├── consumer/                       # Containerized Python Consumer (SQS -> BigQuery)
│   └── k8s/                            # Kubernetes Deployments, ConfigMaps, & Services
├── scripts/
│   ├── bootstrap.ps1                   # One-click startup for emulators, K8s, & Terraform
│   ├── init_gcp_emulators.py           # Provisions BigQuery datasets, GCS buckets, & PubSub
│   └── teardown.ps1                    # Clean shutdown and volume cleanup
└── README.md
```

---

## Quickstart & Deployment Guide

### 1. Prerequisites
Ensure the following tools are installed and available in your system `PATH`:
* **Docker Desktop** (allocated at least 6GB RAM for multi-service emulation)
* **Minikube** & **`kubectl`**
* **Terraform** (`v1.6+`)
* **AWS CLI (`v2`)** & **Python `3.11+`**

### 2. Boot the Multi-Cloud Emulator Mesh
Start LocalStack (EC2, S3, SQS, Lambda, DynamoDB, IAM), BigQuery, Fake-GCS, Pub/Sub, and PostgreSQL:
```powershell
docker compose up -d
```

### 3. Provision Cloud Infrastructure via Terraform
Use Terraform to declaratively spin up virtual machines (EC2), storage buckets (S3), and NoSQL tables against your local endpoints:
```powershell
cd terraform
terraform init
terraform apply -auto-approve
cd ..
```

### 4. Initialize GCP Emulators (BigQuery & GCS)
Run the Python bootstrap script to configure local GCP datasets, tables, and storage buckets:
```powershell
python -m pip install -r requirements-dev.txt
python scripts/init_gcp_emulators.py
```

### 5. Start Kubernetes & Deploy Reference Workloads
Boot Minikube, build the microservice images inside Minikube's Docker daemon, and deploy the event-driven ETL pipeline:
```powershell
minikube start --driver=docker
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

docker build -t order-producer:v2 ./workloads/producer
docker build -t order-consumer:v1 ./workloads/consumer

kubectl apply -f workloads/k8s/
```

### 6. Explore & Verify Emulated Services
* **Verify Mock EC2 Instances:** `aws --endpoint-url=http://localhost:4566 ec2 describe-instances`
* **Verify S3 Buckets:** `aws --endpoint-url=http://localhost:4566 s3 ls`
* **Verify Kubernetes Pods & ETL Pipeline:**
  ```powershell
  kubectl get pods
  kubectl logs -f deployment/order-consumer-deployment
  ```

---

## Core Configuration Reference

### `docker-compose.yml` (Multi-Service Emulator Stack)
```yaml
services:
  localstack:
    image: localstack/localstack:latest
    ports:
      - "4566:4566"
    environment:
      - SERVICES=ec2,s3,sqs,sns,lambda,dynamodb,iam,secretsmanager
      - DEFAULT_REGION=us-east-1
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"

  bigquery:
    image: ghcr.io/goccy/bigquery-emulator:latest
    command: ["--project=local-analytics-project", "--port=9050"]
    ports:
      - "9050:9050"

  fake-gcs:
    image: fsouza/fake-gcs-server:latest
    command: ["-scheme", "http", "-port", "4443"]
    ports:
      - "4443:4443"

  gcp-pubsub:
    image: gcr.io/google.com/cloudsdktool/cloud-sdk:emulators
    command: ["gcloud", "beta", "emulators", "pubsub", "start", "--host-port=0.0.0.0:8085"]
    ports:
      - "8085:8085"

  postgres-rds:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: sandbox_admin
      POSTGRES_PASSWORD: localdevpassword
      POSTGRES_DB: cloud_sandbox_db
    ports:
      - "5432:5432"
```
