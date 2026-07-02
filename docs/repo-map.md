# Carte des repos

Ce workspace est volontairement decoupe en plusieurs repos pour montrer les
frontieres d'une plateforme CI/CD GitOps. Pour apprendre le systeme, lire les
repos dans cet ordre.

| Repo | Role | A retenir |
|---|---|---|
| `control-plane` | Point d'entree operateur | Orchestre les autres repos sans devenir une dependance runtime. |
| `cluster` | Socle Kubernetes local | Cree les VMs, initialise Kubernetes et installe les add-ons reseau bas niveau. |
| `platform-cicd` | Bootstrap technique | Installe ArgoCD, configure le bootstrap initial et expose les commandes operateur. |
| `platform-gitops` | Etat GitOps suivi par ArgoCD | Contient `argocd/managed/`, `argocd/platform/` et l'inventaire applicatif. |
| `toolbox` | Outillage partage | Onboarding d'apps, seed GitLab, credentials ArgoCD, generation ApplicationSet. |
| `ci-templates` | Pipeline applicatif generique | Template GitLab CI versionne, inclus par les apps. |
| `helloworld` | App exemple | Monorepo applicatif multi-services. |
| `helloworld-iac` | Manifests app exemple | Manifests Kubernetes promus par branches d'environnement. |

## Flux principal

1. `cluster` fournit le cluster Kubernetes local.
2. `platform-cicd` installe ArgoCD et applique le root Application.
3. ArgoCD lit `platform-gitops` et synchronise GitLab, les routes plateforme
   et les ApplicationSets applicatifs (les images applicatives sont poussées
   sur GHCR, pas sur un registry interne au cluster).
4. `toolbox` lit l'inventaire de `platform-gitops` pour creer ou mettre a jour
   les projets GitLab et les credentials ArgoCD.
5. `ci-templates` definit la chaine CI/CD consommee par `helloworld`.
6. `helloworld` pousse des images et modifie `helloworld-iac`.
7. ArgoCD deploie `helloworld-iac` dans les namespaces d'environnement.
