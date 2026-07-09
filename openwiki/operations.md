# Operations

## Security posture (POC-scoped shortcuts)

Full detail: [`docs/security-poc.md`](../docs/security-poc.md). This POC
assumes a disposable local network; the shortcuts below are accepted here
but must **not** become defaults for a shared/durable environment
(also see [`docs/prod-constraints.md`](../docs/prod-constraints.md) for the
full production-readiness gap list).

- **TLS**: GitLab and ArgoCD are exposed over HTTPS on `*.nip.io` via a
  wildcard certificate (`nip-io-wildcard-tls`) terminated by the Traefik
  Gateway, issued/renewed by cert-manager from a **self-signed internal CA**
  (`ClusterIssuer poc-lab-ca-issuer`). The certificate lifecycle is managed,
  but the CA itself is not publicly trusted — tools must explicitly trust it
  (`GITLAB_INSECURE_TLS=true`, trust store setup for `semantic-release`).
  GHCR (external registry) already has public TLS, so no internal registry
  TLS concern exists.
- **Bootstrap accounts**: seed scripts use the GitLab `root` account or
  bootstrap tokens. ArgoCD repository secrets are derived directly from the
  GitLab root initial password by External Secrets Operator — fully
  declarative but unscoped. A durable platform would need per-purpose
  scoped tokens (seed, manifest push, read-only ArgoCD PAT, runner
  registration).
- **Corporate CA**: the ArgoCD bootstrap injects a local CA from the macOS
  keychain. A durable platform would manage this as a declared,
  GitOps-applied secret/config instead.

## Secrets management: SOPS + age {#secrets-management}

Credentials that must not appear in cleartext in git (service tokens,
`dockerconfigjson`) are stored in `platform-gitops/flux-secrets/` as
SOPS-encrypted files (age backend), decrypted in-cluster by the Flux
`flux-secrets` Kustomization. No `kubectl` decryption ever runs from the
operator's machine.

```
platform-gitops/.sops.yaml                  # encryption rule (committed, public key only)
platform-gitops/flux-secrets/*.yaml         # encrypted files (committed)
~/.config/sops/age/keys.txt                 # private key (NEVER committed)
```

First-time setup for a new operator: `make ghcr-token-init`
(`scripts/ghcr-token-init.py`). This is **idempotent per-operator** — each
operator has their own local age key, and `platform-gitops/.sops.yaml`
declares only the *current* operator's key as the sole recipient (one
operator = one local environment model). Re-running the command rotates
the GitHub PAT without touching the age key. **Caveat**: switching age keys
makes any other `flux-secrets/*.yaml` file (e.g. `github-credentials.yaml`)
undecryptable by Flux until it is regenerated with the new key.

To edit another secret manually or without the script:

```sh
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops flux-secrets/ghcr-pull-secret.yaml
```

After running `ghcr-token-init`, commit/push `.sops.yaml` and
`flux-secrets/ghcr-pull-secret.yaml` in `platform-gitops` **on `origin`**
(Flux reads GitHub) before running `make platform-up` /
`make ghcr-pull-secret-wait`.

## Git workflow: dual remote {#git-workflow}

Every workspace repo has `origin` → GitHub
(`https://github.com/k8s-gitops-lab/<repo>`), which is **non-negotiable
source of truth**. Four repos additionally have a `gitlab` remote (the
local platform GitLab, one group per repo, none under `root/`):
`ci-templates`, `helloworld`, `helloworld-iac`, `platform-gitops`.

Two different truth directions coexist (`docs/source-control.md`):

- **GitHub-first repos** (default, including `platform-gitops` itself as a
  *source* repo): `git push origin main`. Synced across the workspace with
  `scripts/commit-push-subprojects.sh --remote github`.
- **GitLab-first repos** (`ci-templates`, `helloworld`, `helloworld-iac` —
  CI actually runs on GitLab, which is authoritative for them): commit on
  GitLab first, then mirror to GitHub via
  `scripts/commit-gitlab-app-repos.sh` (`git push gitlab main` then
  `git push origin main`).

