# Strategie de test

Cette strategie couvre le POC complet, pas seulement le repo `control-plane`.
Elle vise a donner rapidement confiance dans une chaine locale Kubernetes,
GitLab, ArgoCD, registry interne et deploiement applicatif GitOps, tout en
gardant un cout de test compatible avec un environnement de developpement.

## Objectifs

- Verifier que les fichiers de configuration sont lisibles, coherents et
  versionnes explicitement.
- Detecter tot les erreurs de rendu, de schema, de chemins inter-repos et de
  variables d'environnement.
- Prouver que le bootstrap converge de maniere idempotente.
- Prouver le parcours applicatif attendu : merge vers `dev`, release vers
  `rec`, gate optionnel `preprod`, gate `prod`.
- Verifier les controles critiques du POC : branches, tags, protected
  environments, ArgoCD self-heal et absence de rebuild pendant la promotion.

## Niveaux de test

### 1. Validations locales rapides

Ces tests doivent tourner avant tout bootstrap long ou toute modification de
contrat inter-repos.

| Cible | Commande / preuve | Attendu |
|---|---|---|
| YAML du profil operateur | `python3 - <<'PY' ... yaml.safe_load(...)` ou test dedie | `platform.yml` est parseable et contient les cles requises. |
| Export d'environnement | `make env` | Toutes les variables attendues sont exportees avec quoting shell correct. |
| Makefile control-plane | `make -n <target>` pour les cibles non destructives | Les commandes deleguent vers les bons repos et passent les bonnes surcharges. |
| Scripts Python | `PYTHONPYCACHEPREFIX=/tmp/control-plane-pycache python3 -m py_compile scripts/*.py` | Pas d'erreur de syntaxe. |
| Documentation operateur | revue des liens `docs/*.md` | Les commandes documentees existent encore. |

Pour `control-plane`, la priorite de test unitaire est
`scripts/export-env.py`, car c'est le contrat qui alimente toutes les cibles
Make.

### 2. Contrats inter-repos

Ces tests verifient que les repos du workspace restent compatibles entre eux
sans demarrer tout le cluster.

| Contrat | Verification |
|---|---|
| `control-plane` -> `cluster` | Les chemins de `platform.repositories.cluster` existent et exposent les cibles appelees (`up`, `create-cluster`, `down`, `destroy`). |
| `control-plane` -> `platform-cicd` | Le repo expose `bootstrap`, `status`, `argocd-password`, `gitlab-password`. |
| `control-plane` -> `toolbox` | Le repo expose `gitlab-seed` et `argocd-repo-creds`. |
| `platform-gitops` -> `toolbox` | L'inventaire applicatif est parseable par les scripts de seed et de rendu. |
| `ci-templates` -> apps | Chaque `.gitlab-ci.yml` applicatif inclut une `ref` explicite du template, jamais `main` par defaut. |

Ces controles peuvent devenir une cible `make validate-workspace` dans
`control-plane` lorsque le workspace se stabilise.

### 3. Tests IaC et rendu

Ces tests doivent tourner dans les repos proprietaires des ressources qu'ils
valident.

| Repo | Tests attendus |
|---|---|
| `cluster` | `ansible-playbook --syntax-check`, rendu des templates critiques, verification des versions Gateway API, MetalLB, Traefik. |
| `platform-cicd` | Rendu Helm/Kubernetes des composants bootstrap, validation des manifests ArgoCD et des namespaces. |
| `platform-gitops` | Rendu `ApplicationSet`, validation des `Application`, `AppProject`, `HTTPRoute`, `Service`, `Deployment` et `Kustomization`. |
| `toolbox` | Tests unitaires des scripts de seed, fixtures d'inventaire multi-apps, tests d'idempotence des operations GitLab simulees. |
| `ci-templates` | Lint GitLab CI du template, tests des `rules`, verification des jobs par contexte (`main`, tag, gate manuel). |
| `helloworld-iac` | `kustomize build`, absence d'`Ingress` durable si la cible est Gateway API, probes et ressources presentes. |

Critere commun : une modification de schema ou de template doit etre testee
avec au moins une app single-service et une app multi-services, meme si
`helloworld` reste l'app de reference.

### 4. Integration cluster

Ces tests exigent un cluster local demarre.

Parcours minimal :

```sh
make platform-fast-up
make status
make gitlab-seed
make argocd-repo-creds
```

Verifications attendues :

- le cluster Kubernetes repond et les nodes sont `Ready` ;
- Gateway API, MetalLB, Traefik et la Gateway partagee sont deployes ;
- ArgoCD est accessible et le root Application converge ;
- GitLab, le registry et l'exposition HTTP ArgoCD sont synchronises par
  ArgoCD ;
