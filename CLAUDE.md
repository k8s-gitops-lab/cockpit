# Règles de travail — poc-devops

## Gouvernance du développement

Toute contribution respecte les trois axes de maîtrise — produit, code,
architecture — décrits dans `AGENTS.md`, section « Gouvernance du
développement » (qui fait foi).

## Workflow Git

Ne jamais modifier les fichiers directement dans l'interface GitLab (éditeur
web, merge request, etc.). Toujours : modifier en local, committer, pousser.

Tous les repos ont `origin` → `https://github.com/k8s-gitops-lab/<repo>`.
Seuls 4 repos ont aussi un remote `gitlab` (GitLab local de la plateforme,
chacun sous son groupe — aucun sous `root/`) :

- `ci-templates` → `.../shared-ci/ci-templates`
- `helloworld` → `.../hello-groupe/helloworld`
- `helloworld-iac` → `.../hello-groupe/helloworld-iac`
- `platform-gitops` → `.../infra/platform-gitops`

Où pousser (détail et rôles : `docs/source-control.md`) :

- Repos GitHub-first (défaut) :
  ```bash
  git push origin main
  ```
- Repos GitLab-first (`ci-templates`, `helloworld`, `helloworld-iac`,
  `platform-gitops` — la CI s'exerce sur GitLab, qui fait foi pour eux) :
  committer côté GitLab puis répercuter sur GitHub
  (`scripts/commit-gitlab-app-repos.sh` enchaîne pull --rebase, push GitLab
  et miroir GitHub) :
  ```bash
  git push gitlab main
  git push origin main
  ```
  Pour les tags : `git push gitlab --tags && git push origin --tags`.

  `platform-gitops` a en plus un miroir GitLab→GitHub automatique
  (`gitlab_project_mirror.platform_gitops_to_github`, côté
  `gitlab-projects-iac`) qui **force-écrase** `origin/main` pour qu'il
  corresponde exactement à `gitlab/main` — un commit poussé seulement sur
  `origin` pour ce repo est silencieusement perdu au prochain passage du
  miroir s'il n'est pas aussi sur `gitlab`. Toujours pousser `gitlab`
  d'abord pour ce repo, jamais `origin` seul (incident vécu le
  2026-07-09 : 3 commits GitHub-only effacés par le miroir).

## Règle : tout commit finit sur GitHub

Tout commit doit être poussé sur `origin` (GitHub) — c'est non négociable, y
compris quand `gitlab` est injoignable depuis l'environnement courant (dans
ce cas, pousser sur GitHub quand même et repousser sur GitLab plus tard).

Si un commit est créé côté GitLab (ex. merge d'une MR), il doit aussi être
répercuté sur GitHub : récupérer la branche depuis `gitlab` et la pousser
vers `origin` avant de considérer le travail terminé.

## OpenWiki

This repository has documentation located in the /openwiki directory.

Start here:
- [OpenWiki quickstart](openwiki/quickstart.md)

OpenWiki includes repository overview, architecture notes, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

When working in this repository, read the OpenWiki quickstart first, then follow its links to the relevant architecture, workflow, domain, operation, and testing notes.