**Absolute rule**: every commit ends up on GitHub, even if `gitlab` is
unreachable — push to GitHub anyway and re-push to GitLab later; the
reverse (GitLab only, GitHub later) is never acceptable
(`CLAUDE.md`, `.agents/skills/poc-devops-git/SKILL.md`).

**Never edit files directly in the GitLab web UI** (editor, MR merge
button excluded — always modify locally, commit, then double-push.

`PLATFORM_REPO_URL` (used by toolbox commands) always points to
`platform-gitops` on **GitHub** — the source repo that receives inventory
PRs/branches, distinct from the internal GitLab URL ArgoCD uses at runtime
(`gitlab-webservice-default.gitlab.svc.cluster.local:8181`). During the
very first bootstrap, ArgoCD may still reference GitHub to avoid a circular
dependency (GitLab itself is described by the GitOps config it would need
to read).

## Governance rules

`AGENTS.md` defines three axes of control that any change (human or agent)
must respect, enforced by a quarterly governance review tracked in
[`docs/backlog.md`](../docs/backlog.md):

1. **Product control** — new work must fit [`docs/prd.md`](../docs/prd.md)
   and be tracked in `docs/backlog.md`. A **product idea** needs a backlog
   entry *before* implementation; a **fix/chore** needs one *at commit time*
   at the latest.
2. **Code control** — keep code simple and reliable: prefer the simplest
   working solution, avoid premature abstraction, don't add a mechanism
   (option, layer, genericity) without a proven need. A change is
   considered reliable once `make validate` and `make platform-verify` pass.
3. **Architecture control** — inter-repo dependencies must match
   [`docs/repo-map.md`](../docs/repo-map.md) (any new cross-repo dependency
   must be justified and documented there); components used must stay
   maintained/supported at reasonably current versions — version upgrades
   are normal platform maintenance, tracked in `docs/backlog.md`'s
   "Entretien courant" section.

## Known production gaps

`docs/prod-constraints.md` lists what a real production rollout of this
POC's pattern would additionally require, grouped by: ArgoCD/GitOps, security,
CI/CD, infrastructure, observability, reliability, governance. Highlights
of the **currently accepted POC gaps** (also see `docs/prd.md`'s explicit
non-goals section):

- Environment branches (`dev`/`rec`/`preprod`) in the manifests repo are
  **not** protected against direct human pushes — only `main` is protected.
  Acceptable in this mono-operator POC (the CI token identity and the human
  git identity are the same `root` account); would need a dedicated CI
  service account with a real team.
- `GITLAB_PUSH_TOKEN` is a personal `root` token with full `api` scope, not
  a project-scoped token — maximizes blast radius on leak. Tracked as
  pre-industrialization debt in `docs/prd.md` and as "Axe 7" in
  `docs/backlog.md`.
- No HA, no external secret manager (Vault/KMS), self-signed TLS CA, no
  image signing/admission policy.

## Verification and troubleshooting commands

- `make platform-verify` — full smoke test at any time; also used
  internally by `bootstrap.py` as the final convergence check.
- `make argocd-status` — ArgoCD Application sync state.
- `make platform-bootstrap-status` — resume state of `platform-up` (which
  steps are done, with durations).
- `kubectl -n <argocd namespace> get applications.argoproj.io` — raw
  ArgoCD Application status, suggested by `argocd-apps-wait.py` on timeout.
- `docs/backlog.md` — check "Entretien courant" and "Dette transverse"
  sections before assuming a known issue is undocumented; e.g. pending
  commits not yet pushed to the `gitlab` remote are tracked there.

## What to check before changing operations-related code

- Any new secret must go through the SOPS/age flow in `platform-gitops`,
  never committed in cleartext, and never decrypted via ad hoc `kubectl` on
  the operator's machine.
- Any new cross-repo command must preserve the dual-remote push discipline
  — a task is not complete with only one remote updated.
- Any new automation must be traceable to a backlog entry per the
  governance rule, and validated with `make validate` +
  `make platform-verify` before being considered reliable.
