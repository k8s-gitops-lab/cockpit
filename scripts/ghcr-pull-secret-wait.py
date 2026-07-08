#!/usr/bin/env python3
"""Attend que Flux dépose le secret source GHCR dans le cluster.

Le secret n'est plus poussé depuis le poste : c'est la Kustomization Flux
flux-secrets qui déchiffre platform-gitops/flux-secrets/ghcr-pull-secret.yaml
(SOPS/age) et l'applique dans le namespace argocd, où External Secrets
Operator le distribue aux namespaces applicatifs.

Ce script vérifie d'abord que le fichier chiffré existe dans le repo gitops
(sinon oriente vers `make ghcr-token-init`), puis attend la convergence.

Usage :
  CONFIG=platform.yml python3 scripts/ghcr-pull-secret-wait.py
  # ou via make :
  make ghcr-pull-secret-wait

Variables optionnelles :
  GHCR_SECRET_TIMEOUT  délai max en secondes (défaut 600)
"""
from __future__ import annotations

import os
import sys
import time

import platform_checks as pc

POLL_INTERVAL = 10  # secondes


def main() -> None:
    values = pc.load_values()
    secret_file = pc.repo_path(values, "GITOPS_REPO_ROOT") / "flux-secrets" / "ghcr-pull-secret.yaml"
    if not secret_file.exists():
        sys.exit(
            f"{secret_file} introuvable.\n"
            "Lancer `make ghcr-token-init` puis committer et pousser platform-gitops "
            "(git push origin main) : Flux lit le repo GitHub."
        )

    timeout = int(os.environ.get("GHCR_SECRET_TIMEOUT", "600"))
    deadline = time.monotonic() + timeout
    while True:
        ok, detail = pc.check_ghcr_secret(values)
        if ok:
            print(f"OK : {detail}")
            return
        if time.monotonic() >= deadline:
            sys.exit(
                f"Timeout ({timeout}s) : {detail}.\n"
                "Vérifier que flux-secrets/ghcr-pull-secret.yaml est committé et poussé "
                "sur origin (GitHub), et l'état Flux :\n"
                "  kubectl -n flux-system get kustomization flux-secrets"
            )
        print(f"En attente ({detail})...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