- les projets GitLab applicatifs et manifests existent ;
- les credentials ArgoCD permettent de lire les repos manifests prives ;
- les Applications applicatives existent pour les environnements declares.

Le test est reussi uniquement si une relance des commandes de bootstrap ne
detruit pas l'etat attendu et ne cree pas de doublons fonctionnels.

### 5. End-to-end applicatif

Le test bout en bout de reference est `helloworld`.

Scenario `dev` :

1. merger un changement applicatif dans `main` ;
2. verifier que le pipeline build les services attendus ;
3. verifier le push des images vers le registry interne ;
4. verifier le commit automatique sur la branche manifests `dev` ;
5. verifier la synchronisation ArgoCD vers `helloworld-dev` ;
6. appeler l'URL applicative et verifier la reponse du frontend et de l'API.

Scenario release :

1. lancer `semantic-release` depuis `main` ;
2. verifier la creation du tag `vX.Y.Z` et de la Release GitLab ;
3. verifier que `deploy-rec` construit une seule fois les images taguees
   `vX.Y.Z` ;
4. verifier que `deploy-preprod`, si actif, ne reconstruit pas d'image ;
5. verifier que `deploy-prod` ne reconstruit pas d'image et pousse l'etat sur
   la branche manifests `main` ;
6. verifier dans ArgoCD que chaque environnement pointe vers la meme version
   applicative ;
7. verifier l'acces HTTP de chaque environnement expose.

Scenario rollback :

1. revert du commit cible dans le depot manifests de production ;
2. synchronisation ArgoCD ;
3. verification que la version precedente est redeployee sans rebuild.

## Tests de securite du POC

Ces controles ne transforment pas le POC en plateforme de production, mais ils
verifient que les limites documentees restent conscientes et visibles.

- GitLab : `main` du depot de code protege, push direct interdit, merge
  reserve aux Maintainers.
- GitLab : `deploy-prod` restreint par protected environment.
- GitLab : les branches manifests d'environnement ont le niveau de protection
  attendu pour le POC, avec les limites documentees dans le PRD.
- CI : `GITLAB_PUSH_TOKEN` masque dans les logs et non imprime par les scripts.
- CI : le template applicatif est inclus avec une `ref` versionnee.
- Registry : aucune promotion ne retag une image mutable vers la production.
- ArgoCD : `selfHeal` corrige une derive manuelle volontaire sur une ressource
  applicative non critique.

## Tests de non-regression prioritaires

Les regressions les plus couteuses pour ce POC sont :

- un changement de `platform.yml` qui casse `make env` ou une delegation Make ;
- une version de chart ou CRD incompatible avec les manifests rendus ;
- un changement d'inventaire qui genere des `Application` ou `AppProject`
  trop permissifs ;
- un template CI qui build plusieurs fois une release ou promeut une image
  differente entre `rec`, `preprod` et `prod` ;
- une operation de seed non idempotente qui casse un projet GitLab existant ;
- une divergence entre la documentation operateur et les cibles Make reelles.

Ces cas doivent avoir un test automatique ou, a defaut, une verification
manuelle explicite dans la checklist de release du POC.

## Definition of Done

Une evolution est consideree testee si :

- les validations locales rapides passent ;
- les contrats inter-repos touches ont ete verifies ;
- les manifests ou templates modifies ont ete rendus et valides ;
- le bootstrap ou le seed concerne est relance au moins deux fois sans effet
  secondaire non attendu ;
- un changement CI/CD touchant la promotion est valide par un scenario
  `helloworld` complet jusqu'au dernier environnement concerne ;
- les limites de securite modifiees sont reportees dans `docs/security-poc.md`
  ou `docs/prod-constraints.md` si elles changent le risque accepte.

## Automatisation cible

Court terme :

- utiliser `make validate` dans `control-plane` pour compiler les scripts
  Python, parser `platform.yml`, tester `make env` et lancer les tests
  unitaires ;
- utiliser `make validate-workspace` pour verifier l'existence des repos
  voisins et des cibles Make appelees ;
- maintenir les tests unitaires de `scripts/export-env.py` quand le contrat
  d'environnement evolue.

Moyen terme :

- centraliser les checks statiques dans chaque repo specialise ;
- lancer les rendus Helm/Kustomize/ApplicationSet en CI ;
- ajouter un job nightly ou manuel de smoke test `platform-fast-up` sur une
  machine capable d'executer Vagrant/libvirt ;
- conserver les preuves de test de release : tag, digest d'image, commit
  manifests, sync ArgoCD, approbateur du gate prod.

Hors perimetre POC :

- tests de charge representatifs ;
- haute disponibilite ;
- disaster recovery complet ;
- scan de vulnerabilites bloquant ;
- verification d'image signee par admission controller.

Ces sujets deviennent obligatoires dans une cible production et sont detailles
dans `docs/prod-constraints.md`.
