# Spec technique

> Le "comment" du projet : jobs CI/CD détaillés, scripts, schémas
> d'inventaire, dette IaC connue, contraintes d'infra. Pour la vision/le
> périmètre produit, voir [`prd.md`](./prd.md). Pour les règles de
> fonctionnement, voir [`spec-fonctionnelle.md`](./spec-fonctionnelle.md).

## CI/CD : chaîne d'environnements (résumé)

La chaîne "build once, promote everywhere" (tag `vX.Y.Z`, build kaniko au
merge sur `main` puis retag `crane` à la release, promotion dev → rec →
preprod → prod par mise à jour du `kustomization.yaml` du dépôt manifests,
gates manuels + protected environment sur `deploy-prod`, self-heal ArgoCD,
rollback par `git revert` sur le dépôt manifests) est implémentée et
documentée en détail dans `ci-templates` (jobs, table d'activation par
environnement) et `gitlab-projects-iac` (protections de branche, gates
Terraform). Ce document ne garde que ce qui concerne l'orchestration
`control-plane` elle-même ; voir :

- `ci-templates/docs/spec-technique.md` : détail des jobs, `resource_group`,
  gates manuels/protected environment, format des commits GitOps.
- `gitlab-projects-iac/docs/spec-technique.md` : protections de branche,
  gates Terraform sur `main`.
- `platform-gitops/docs/spec-technique.md` : mécanique ArgoCD
  (`Application`, `automated.selfHeal`, structure des manifests).

## Monorepo multi-services : implémentation

**Statut : implémenté**, illustré par `helloworld` (deux sous-dossiers
`helloworld-svc`/`helloworld-gui`, un `Dockerfile` par service, `services:`
listé dans `platform-gitops/argocd/apps/helloworld.yaml`). Détail du
mécanisme (boucle CI sur `${SERVICES}`, plusieurs `kustomize edit set
image`) : `ci-templates/docs/spec-technique.md` et
`helloworld/docs/spec-technique.md`.

## Industrialisation : implémentation

- **Repo `ci-templates`** (GitLab) : héberge le pipeline générique décrit
  ci-dessus. Source locale : `ci-templates/`, projet créé par Terraform
  `gitlab-projects-iac` dans le groupe GitLab `shared-ci` (indépendant du
  groupe `infra` des projets applicatifs), avec une ref versionnée déclarée
  par application.
  Le `.gitlab-ci.yml` de chaque app se réduit à un `include` de
  ce template, **`ref` épinglée à une version** (ex. `v1.3.0`, pas `main`)
  + ses variables propres (`IMAGE`, `MANIFESTS_PROJECT_PATH`, `SERVICES`,
  `HAS_PREPROD`). Corriger le pipeline = un commit dans `ci-templates` + un
  bump délibéré de la `ref` dans le `.gitlab-ci.yml` de chaque app qui veut
  l'adopter — **pas de propagation automatique** : un commit cassé dans
  `ci-templates` n'affecte aucune app tant qu'elle n'a pas explicitement
  bumpé sa `ref`. Choix délibéré au prix d'un bump manuel par app : isole le
  rayon d'impact d'une régression du template, plutôt que de la propager
  instantanément à toutes les apps.
- **Descriptors explicites `platform-gitops/argocd/apps/<app>.yaml`** :
  chaque application a son propre fichier plat dans
  `platform-gitops/argocd/apps/`. L'ensemble reste
  la source de vérité des
  projets GitLab (`code.projectPath`, `manifests.projectPath`,
  `ciTemplate.projectPath`), du repo GitOps autorisé (`manifests.repoURL`),
  des environnements (`environments[].branch`, `namespace`, `url`,
  `ingressHost`) et des restrictions ArgoCD (`argocd.sourceRepos`,
  `argocd.destinations`). Le choix est volontairement plus verbeux qu'un
  schéma "tout par convention" : la sécurité attendue est lisible directement
  dans l'inventaire, sans avoir à connaître le renderer. Consommé par deux
  mécanismes :
  - le **rendu ArgoCD** : `platform-cicd/scripts/render-argocd-apps.py`
    (cible `make argocd-apps-render`), déclenché automatiquement par un job
    CI au merge d'une PR sur `platform-gitops`, génère par app un dossier
    `argocd/generated/apps/<app>/` (un `AppProject` dédié, un
    `ApplicationSet` qui produit les `Application` par environnement, les
    credentials repo et les Jobs de copie de secrets) — les `sourceRepos` et
    `destinations` sont recopiés depuis le fichier d'app, pas reconstruits
    implicitement. Cloisonnement explicite : une app ne peut pas, même par
    erreur de génération ou compromission, affecter les ressources d'une
    autre app. Plus de fichier YAML à créer à la main par app. Un
    `ApplicationSet` générique committé dans `argocd/managed/apps-appset.yaml`
    (generator git par répertoire) découvre ces dossiers générés ; le tout
    est synchronisé en continu par le root Application "app of apps"
    (`argocd/root-app.yaml`).
  - **Terraform `gitlab-projects-iac`** : crée le groupe GitLab dédié de
    l'app (`group`) et les dépôts `<app>`/`<app>-iac` dedans, configure les
    gates, les variables et les protections GitLab.
