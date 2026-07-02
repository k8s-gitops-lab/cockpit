# Règles de travail — poc-devops

## Workflow Git

Ne jamais modifier les fichiers directement dans l'interface GitLab (éditeur web, merge request, etc.).

Toujours :
1. Faire les modifications en local.
2. Committer localement.
3. Pousser vers les deux remotes :
   ```bash
   git push origin main   # GitHub
   git push gitlab main   # GitLab local
   ```
   Pour les tags :
   ```bash
   git push origin --tags
   git push gitlab --tags
   ```

Les remotes disponibles dans tous les repos du POC :
- `origin` → `https://github.com/k8s-gitops-lab/<repo>`
- `gitlab` → `http(s)://gitlab.192.168.33.100.nip.io/root/<repo>`

## Règle : GitHub fait foi

Tout commit doit être poussé sur `origin` (GitHub) — c'est non négociable, y
compris quand `gitlab` est injoignable depuis l'environnement courant (dans
ce cas, pousser sur GitHub quand même et repousser sur GitLab plus tard).

Si un commit est créé côté GitLab (ex. merge d'une MR), il doit aussi être
répercuté sur GitHub : récupérer la branche depuis `gitlab` et la pousser
vers `origin` avant de considérer le travail terminé.
