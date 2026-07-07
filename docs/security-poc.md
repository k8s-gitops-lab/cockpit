# Raccourcis de securite du POC

Ce POC assume un reseau local jetable. Les choix suivants sont acceptes pour
reduire le cout de bootstrap, mais ne doivent pas devenir les valeurs par
defaut d'un environnement partage ou durable.

## TLS auto-signe

GitLab et ArgoCD sont exposes en HTTPS sur `*.nip.io`, avec un certificat
wildcard auto-signe termine par la Gateway Traefik (`nip-io-wildcard-tls`) —
a accepter dans le navigateur, et a faire confiance explicitement dans les
outils (scripts bootstrap `GITLAB_INSECURE_TLS=true`, trust store du job
`semantic-release`). Pour une plateforme durable, remplacer par des
certificats geres (cert-manager, PKI) et une policy d'entree explicite.
Les images applicatives sont poussees sur GHCR (TLS public) : pas de registry
interne au cluster a securiser.

## Comptes bootstrap

Les scripts de seed utilisent le compte `root` GitLab ou des tokens de bootstrap.
Pour une plateforme durable, creer des tokens scopes par usage : seed, push
manifests, lecture ArgoCD, runner registration.

## CA corporate

Le bootstrap ArgoCD injecte une CA locale depuis le trousseau macOS. Pour une
plateforme durable, gerer la CA comme un secret/config declare, versionne selon
le niveau de sensibilite, et applique par GitOps.

## Gestion des secrets sensibles — SOPS + age

Les credentials qui ne doivent pas apparaitre en clair dans git (tokens de
service, secrets `dockerconfigjson`) sont stockes dans `secrets/` sous forme
de fichiers SOPS chiffres avec `age` — par exemple
`secrets/ghcr-pull-secret.yaml`, decrypte par `make ghcr-pull-secret`.

### Structure

```
.sops.yaml              # règle de chiffrement (commité)
secrets/*.yaml           # fichiers chiffrés (commités)
~/.config/sops/age/keys.txt # clé privée age (JAMAIS commitée)
```

### Prérequis

```bash
brew install age sops
```

### Premier parametrage (nouvel operateur) : `make ghcr-token-init`

Chaque operateur du POC travaille avec sa propre cle age locale : `.sops.yaml`
ne declare qu'un seul recipient a la fois, celui de l'operateur courant. En
clonant le workspace, remplacer ce recipient et regenerer le secret GHCR se
fait en une commande :

```bash
make ghcr-token-init
```

Cette commande (`scripts/ghcr-token-init.py`) :

1. Genere `~/.config/sops/age/keys.txt` si absente (reutilisee sinon).
2. Enregistre la cle publique correspondante comme recipient dans `.sops.yaml`.
3. Demande un compte GitHub et un PAT (scope `read:packages`, saisie masquee) —
   un lien de creation rapide du token est affiche.
4. Construit et chiffre `secrets/ghcr-pull-secret.yaml` (memes conventions que
   le fichier existant : seul `stringData` est chiffre, via
   `--encrypted-regex '^(stringData|data)$'`).
5. Verifie que le secret est bien dechiffrable avec la cle locale.

A l'issue de la commande, committer/pousser `.sops.yaml` et
`secrets/ghcr-pull-secret.yaml` avant `make platform-up` / `make
ghcr-pull-secret`. Rejouer la commande plus tard permet de faire tourner
(rotate) le token GitHub sans toucher a la cle age.

### Modifier un secret manuellement

Pour les autres secrets `secrets/*.yaml`, ou pour editer `ghcr-pull-secret.yaml`
sans repasser par le script :

```bash
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops secrets/ghcr-pull-secret.yaml
```

SOPS ouvre l'editeur avec le contenu dechiffre. A la fermeture, le fichier est
re-chiffre automatiquement.

### Lire une valeur manuellement

```bash
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
  sops --decrypt --extract '["stringData"][".dockerconfigjson"]' secrets/ghcr-pull-secret.yaml
```

### Ce qui est commité / non commité

| Fichier | Commité | Raison |
|---|---|---|
| `.sops.yaml` | oui | contient uniquement la clé publique |
| `secrets/*.yaml` | oui | chiffré par SOPS, illisible sans la clé privée |
| `~/.config/sops/age/keys.txt` | non | clé privée, à sauvegarder hors git |

Pour une plateforme durable, centraliser la clé dans un gestionnaire de secrets
(Vault, AWS Secrets Manager) et remplacer `age` par le KMS correspondant.
