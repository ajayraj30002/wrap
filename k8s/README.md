# WRAP Kubernetes Deployment Guide

This directory contains production-ready Kubernetes manifests for deploying the WRAP AI Gateway, its React Mission Control Console, and PostgreSQL persistence with high availability, liveness/readiness probes, and Prometheus metrics scraping.

---

## Architecture in Kubernetes

- **Namespace**: `wrap`
- **StatefulSet**: `wrap-postgres` (PostgreSQL 16 with PersistentVolumeClaim)
- **Deployments**:
  - `wrap-backend` (2 replicas with rolling updates, `/healthz` liveness, `/ready` readiness)
  - `wrap-frontend` (2 replicas with Nginx reverse proxy)
- **Observability**:
  - `wrap-backend-monitor` (Prometheus Operator ServiceMonitor scraping `/metrics` every 15s)
- **Ingress**: `wrap-ingress` (Nginx Ingress controller routing `/v1`, `/api`, and console UI)

---

## Deployment Steps

### 1. Build and Tag Container Images

```bash
# Build backend
docker build -t wrap-backend:latest ./backend

# Build frontend
docker build -t wrap-frontend:latest ./frontend
```

*(If using a remote registry like ECR/GCR/DockerHub, tag with your registry prefix and push)*

---

### 2. Apply Manifests with Kustomize

```bash
kubectl apply -k k8s/
```

Verify that all workloads are running:

```bash
kubectl get pods -n wrap
kubectl get svc -n wrap
kubectl get ingress -n wrap
```

---

### 3. Verification Probes

Test the Kubernetes probes:

```bash
# Liveness Probe
kubectl exec -it deploy/wrap-backend -n wrap -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read().decode())"

# Readiness Probe
kubectl exec -it deploy/wrap-backend -n wrap -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"

# Prometheus Metrics Scraping
kubectl exec -it deploy/wrap-backend -n wrap -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode()[:300])"
```
