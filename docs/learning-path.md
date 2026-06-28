# Parcours d'apprentissage

Ce parcours sert a comprendre le POC par etapes. Il se lit comme une sequence
operateur, puis comme une sequence developpeur applicatif.

## 1. Comprendre les responsabilites

Lire d'abord :

```sh
cat docs/repo-map.md
cat README.md
```

Objectif : savoir quel repo porte le cluster, le bootstrap, l'etat GitOps, les
outils partages, le pipeline et l'application exemple.

## 2. Demarrer le socle

Depuis `control-plane` :

```sh
make env
make platform-fast-up
```

`platform-fast-up` utilise les images Vagrant deja construites, demarre le
cluster, puis bootstrappe ArgoCD et la plateforme.

Pour le parcours complet avec reconstruction des images :

```sh
make platform-up
```

## 3. Recuperer les acces

```sh
make argocd-password
make gitlab-password
```

URLs par defaut :

- GitLab : `http://gitlab.192.168.33.100.nip.io`
- ArgoCD : `http://argocd.192.168.33.100.nip.io`
- Registry : `http://registry.192.168.33.100.nip.io`

## 4. Observer la convergence GitOps

```sh
make status
```

Dans ArgoCD, verifier que le root Application lit le depot `platform-gitops`
et cree les Applications de plateforme et d'applications. Le code source de
`platform-gitops` vit sur GitHub ; les depots applicatifs importes dans GitLab
servent ensuite aux pipelines et aux synchronisations runtime.

## 5. Seeder GitLab

```sh
make gitlab-seed
make argocd-repo-creds
```

Ces commandes passent par `toolbox` et lisent l'inventaire
`platform-gitops/argocd/apps.yaml`, puis creent ou mettent a jour les projets
dans le GitLab interne.

## 6. Jouer le parcours applicatif

Dans GitLab, observer les projets `root/helloworld`,
`root/helloworld-iac` et `root/ci-templates`.

Le flow attendu :

1. merge sur `main` dans `helloworld` ;
2. build dev ;
3. commit GitOps sur la branche `dev` de `helloworld-iac` ;
4. sync ArgoCD vers le namespace `helloworld-dev`.

Pour une release :

1. lancer le job `semantic-release` ;
2. laisser `deploy-rec` se jouer automatiquement ;
3. jouer manuellement `deploy-preprod` si active ;
4. jouer manuellement `deploy-prod`.

## 7. Modifier l'inventaire GitOps

Toute modification d'app se fait dans `platform-gitops` :

```sh
cd platform-gitops
vim argocd/apps/<app>.yaml
cd platform-cicd
make argocd-apps-render
```

Puis commit et push depuis `platform-gitops`. Pour une operation sur la
plateforme deployee, ouvrir la pull request sur le depot GitHub
`poc-devops-elkouhen/platform-gitops`. ArgoCD lit Git, pas le disque local.

## 8. Arreter la plateforme

```sh
make platform-down
```

Pour detruire les VMs :

```sh
make platform-destroy
```
