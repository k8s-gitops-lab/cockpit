# Fiches de tâches — extensibilité / généricité

> Descriptions auto-portantes des tâches restantes, à réaliser ultérieurement.
> Vue d'ensemble et statut : `backlog-extensibilite.md`. Checklist courte :
> `../TODO.txt`. Chaque tâche s'implémente **dans son repo propriétaire**,
> commit + push sur les deux remotes (`origin` puis `gitlab`). L'état actuel
> décrit ici a été vérifié sur le code le 2026-07-08 ; re-vérifier avant de
> commencer si les repos ont bougé.

Convention de chaque fiche : **Objectif**, **État actuel** (vérifié),
**Fichiers**, **Étapes**, **Critères d'acceptation**, **Vérification**,
**Pièges**.

---

## Axe 2 — Contrat de variables plateforme (dé-hardcoder domaine / registre)

**Objectif** — Un seul point de déclaration par couche pour le domaine
(`192.168.33.100.nip.io`) et le registre (`ghcr.io/k8s-gitops-lab`), propagé
par le canal natif de chaque couche. Instancier le produit ailleurs (autre
domaine/registre) sans grep multi-repo. Le contrat fixe les **noms** de
variables ; chaque repo garde son default local (cf. `AGENTS.md`).

**État actuel (vérifié)** — Le domaine est en dur dans **27 fichiers** de 9
repos. Ils se classent en 3 catégories :

1. **Sources de vérité déjà en place** (à garder, à documenter comme telles) :
   - `infrastructure/ansible/group_vars/all.yml` → `platform.domain` (socle cluster)
   - `platform-gitops/argocd/apps.yaml` → bloc `platform:` (`domain`, `registry.host`, `repoURL`, `targetRevision`) + `gitlab.internalHost`
   - `control-plane/platform.yml` → profil opérateur (surcharge)