- **Add-ons plateforme sous ArgoCD** : le root Application synchronise aussi
  les `Application` déclarées dans `argocd/managed/` pour les composants de
  plateforme applicative : GitLab, exposition HTTP d'ArgoCD, Flux
  (déchiffrement SOPS et Terraform) et External Secrets Operator
  (distribution des secrets GHCR et repository ArgoCD). Les images
  applicatives sont poussées sur GHCR (`ghcr.io/k8s-gitops-lab`), pas
  sur un registry interne au cluster. Les add-ons cluster bas niveau
  (Gateway API, MetalLB, Traefik et Gateway partagée) sont provisionnés par
  Ansible.

Modifier un fichier `platform-gitops/argocd/apps/<app>.yaml` se fait via une pull request sur le dépôt
`platform-gitops`. Au merge, le pipeline CI de `platform-gitops` régénère
automatiquement `argocd/generated/apps/<app>/` et `argocd/managed/apps-appset.yaml`
et commite le résultat sur `main` : ArgoCD lit Git, pas le disque local. Pendant l'amorçage, certaines
références ArgoCD peuvent pointer vers GitHub pour éviter une dépendance
circulaire avec GitLab.

Voir aussi [`source-control.md`](./source-control.md) : GitHub est l'amont du
code source et la cible de `PLATFORM_REPO_URL`, tandis que GitLab porte les
depots runtime importes/seedes.

## Routage HTTP : Gateway API, Traefik et MetalLB

La cible de routage applicatif est de migrer les expositions HTTP applicatives
du modèle `Ingress` vers **Gateway API**. Cette couche cluster est déclarée
dans Ansible, pas dans ArgoCD :

- **Gateway API CRDs** : le rôle Ansible `kubernetes-platform` applique les CRD
  standard Gateway API, versionnées par `gateway_api_version`.
- **Traefik** : le rôle Ansible `kubernetes-platform` installe le chart Helm
  Traefik avec les values rendues depuis
  `ansible/roles/kubernetes-platform/templates/traefik-values.yaml.j2`
  (`providers.kubernetesGateway.enabled=true`, `gateway.enabled=true`).
- **MetalLB** : le rôle Ansible `kubernetes-platform` installe MetalLB, puis
  applique l'`IPAddressPool` et la `L2Advertisement` rendus depuis
  `ansible/roles/kubernetes-platform/templates/metallb-config.yaml.j2`.
- **Gateway partagée** : le rôle Ansible `kubernetes-platform` applique la
  `Gateway` HTTP rendue depuis
  `ansible/roles/kubernetes-platform/templates/gateway.yaml.j2`, acceptant les
  `HTTPRoute` des namespaces applicatifs nécessaires.
- **HTTPRoute par service exposé** : les anciens `Ingress` applicatifs doivent
  être remplacés par des `HTTPRoute` qui pointent vers les `Service`
  Kubernetes de l'app.
- **UI ArgoCD** : `argocd/managed/argocd-ui.yaml` déploie l'exposition HTTP
  ArgoCD depuis `argocd/platform/argocd-ui/`. La cible `make argocd-ingress`
  ne fait plus qu'activer le mode HTTP côté serveur ArgoCD.

Les applications doivent converger vers des `HTTPRoute` au lieu d'`Ingress`.
Une phase transitoire est acceptable, mais une app ne doit pas rester durablement
mixte sans décision explicite.

### Ajouter une application : séquence technique

