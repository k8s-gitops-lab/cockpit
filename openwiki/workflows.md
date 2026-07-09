# Workflows

Two distinct user profiles use this workspace, at two different times —
this split is the backbone of [`README.md`](../README.md), "Parcours
utilisateurs".

## Journey 1 — Operator bootstraps the platform

**Prerequisites**: the workspace cloned side-by-side
(`bash scripts/clone-github-org.sh`), and the GHCR secret configured once
via `make ghcr-token-init` (generates/reuses a local age key, encrypts
`platform-gitops/flux-secrets/ghcr-pull-secret.yaml` — see
[Operations → Secrets management](operations.md#secrets-management)). That
encrypted file must be committed/pushed to `platform-gitops` **before**
running the full sequence, since Flux reads GitHub.

### `make platform-up`: the full sequence

```sh
make platform-up
```

This single command builds everything from scratch and is **idempotent**:
on failure it resumes at the right step automatically, and on every rerun
it re-verifies that already-completed steps still hold before skipping
them — it is a *reconciliation* command, not just a crash-resume
(`README.md`, `AGENTS.md`).

The sequence, as encoded in `scripts/bootstrap.py`'s `STEPS` list:

| Step | Make target | Convergence check (`platform_checks.py`) |
|---|---|---|
| `vm-images` | `vm-images` | `check_vm_images` |
| `cluster-from-images` | `cluster-from-images` | `check_cluster` |
| `snapshot-cluster` | `snapshot-cluster` | `check_vm_snapshot` |
| `platform-bootstrap` | `platform-bootstrap` | `check_argocd_ready` |
| `ghcr-pull-secret` | `ghcr-pull-secret-wait` | `check_ghcr_secret` |
| `gitlab-git-creds` | `gitlab-git-credentials` | `check_git_creds` |
| `gitlab-projects` | `gitlab-projects-wait` | `check_gitlab_iac` |
| `argocd-apps` | `argocd-apps-wait` | `check_apps_synced` |
| `platform-verify` | `platform-verify` | full smoke test (subprocess) |

### `platform-up` resume and convergence

`scripts/bootstrap.py` persists progress to `.bootstrap-state.json`
(not committed — contains local run state), including a hash of
`platform.yml` so a config change invalidates the saved state. On each run:

1. It determines a resume point from the last-recorded completed steps.
2. Unless `--no-verify` is passed, it **re-runs the convergence check** for
   every step already marked complete — the first one that no longer holds
   (VM destroyed, secret deleted, PAT revoked...) becomes the new resume
   point. This is what makes repeated `make platform-up` runs safe and
   self-healing rather than blindly trusting stale state.
3. It runs remaining steps via `make <target> CONFIG=...`, recording
   duration and timestamp per step, and prints a final per-step duration
   summary.
4. On a step failure, it exits with the step name so the operator can fix
   the issue and simply rerun the same command.

`make platform-bootstrap-status` shows step completion + duration without
running anything; `make platform-bootstrap-reset` clears the saved state.

**Why `argocd-apps-wait` exists** (commit `8fee308`, 2026-07-09): the
`argocd-apps` check in `platform-verify` used to run as a one-shot
immediately after `gitlab-projects-wait`, but ArgoCD needs time after
GitLab project creation to refresh repos and reconcile — Applications pass
through transitory `Unknown`/`Progressing`/`Degraded` states for several
minutes. `argocd-apps-wait` (same polling pattern as `gitlab-iac-wait`,
default timeout 900s via `ARGOCD_APPS_TIMEOUT`) was inserted as its own
bootstrap step before `platform-verify` to poll until convergence instead
of failing.

### Variants

- `make platform-provision` — same as `platform-up` but skips rebuilding
  Packer VM images (`--from cluster-from-images`).
- `make platform-from-snapshot` — restores a VirtualBox snapshot taken
  right after cluster provisioning (`make snapshot-cluster`,
  `SNAPSHOT_NAME` default `cluster-ready`) and resumes directly at
  `platform-bootstrap`, skipping Packer/Vagrant/kubeadm entirely. Useful to
  replay only the CI/CD bootstrap repeatedly.
- `make platform-bootstrap START_AT=<step>` — resume only the
  platform-bootstrap sub-sequence (delegates to `platform-bootstrap`'s own
  Ansible-driven resume, see `.agents/skills/poc-devops-ansible/SKILL.md`).

### Post-bootstrap operator commands

- `make platform-verify` — replay the smoke test at any time (cluster,
  GitLab, ArgoCD Applications Synced/Healthy, GHCR secret, PAT, per-app
  GitLab projects/pipelines). For each inventory app it also validates that
  every `include: component:` referenced by the app's `.gitlab-ci.yml`
  actually resolves — same lookup GitLab itself performs (`templates/<name>/
  template.yml` in the referenced project at the referenced tag), followed
  recursively into components-of-components (`check_app_ci_components` in
  `scripts/platform_checks.py`). This catches a broken/renamed `ci-templates`
  ref, or a missing `to-be-continuous` mirror entry, before a real pipeline
  run would fail with "component content not found".
- `make argocd-status` — ArgoCD sync state.
- `make argocd-password` / `make gitlab-password` — retrieve initial admin
  passwords.

## Journey 2 — Application team onboards a project

**Prerequisites**: the platform is already up (Journey 1 done), and
`make gitlab-git-credentials` has been run at least once (stored GitLab
git credentials for the internal host).

1. Write the app's code (`<app>/`) and its manifests repo (`<app>-iac/`),
   reusing `ci-templates` for CI (`helloworld`/`helloworld-iac` are the
   reference example).
2. Open a merge request directly on the `platform-gitops` GitLab project,
   adding `argocd/apps/<app>.yaml` in **minimal format**: `name`, `group`,
   `description`, `services`, `hasPreprod`. Everything else (`repoURL`,
   namespaces, URLs, ArgoCD destinations) is derived by convention by
   `toolbox/scripts/platform_inventory.py`.
3. At merge time, the chain triggers automatically, with **no manual
   action**: ArgoCD manifest regeneration (`ApplicationSet`/`AppProject`),
   Terraform inventory regeneration (`apps.auto.tfvars.json`), creation of
   the corresponding (empty) GitLab projects, then ArgoCD sync of the
   declared environments.
4. Push the initial code to the newly created (empty) GitLab projects —
   see the exact `git remote add`/`push` commands in
   [`README.md`](../README.md#parcours-2--une-équipe-applicative-crée-un-projet).
5. Verify: the project appears in GitLab, matching ArgoCD `Application`
   resources are visible/synced, and the first merge on `<app>` triggers
   the `ci-templates` pipeline (build once, auto-deploy to `dev`).
6. Subsequent pushes follow the `ci-templates` promotion pipeline: build
   once, promote dev → rec → preprod (optional) → prod by tag.

Full technical detail of each step (seed vs render distinction, inventory
schema, CI job structure) lives in `docs/spec-fonctionnelle.md` and
`docs/spec-technique.md` — this repo only orchestrates and documents the
cross-repo narrative; the actual mechanics live in `platform-bootstrap`,
`toolbox`, `gitlab-projects-iac`, and `ci-templates`.

## Full `make` targets reference

Run `make help` for the live, auto-generated list (parsed from `## `
comments in the `Makefile`). Key targets not already covered above:

| Target | Effect |
|---|---|
| `make env` | Print exported variables from `platform.yml` without applying them |
| `make validate` | Compile all Python scripts, validate `platform.yml`, validate `.agents/skills/*` |
| `make cluster-up` | Cluster only, without Packer images |
| `make snapshot-cluster` / `make restore-cluster` | VirtualBox snapshot lifecycle for the cluster |
| `make platform-down` / `make platform-destroy` | Power off / destroy platform VMs |
| `make gitlab-terraform-credentials` | Create/rotate the GitLab PAT consumed by Terraform |

## Tests / checks relevant to changing this repo

- `make validate` — must pass after any script or skill change (compiles
  Python, validates config, validates skills).
- `make platform-verify` — the functional acceptance check; per
  `AGENTS.md`'s governance rule, a change is "reliable" once both
  `make validate` and `make platform-verify` pass.
- `scripts/validate-skills.py` catches stale cross-repo path references in
  `.agents/skills/*/SKILL.md` — run it if you rename a path in a sibling repo
  that a skill file cites.
