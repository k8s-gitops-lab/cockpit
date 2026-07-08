# Backlog — extensibilité / généricité du produit

> Initiative transverse décidée le 2026-07-08 : rendre le produit plus
> extensible et instanciable ailleurs (autre domaine, autre registre,
> plusieurs équipes). Ce fichier suit l'avancement ; chaque axe est
> implémenté **dans son repo propriétaire**, jamais depuis `control-plane`
> (cf. `AGENTS.md`). L'état actuel ci-dessous a été vérifié sur le code —
> plusieurs axes sont déjà partiellement en place.

## Tableau de suivi

| # | Axe | Statut | Repo(s) propriétaire(s) | Risque |
|---|---|---|---|---|
| 1 | Schéma d'inventaire versionné + validation CI | À faire | `platform-gitops` (+ `platform-cicd`) | Faible |
| 2 | Contrat de variables plateforme (dé-duplication domaine/registre) | Partiel | `platform-gitops`, `gitlab-projects-iac`, `ci-templates`, `infrastructure` | Faible |
| 3 | Générateur natif ArgoCD (réduire `render-argocd-apps.py`) | Partiel | `platform-cicd`, `platform-gitops` | Élevé (spike) |
| 4 | `ci-templates` → composants CI versionnés (`spec:inputs`) | À faire | `ci-templates` | Moyen |
| 5 | Séquence d'environnements déclarée par app | Partiel | `platform-gitops` + `ci-templates` | Moyen-élevé |
| 7 | Multi-tenancy GitLab (token de projet par app) | Partiel | `gitlab-projects-iac`, `platform-cicd` | Élevé (sécurité) |
| 6 | Scaffolding d'app (`app-template` + `toolbox`) | **Différé** | `toolbox` (+ nouveau repo) | — |

## Séquencement recommandé

1. **Phase 1 — fondations (faible risque)** : axe 1 puis axe 2. Contrat
   d'entrée (schéma) + contrat de sortie (variables) ; ils dé-risquent tout
   le reste.
2. **Phase 2 — refactor CI (couplé)** : axe 4 (composants) puis axe 5
   (séquence déclarative consommée par les composants). À faire ensemble.
3. **Phase 3 — spikes** : axe 3 (générateur natif) et axe 7 (tokens de
   projet), chacun précédé d'une spike de validation.
4. **Différé** : axe 6.

---

## Axe 1 — Schéma d'inventaire versionné

**État actuel** : aucun schéma formel. Le contrat vit implicitement dans
`platform-cicd/scripts/platform_inventory.py` (`_normalize_app`). Champs
requis : `name`, `group`. Tout le reste est dérivé par convention :
`description`, `services` (liste de strings ou `{name,image}`), `hasPreprod`,
`environments`, `manifests`, `code`, `showcaseService`, `argocd`,
`importFromGithub`.

**Reste à faire** : JSON Schema versionné (`apiVersion: platform/v1`) +
job de validation dans la CI de `platform-gitops` déclenché sur la MR
d'inventaire (feedback avant merge, pas après échec de rendu). Le schéma
documente aussi le contrat, aujourd'hui éparpillé entre spec et code Python.

## Axe 2 — Contrat de variables plateforme

**État actuel (partiel)** : `platform-gitops/argocd/apps.yaml` porte déjà un
bloc `platform:` (`domain`, `repoURL`, `targetRevision`, `registry.host`) +
`gitlab.internalHost`. MAIS ces valeurs sont dupliquées ailleurs :
`_PLATFORM_DEFAULTS` en Python, `gitlab_url` en dur dans
`gitlab-projects-iac/terraform/variables.tf`, `REGISTRY_HOST` /
`INTERNAL_GITLAB_HOST` en dur dans `ci-templates/gitlab-ci.yml`, et le
domaine `192.168.33.100.nip.io` en dur dans ~20 fichiers de 9 repos.

**Reste à faire** : un contrat de noms bien connus (`PLATFORM_DOMAIN`,
`PLATFORM_REGISTRY`, `INTERNAL_GITLAB_HOST`…) injectés par le canal natif de
chaque couche (variable TF, variable CI de groupe GitLab, values Helm, patch
Kustomize). Chaque repo garde son default local (cf. `AGENTS.md`) ; le
contrat ne fixe que les noms. Objectif : instancier le produit ailleurs sans
grep multi-repo.

## Axe 3 — Générateur natif ArgoCD

**État actuel (partiel)** : il existe déjà un `ApplicationSet` avec un git
*directory* generator sur `argocd/generated/apps/*`, mais ces répertoires
sont produits par une étape de rendu (`render-argocd-apps.py`, 280 lignes,
génère aussi namespaces, ExternalSecrets, AppProjects).

**Reste à faire (spike)** : évaluer un git *files* generator consommant
directement `argocd/apps/*.yaml` + `goTemplate`, pour supprimer/réduire le
rendu. Point dur : ExternalSecrets, namespaces et projets sont aussi générés
— la spike doit trancher ce qui devient natif vs ce qui reste scripté.

## Axe 4 — Composants CI versionnés

**État actuel** : `ci-templates/gitlab-ci.yml` est un template monolithique
étendu par variables libres (`SERVICES`, `REGISTRY_HOST`, `HAS_PREPROD`…).

**Reste à faire** : convertir en **CI/CD components** GitLab
(`include:component` + `spec:inputs` typés, defaults, validation). Découper
en composants réutilisables (`build-kaniko`, `deploy-gitops`, `promote`).
Une nouvelle capacité devient un composant versionné partagé, jamais du
YAML local dans l'app (préserve le périmètre « app standard », cf.
`CONTEXT.md`).

## Axe 5 — Séquence d'environnements déclarée par app

**État actuel (partiel)** : `_normalize_app` accepte déjà un champ
`environments:` qui surcharge intégralement la séquence dérivée
(`dev/rec/preprod?/prod`), et `hasPreprod` bascule preprod. MAIS le template
CI `ci-templates/gitlab-ci.yml` câble en dur les jobs `deploy-dev/rec/
preprod/prod` avec une gate `HAS_PREPROD` — la séquence n'est donc PAS
réellement déclarative côté CI.

**Reste à faire** : permettre de déclarer la séquence par app (ex.
`environments: [dev, staging, prod]` en noms, le reste dérivé) et la
consommer **des deux côtés** : rendu ArgoCD ET génération des jobs de
déploiement (couplé à l'axe 4, via un composant qui génère un job par env
déclaré). `preprod` cesse d'être un cas spécial → juste un env de la liste.

## Axe 7 — Multi-tenancy GitLab

**État actuel (partiel)** : le champ `group` existe déjà par app dans
l'inventaire ET dans `gitlab-projects-iac/terraform/variables.tf` ; les
projets sont créés sous ce groupe.

**Reste à faire** : remplacer le token personnel `root` partagé (scope `api`
complet, rayon d'explosion maximal — déjà signalé comme dette dans le PRD)
par un **token de projet** (`project access token`) par couple
`<app>`/`<app>-iac`, scopé au strict nécessaire. Touche `gitlab-projects-iac`
(création des tokens) et le plumbing de secrets CI.

---

## Différé

### Axe 6 — Scaffolding d'app (`app-template`)

Repo `app-template` (cookiecutter via `toolbox`) générant `<app>` +
`<app>-iac` + `.gitlab-ci.yml` + l'entrée d'inventaire, pour réduire
l'onboarding à une commande + une MR et garantir que les nouvelles apps
naissent conformes au pattern. **À traiter un autre jour** (décision
2026-07-08).