Le parcours complet (côté équipe applicative) est décrit dans
[`../README.md`](../README.md#parcours-2--une-équipe-applicative-crée-un-projet).
Résumé technique : sources locales (`<app>/`, `<app>-iac/`) → entrée dans
`platform-gitops/argocd/apps/<app>.yaml` via PR → au merge, régénération
`argocd/managed/apps-appset.yaml` (job CI `platform-cicd`) et de
`gitlab-projects-iac/terraform/apps.auto.tfvars.json` (job CI
`platform-gitops`, script `toolbox/scripts/render-gitlab-projects.py`) →
Terraform crée/actualise les projets GitLab.

## Outillage partagé

`control-plane/scripts/` ne contient que les scripts propres à
l'orchestration locale (`bootstrap.py`, `export-env.py`,
`gitlab-git-creds.py`, `ghcr-token-init.py`, scripts workspace
`clone-github-org.sh` et `commit-*.sh` — les deux scripts `commit-*`
encodent des directions de vérité opposées, voir
[`source-control.md`](source-control.md)). Les scripts de bootstrap plateforme
(`gitlab-tf-credentials.py`, `render-argocd-apps.py`, `gitlab-runner-token.py`,
`gitlab-dex-oauth-app.py`) vivent dans `platform-cicd/scripts/` et sont
appelés par `control-plane` via `make -C ../platform-cicd <cible>` (voir
`Makefile`). Les utilitaires d'administration applicative
(`render-gitlab-projects.py`) vivent dans `toolbox/scripts/` et s'appellent
avec `PLATFORM_REPO_ROOT` pointant vers `platform-gitops`. L'ajout d'une app ne passe pas par un script : c'est une
pull/merge request directe sur `platform-gitops`.

## Dette IaC connue

La chaîne CI/CD principale (bootstrap ArgoCD/GitLab, `helloworld`,
inventaire multi-apps) est automatisée. Le détail des scripts de bootstrap
plateforme est documenté dans `platform-cicd/docs/spec-technique.md`.

- `argocd/managed/` (dans `platform-gitops`) déclare les add-ons plateforme
  applicative synchronisés par ArgoCD ; les add-ons cluster bas niveau
  vivent dans `infrastructure/ansible`, le bootstrap ArgoCD/GitLab dans
  `platform-cicd/ansible`.
- Le pipeline générique (`ci-templates`) couvre le tag unique `vX.Y.Z`, le
  build once/promote everywhere, les gates manuels, le rollback prod et le
  self-heal ArgoCD.

Dette active hors chaîne CI/CD applicative :

- **Sandbox Ansible/k8s** : le contenu `ansible/`, Vagrant et Packer porte
  désormais le cluster local du POC. Avant de le considérer reproductible sur
  une autre machine, il faut supprimer les chemins propres à l'environnement
  local dans l'inventaire et les variables.
- **Migration des manifests applicatifs vers `HTTPRoute`** : les apps doivent
  converger vers des `HTTPRoute` au lieu d'`Ingress`; la phase transitoire doit
  rester courte et explicite.

## Contraintes d'environnement déjà identifiées

- Cluster mono-nœud arm64 (Apple Silicon) : toute image dépendant de
  l'architecture (ex. `helper_image` du GitLab Runner) doit être épinglée en
  `arm64` explicitement.
- Pas de cert-manager sur ce cluster local : le TLS est terminé par la
  Gateway Traefik avec un certificat wildcard auto-signé
  (`nip-io-wildcard-tls`). Le chart GitLab doit garder
  `global.hosts.https: true` pour annoncer son URL publique en HTTPS (OAuth,
  callbacks, cookies de session), même si les pods GitLab servent en HTTP
  derrière la Gateway.
- Vagrant publie l'adresse MetalLB exposée par Traefik vers l'hôte
  (`cluster-up` ou `cluster-from-images` dans le `Makefile`) : tout accès UI
  doit passer par le
  contrôleur HTTP déclaré (Traefik via Gateway API)
  avec les hosts `*.192.168.33.100.nip.io`, pas par `kubectl port-forward` direct
  vers un service, sous peine de mismatch Host/Origin.
- Les images applicatives sont poussées sur GHCR (registre externe,
  HTTPS) : pas de configuration `node-trust-registry`/résolution DNS
  interne au cluster à maintenir pour les pulls/pushs, contrairement à un
  registry interne au cluster.

## Annexe : infrastructure Ansible/k8s

`infrastructure` (Packer, Vagrant et playbooks Ansible) fournit le socle
Kubernetes local sur lequel la chaîne CI/CD `helloworld`, ArgoCD et GitLab
sont déployés. La séparation de responsabilités reste volontaire :
`infrastructure` construit et initialise le socle Kubernetes, `platform-cicd` déploie
la plateforme applicative, et `control-plane` orchestre le parcours complet.