2. **Consommateurs à câbler sur une source** (le vrai travail) :
   - `platform-cicd/scripts/platform_inventory.py` **et** `toolbox/scripts/platform_inventory.py` — `_PLATFORM_DEFAULTS` (domaine + registre en dur, **fichier dupliqué à l'identique dans 2 repos** : dette à traiter au passage)
   - `gitlab-projects-iac/terraform/variables.tf` — `gitlab_url` default en dur
   - `ci-templates/gitlab-ci.yml` — `REGISTRY_HOST`, `INTERNAL_GITLAB_HOST` ; `ci-templates/scripts/deploy.py` prend déjà `DOMAIN` **en variable d'env** (bon modèle à généraliser)
   - Variables CI de groupe GitLab : `gitlab_group_variable` dans `gitlab-projects-iac/terraform/main.tf` (vérifier si `DOMAIN`/`REGISTRY_HOST` y sont déjà posées — c'est le canal natif pour la CI)
   - Manifests plateforme (ingress/hostnames) : `platform-gitops/argocd/platform/{argocd-config/argocd-cm.yaml, argocd-ui/route.yaml, argocd-ui/dex-route.yaml, gitlab-routes/routes.yaml, gitlab/values-local.yaml, tf-controller/terraform-gitlab.yaml}`, `platform-cicd/argocd/dex-ca-patch.yaml`, `platform-cicd/ansible/roles/platform_bootstrap/defaults/main.yml`
   - Manifests d'app : `helloworld-iac/k8s/*route.yaml` (réécrits par `deploy.py update_routes` à chaque déploiement — donc pilotés par `DOMAIN`, à confirmer)
   - Scripts GitLab : `platform-cicd/scripts/{gitlab-dex-oauth-app,gitlab-runner-token,gitlab-tf-credentials}.py`, `control-plane/scripts/gitlab-git-creds.py`, `toolbox/scripts/{get-gitlab-token,platform_git}.py`
3. **Hors périmètre** (artefacts de dev local, ne pas toucher) :
   - `*/.gitlab-ci-local.yml`, `*/.claude/settings.local.json`

**Étapes** (par sous-phases, pour limiter le rayon) :
- **2a — Contrat + chemin applicatif** : figer les noms (`PLATFORM_DOMAIN`,
  `PLATFORM_REGISTRY`, `INTERNAL_GITLAB_HOST`). Faire lire `_PLATFORM_DEFAULTS`
  depuis `apps.yaml` sans re-hardcoder (les defaults Python doivent au moins
  correspondre / ou disparaître au profit du bloc `platform:`). Dé-dupliquer
  `platform_inventory.py` (un seul exemplaire partagé, ou vendoring documenté).
  Câbler `gitlab-projects-iac` `gitlab_url` sur une variable, et vérifier les
  `gitlab_group_variable` (DOMAIN/REGISTRY_HOST) qui alimentent la CI.
- **2b — Manifests plateforme** : paramétrer les hostnames d'ingress des
  composants (ArgoCD, GitLab, Dex) — plus lourd car ce sont des manifests
  GitOps statiques. Option : overlay Kustomize avec un `configMapGenerator` /
  variable de substitution, ou values Helm là où c'est un chart. À traiter
  après 2a.

**Critères d'acceptation** — Changer le domaine se fait en éditant les
sources de vérité (`group_vars/all.yml` + `apps.yaml` + `platform.yml`) ; un
`grep -rl 192.168.33.100` hors sources de vérité et hors fichiers `.local`
ne retourne plus de **consommateur** applicatif. `make platform-verify`
(control-plane) passe toujours.

**Vérification** — `grep -rln '192.168.33.100'` avant/après (le compte des
consommateurs baisse) ; rendu inchangé côté ArgoCD (`render-argocd-apps.py
--check` dans `platform-cicd`) ; `terraform validate` dans `gitlab-projects-iac`.

**Pièges** — Ne pas casser les deux sources de vérité légitimes ; les
`_PLATFORM_DEFAULTS` sont un filet de sécurité, pas un doublon à supprimer
aveuglément (garder un default cohérent). Les manifests plateforme (2b) sont
consommés tels quels par ArgoCD : une substitution non résolue casse le
déploiement — tester sur un env jetable.

---

## Axe 4 — `ci-templates` → composants CI versionnés (`spec:inputs`)

**Objectif** — Remplacer le template monolithique étendu par variables libres
par des **CI/CD components** GitLab (`spec:inputs` typés, defaults, validation),
découpés en unités réutilisables. Une nouvelle capacité = un composant
versionné partagé, jamais du YAML local dans l'app.

**État actuel (vérifié)** — `ci-templates/gitlab-ci.yml` est un fichier
unique inclus par `include:` dans le `.gitlab-ci.yml` de chaque app. Stages
`build / deploy / promote`. Jobs : `build-dev` (Kaniko), `build-rec` (crane
retag), `deploy-{dev,rec,preprod,prod}`, `semantic-release`. Étendu par
variables : `SERVICES` (`"<svc>=<image> ..."`), `REGISTRY_HOST`,
`INTERNAL_GITLAB_HOST`, `HAS_PREPROD`, `DOMAIN`, `APP_NAME`, etc. Scripts
associés : `scripts/{deploy.py, rollback.py, gitlab-release-env.js}`.
Ancre partagée `.fetch-scripts` qui clone `ci-templates` si `CI_SCRIPTS_DIR`
absent.

**Étapes** —
- Créer `templates/` avec un composant par capacité : `build-kaniko`,
  `deploy-gitops`, `promote` (chacun `templates/<nom>/template.yml` +
  `spec:inputs`).
- Typer les inputs (ex. `services` en `array`, `has_preprod` en `boolean`,
  `registry_host`/`domain` en `string` avec default). Remplacer les
  variables libres par ces inputs.
- Publier via le catalogue de composants (nécessite un `CI_CATALOG` /
  release de `ci-templates` — vérifier la version GitLab de l'instance).
- Adapter le `.gitlab-ci.yml` de `helloworld` pour consommer les composants
  (`include: component: ...@<version>`).

**Critères d'acceptation** — Le `.gitlab-ci.yml` d'une app standard
n'assemble que des composants + inputs, aucune logique inline. Les inputs
invalides échouent au lint. Pipeline `helloworld` vert de bout en bout.

**Vérification** — `glab ci lint` / lint API sur `helloworld` ; exécuter un
pipeline complet (`gitlab-ci-local` si dispo, cf. `.gitlab-ci-local.yml`) ;
comparer les images/tags produits avant/après.

**Pièges** — Les composants exigent une version GitLab récente + le catalogue
activé ; vérifier avant de s'engager. `.fetch-scripts` (clone du repo pour
les scripts Python) doit continuer à fonctionner ou être remplacé par des
scripts embarqués dans le composant. **Couplé à l'axe 5** : concevoir
`deploy-gitops` pour générer un job par environnement déclaré (voir axe 5),
pas 4 jobs figés.

---

## Axe 5 — Séquence d'environnements déclarée par app

**Objectif** — Déclarer la séquence d'environnements par app (ex.
`environments: [dev, staging, prod]` en noms) et la consommer **des deux
côtés** : rendu ArgoCD ET génération des jobs de déploiement CI. `preprod`
cesse d'être un cas spécial.

**État actuel (vérifié)** —
- Côté rendu : `platform-cicd/scripts/platform_inventory.py:_normalize_app`
  accepte **déjà** un champ `environments:` en surcharge **complète** (chaque
  entrée = `name/branch/namespace/services[{name,url,ingressHost}]`), sinon
  dérive `dev → rec → (preprod si hasPreprod) → prod`. Le JSON Schema
  (`platform-gitops/argocd/apps.schema.json`, axe 1) modélise cette forme
  complète.
- Côté CI : `ci-templates/gitlab-ci.yml` **câble en dur** `deploy-dev/rec/
  preprod/prod` avec une gate `HAS_PREPROD`. La séquence n'est donc PAS
  déclarative côté CI. `deploy.py` mappe `_ENV_BRANCH = {dev, rec, preprod,
  prod→main}` en dur.

**Étapes** —
- Étendre le schéma (axe 1) : autoriser `environments` en **liste de noms**
  (string) OU liste d'objets partiels `{name, branch?, promotion?}`, le reste
  dérivé. Garder la forme complète actuelle valide (rétro-compatible).
- Étendre `_normalize_app` pour dériver depuis une liste de noms (mapper
  `name → branch` : convention `prod→main`, sinon `name→name` ; `namespace`,
  `services.url/ingressHost` comme aujourd'hui).
- Généraliser `deploy.py._ENV_BRANCH` (le déduire de la séquence, pas une
  constante). Idem gates de promotion.
- Côté CI (couplé axe 4) : générer un job de deploy **par env déclaré**
  (composant paramétré par la liste), au lieu de 4 jobs figés + gate
  `HAS_PREPROD`.

**Critères d'acceptation** — Une app peut déclarer `environments: [dev,
prod]` (2 envs) ou `[dev, staging, preprod, prod]` (4 envs custom) et obtenir
le bon rendu ArgoCD **et** les bons jobs CI, sans toucher au template.
`helloworld` (dev/rec/preprod/prod) inchangé.

**Vérification** — `validate-inventory.py` accepte les nouvelles formes ;
`render-argocd-apps.py --check` cohérent ; pipeline d'une app à séquence
custom vert.

**Pièges** — Rétro-compatibilité de `helloworld.yaml` (`hasPreprod: true`
doit continuer à marcher, ou migrer explicitement vers `environments:`).
La branche `prod → main` est une convention à préserver. Le rendu ArgoCD et
la CI doivent lire **la même** définition d'ordre (source unique : l'entrée
d'inventaire).

---

## Axe 3 — Générateur natif ArgoCD (réduire `render-argocd-apps.py`) [spike]

**Objectif** — Consommer `argocd/apps/*.yaml` directement via un
`ApplicationSet` **git files generator** + `goTemplate`, pour supprimer ou
réduire l'étape de rendu (`render-argocd-apps.py`, 280 lignes) et son
répertoire `argocd/generated/`.

**État actuel (vérifié)** — Il existe déjà un `ApplicationSet` (généré, dans
`argocd/managed/apps-appset.yaml`) avec un git **directory** generator sur
`argocd/generated/apps/*`. Le rendu produit par app : `app-project.yaml`
(AppProject), `applicationset.yaml` (Applications par env), `namespaces.yaml`
(namespaces labellisés pour la distribution du secret `ghcr-pull`),
`repo-creds.yaml` (ExternalSecret du repo manifests), `kustomization.yaml`.
Le pipeline `platform-gitops/.gitlab-ci.yml` (`onboard-apps`) régénère et
committe au merge.

**Étapes (spike d'abord)** —
- Prototyper un `ApplicationSet` git **files** generator sur
  `argocd/apps/*.yaml` avec `goTemplate` : générer les Applications par env
  directement depuis les champs de l'entrée d'inventaire.
- Trancher explicitement ce qui **reste scripté** : les `Namespace`
  labellisés, les `ExternalSecret` de repo-creds, et les `AppProject` ne se
  génèrent pas trivialement via un seul ApplicationSet — évaluer un
  ApplicationSet séparé, un générateur de matrices, ou les garder en rendu.
- Documenter le verdict (natif vs scripté) avant d'implémenter.

**Critères d'acceptation** — Décision documentée + prototype fonctionnel sur
`helloworld` (Applications par env synchronisées Healthy) sans régression sur
namespaces/secrets/projet. Réduction nette de code custom si le spike est
concluant.

**Vérification** — Diff des `Application` ArgoCD générées avant/après ;
`argocd app list` Synced/Healthy ; les secrets `ghcr-pull` et repo-creds
toujours distribués.

**Pièges** — La dérivation par convention (`_normalize_app`) est riche
(services→images, hosts, argocdRepoURL in-cluster) : `goTemplate` doit
reproduire cette logique ou l'inventaire doit porter plus de champs. Risque
de déplacer la complexité plutôt que la supprimer — d'où le spike préalable.

---

## Axe 7 — Multi-tenancy GitLab : token de projet par app [sécurité]

**Objectif** — Remplacer le PAT personnel `root` partagé (scope `api`
complet, rayon d'explosion maximal — dette déjà documentée dans le PRD) par
un **project access token** scopé par couple `<app>`/`<app>-iac`.

**État actuel (vérifié)** — Le champ `group` (groupe GitLab dédié par app)
existe déjà dans l'inventaire ET dans `gitlab-projects-iac`
(`terraform/main.tf` : `app_projects`, `app_groups`, un `gitlab_group` par
app). Les pipelines applicatifs référencent `GITLAB_PUSH_TOKEN` (PAT root)
pour cloner `shared-ci/ci-templates` et pousser sur le dépôt manifests +
créer les tags (`semantic-release`). Note dans les commentaires TF : un
**project bot** issu d'un access token ne peut pas être ajouté à un autre
groupe/projet (limitation GitLab), ce qui contraint la conception cross-groupe.

**Étapes** —
- Créer un `gitlab_project_access_token` (ou group access token) par app dans
  `gitlab-projects-iac`, scopé au minimum (`write_repository` sur `<app>-iac`,
  lecture sur `ci-templates`).
- Distribuer le token à la CI de l'app via une `gitlab_project_variable` /
  `gitlab_group_variable` (masquée), en remplacement de `GITLAB_PUSH_TOKEN`
  partagé.
- Gérer l'expiration/rotation (les project access tokens expirent) :
  stratégie de renouvellement (Terraform `rotation` ou job planifié).
- Traiter la contrainte cross-groupe : l'accès en lecture à
  `shared-ci/ci-templates` depuis le token d'une app d'un autre groupe peut
  être refusé — évaluer un déploiement de `ci-templates` en public interne,
  ou un token dédié au clone.

**Critères d'acceptation** — Chaque app pousse ses manifests et crée ses
releases avec **son** token scopé ; le PAT root n'est plus référencé par les
pipelines applicatifs. Fuite d'un token = rayon limité à une app.

**Vérification** — Pipeline `helloworld` vert avec le token scopé ; tentative
d'accès hors périmètre refusée ; `terraform plan` idempotent.

**Pièges** — Sécurité-sensible : ne pas logguer les tokens (masquage CI) ;
l'expiration casse la CI silencieusement si non rotée ; la limitation
project-bot cross-groupe (documentée dans le TF) peut imposer un compromis de
conception. Coordonner avec l'axe 2 (les variables de groupe sont le canal de
distribution).

---

## Dette transverse relevée

- **Deux copies identiques de `platform_inventory.py`**
  (`platform-cicd/scripts/` et `toolbox/scripts/`) : à dé-dupliquer (traiter
  avec l'axe 2). Toute évolution du contrat doit aujourd'hui être faite deux
  fois.
- **`_normalize_app` vs `apps.schema.json`** : deux définitions du contrat
  susceptibles de diverger. Piste : générer/valider l'une depuis l'autre.
- **Commits en attente vers `gitlab`** : remote injoignable le 2026-07-08,
  repousser quand accessible (`git push gitlab main` dans chaque repo touché).
