# Architecture

## Role of `cockpit` in the system

`cockpit` is a **non-runtime, operator-facing orchestration layer**. It
never runs inside the Kubernetes cluster it helps build, and it is not a
dependency of any other repo's own execution path — sibling repos must
keep working standalone (`AGENTS.md`, "Rôle du dépôt").

Concretely, `cockpit` provides:

- A `Makefile` exposing a single, memorable set of operator commands
  (`make platform-up`, `make platform-verify`, ...).
- `scripts/` — Python/bash glue code that calls into sibling repos' own
  Makefiles/scripts with explicit variables (never hardcoded values).
- `platform.yml` — a local override profile (see below).
- Workspace-wide scripts (cloning the org, committing/pushing across all
  repos, dual-remote git helpers).

## Dependency graph

The authoritative dependency graph for the whole workspace (not just
`cockpit`) lives in [`docs/repo-map.md`](../docs/repo-map.md), including a
mermaid diagram. Read that file for the full picture; the key facts
relevant to `cockpit` specifically:

- `cockpit -.-> infra-iac` via `make -C ../infra-iac` (cluster provisioning).
- `cockpit -.-> platform-bootstrap` via `make -C ../platform-bootstrap`
  (ArgoCD/GitLab bootstrap).
- `cockpit -.-> platform-gitops` — `ghcr-token-init.py` writes the encrypted
  GHCR pull secret directly into `platform-gitops/flux-secrets/`.
- `cockpit -.-> toolbox` — exposed as a path, but outside the main
  bootstrap flow.

These are all **dashed** (deployment/orchestration) edges, not content
dependencies — `cockpit` calls other repos' commands, it does not embed
their code. A recent example of this boundary being enforced: `repoURL` in
`platform-bootstrap` used to be a value baked from `platform-gitops`, which
was flagged as an "accidental coupling" and turned into an Ansible variable
(`gitops_repo_url`) instead — see `docs/repo-map.md`'s note on this.

One external dependency is also part of the graph and worth knowing when
debugging a broken app pipeline: the local GitLab group `to-be-continuous`
is a **mirror** of `gitlab.com/to-be-continuous`, created/refreshed by the
`gitlab-projects-iac` Terraform (GitLab only resolves `include: component:`
against its own instance — it cannot reach `gitlab.com` directly).
`ci-templates` includes these upstream components at a pinned version (e.g.
`docker@6.1.0`). Without this mirror, no `build-docker` job can pass for any
app — see `docs/repo-map.md`'s dependency diagram.

## `platform.yml`: override profile, not source of truth

[`platform.yml`](../platform.yml) declares only the values that are
*actually consumed* by a Makefile target in this repo:

```yaml
platform:
  domain: 192.168.33.100.nip.io
  gitlab: {namespace, internalHost}
  argocd: {namespace}
  repositories: {infrastructure, platform, gitops, toolbox}   # paths to sibling repos
versions:
  argocd: v3.4.4
```

Important boundary (`AGENTS.md`): **cluster substrate versions (Kubernetes,
Flannel, Helm, charts) are pinned in `infra-iac/ansible/group_vars/all.yml`,
not here.** Do not add a value to `platform.yml` unless a Makefile target in
*this* repo actually reads it — sibling repos keep their own defaults
independently.

`scripts/export-env.py` loads `platform.yml` (via `platform_checks.load_values`)
and prints `export KEY=value` shell statements, captured into `.cockpit.env`
by the `ENV` macro in the `Makefile`. **`.cockpit.env` is never committed**
(it contains local absolute paths) — see `AGENTS.md`, "Ce qu'il ne faut pas
faire".

## `scripts/` inventory and responsibility split

All scripts in this repo are orchestration for the *local* workspace only.
Platform bootstrap logic itself (installing ArgoCD, rendering ArgoCD apps,
GitLab runner tokens, Dex OAuth) lives in `platform-bootstrap/scripts/` and
is invoked via `make -C ../platform-bootstrap <target>` — it is **not**
duplicated here (`docs/spec-technique.md`, "Outillage partagé").

| Script | Purpose |
|---|---|
| `platform_checks.py` | Shared convergence checks + `platform.yml` loader. Used by `export-env.py`, `bootstrap.py`, `platform-verify.py`, `gitlab-git-creds.py`. Each check returns `(ok, detail)` without printing — callers decide the display format. |
| `bootstrap.py` | Drives `make platform-up`: resumable, self-verifying step sequencer (see [Workflows](workflows.md)). |
| `export-env.py` | Renders `platform.yml` into shell `export` statements. |
| `platform-verify.py` | End-to-end smoke test (cluster, GitLab, ArgoCD apps Synced/Healthy, GHCR secret, PAT, per-app GitLab projects/pipelines). |
| `gitlab-git-creds.py` | Creates/rotates the GitLab root PAT stored in `git-credential` for the internal cluster host. |
| `ghcr-token-init.py` | Generates the local age key, registers it as SOPS recipient, encrypts `platform-gitops/flux-secrets/ghcr-pull-secret.yaml` from a GitHub PAT. |
| `gitlab-iac-wait.py` | Waits for the Terraform-managed GitLab projects (`gitlab-projects-iac`, applied by Flux) to converge. |
| `argocd-apps-wait.py` | Waits for all ArgoCD `Application` resources to reach Synced/Healthy — added in commit `8fee308` to fix `platform-verify` racing ahead of ArgoCD convergence after GitLab projects are created. |
| `validate-skills.py` | Validates `.agents/skills/*/SKILL.md` frontmatter and checks that any `repo/path` reference cited actually exists on disk. |
| `clone-github-org.sh` | Clones/updates all workspace repos side-by-side from the GitHub org. |
| `commit-push-subprojects.sh` / `commit-gitlab-app-repos.sh` | Cross-repo commit/push helpers — two scripts because two different remotes are authoritative for different repo subsets (see [Operations → Git workflow](operations.md#git-workflow)). |

## Deployment-mechanism preference order

`AGENTS.md` sets a strict ordering that applies to every repo in the
workspace, including any new automation added to `cockpit`:

1. **Declarative Terraform/Kubernetes resource** (TF provider, manifest
   applied by ArgoCD/Flux) — no custom script if a native resource suffices.
2. **Ansible** (playbook/role) for multi-step imperative tasks needing
   idempotence — used when a declarative resource isn't enough.
3. **Make**, last resort — a simple target that chains other commands or
   exposes an operator entrypoint, **never** a place for business logic.

This is why `bootstrap.py` (a Python state machine), not a chain of Make
targets, owns the resume/convergence logic for `platform-up` — see
[Workflows](workflows.md#platform-up-resume-and-convergence). Multi-step
orchestration *within* a single sibling repo (e.g. `platform-bootstrap`'s
own bootstrap sequence) is expected to use Ansible playbooks with tagged
roles, not nested Make targets — see
`.agents/skills/poc-devops-ansible/SKILL.md` for the detailed rationale
(never shell out to `ansible-playbook` from within a task, use
`include_role`/`import_role` instead).

## What to watch out for when changing this repo

- Never add a value to `platform.yml` that isn't consumed by a Makefile
  target here — see "override profile" above.
- Never call into a sibling repo's internals directly; always go through
  its Makefile (`make -C ../<repo> <target>`), passing explicit variables.
- If you add a new bootstrap step, it belongs in `scripts/bootstrap.py`'s
  `STEPS` list with its own convergence check in `platform_checks.py` — not
  as a bare Make target chain (see `argocd-apps-wait` as the template).
- `make validate` compiles all scripts and validates `platform.yml` and
  `.agents/skills/*` — run it after any script or skill change.
