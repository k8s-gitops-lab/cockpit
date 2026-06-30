#!/usr/bin/env bash
set -euo pipefail

SECRET_NAME="github-credentials"
NAMESPACE="flux-system"

echo "Création du secret Kubernetes '$SECRET_NAME' dans le namespace '$NAMESPACE'."
echo "Le PAT GitHub doit avoir le scope 'repo'."
echo ""

read -rsp "GitHub Personal Access Token : " GITHUB_PAT
echo ""

if [[ -z "$GITHUB_PAT" ]]; then
  echo "Erreur : token vide." >&2
  exit 1
fi

kubectl create secret generic "$SECRET_NAME" \
  --namespace "$NAMESPACE" \
  --from-literal=username=x-token \
  --from-literal=password="$GITHUB_PAT" \
  --from-literal=token="$GITHUB_PAT" \
  --dry-run=client -o yaml \
  | kubectl apply -f -

echo "Secret '$SECRET_NAME' créé/mis à jour dans '$NAMESPACE'."
