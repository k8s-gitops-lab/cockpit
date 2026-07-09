#!/usr/bin/env python3
"""Attend que toutes les Applications ArgoCD soient Synced/Healthy.

Après la création des projets GitLab (gitlab-projects-wait), ArgoCD doit
encore rafraîchir les repos, comparer et déployer : les Applications passent
par des états transitoires (Unknown/Progressing/Degraded) pendant plusieurs
minutes. platform-verify fait un check one-shot : sans cette attente, il
s'exécute pendant la convergence et échoue sur argocd-apps.

Usage :
  CONFIG=platform.yml python3 scripts/argocd-apps-wait.py
  # ou via make :
  make argocd-apps-wait

Variables optionnelles :
  ARGOCD_APPS_TIMEOUT  délai max en secondes (défaut 900)
"""
from __future__ import annotations

import os
import sys
import time

import platform_checks as pc

POLL_INTERVAL = 10  # secondes


def main() -> None:
    values = pc.load_values()

    timeout = int(os.environ.get("ARGOCD_APPS_TIMEOUT", "900"))
    deadline = time.monotonic() + timeout
    while True:
        ok, detail = pc.check_apps_synced(values)
        if ok:
            print(f"OK : {detail}")
            return
        if time.monotonic() >= deadline:
            sys.exit(
                f"Timeout ({timeout}s) : {detail}.\n"
                "Vérifier l'état des Applications ArgoCD :\n"
                f"  kubectl -n {values['ARGOCD_NAMESPACE']} get applications.argoproj.io\n"
                "  make argocd-status"
            )
        print(f"En attente ({detail})...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
