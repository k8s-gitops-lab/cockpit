# OpenWiki Quickstart — cockpit

## What this repository is

`cockpit` is the **operator entrypoint** of a multi-repo proof-of-concept
(POC) for a self-hosted GitOps CI/CD platform (the `k8s-gitops-lab` GitHub
organization). It contains **no application runtime code**: it is a thin
orchestration layer — a `Makefile`, a set of Python/bash scripts, and a
local override profile (`platform.yml`) — that chains together commands
from several sibling repositories cloned side-by-side on the operator's
machine. See [`README.md`](../README.md) and [`AGENTS.md`](../AGENTS.md)
(French, canonical) for the full narrative; this wiki is a navigation and
synthesis layer over that existing documentation, not a replacement for it.

Key ground rule (from `AGENTS.md` / `README.md`): **`cockpit` orchestrates,
it does not own**. Every sibling repo must remain runnable standalone with
its own Makefile and defaults. `cockpit` only adds explicit variables and
sequencing on top.

## The workspace this repo sits in

`cockpit` is one of nine repositories cloned side-by-side (no git
submodules). Read them in this order to learn the system — this order is
documented in [`docs/repo-map.md`](../docs/repo-map.md):

| Repo | Role |
|---|---|
| `cockpit` (this repo) | Operator entrypoint, orchestrates the others |
| `infra-iac` | Local Kubernetes substrate (Packer/Vagrant/Ansible) |
| `platform-bootstrap` | Installs ArgoCD, bootstraps GitLab/credentials |
| `platform-gitops` | GitOps state continuously synced by ArgoCD |
| `toolbox` | Shared tooling: app onboarding, GitLab Terraform variable rendering |
| `gitlab-projects-iac` | Terraform provisioning of GitLab projects/branch protection/mirrors |
| `ci-templates` | Versioned generic GitLab CI pipeline, included by apps |
| `helloworld` | Reference example application (multi-service monorepo) |
| `helloworld-iac` | Reference example manifests repo (environment branches) |

See [Architecture](architecture.md) for the dependency graph and where
`cockpit` fits in it.

## What problem the platform (not just this repo) solves

The wider POC demonstrates a CI/CD chain where onboarding a new application
reduces to **one inventory file + one merge request** — no manual GitLab
project creation, no manual ArgoCD wiring. Full product intent, scope, and
explicit non-goals live in [`docs/prd.md`](../docs/prd.md); day-to-day
vocabulary (what "seed/rendu", "gate de promotion", "app standard" mean)
lives in [`CLAUDE.md`](../CLAUDE.md). See [Workflows](workflows.md) for the
two concrete user journeys this repo's `README.md` documents.

## Where to start reading

1. [`README.md`](../README.md) — the two user journeys (operator bootstrap,
   application onboarding) with copy-pasteable commands.
2. [`AGENTS.md`](../AGENTS.md) — governance rules any change (human or
   agent) must respect: product scope, code simplicity, architecture
   boundaries, deployment-mechanism preference order.
3. [`docs/repo-map.md`](../docs/repo-map.md) — the dependency graph between
   all nine repos, with a mermaid diagram.
4. [`docs/prd.md`](../docs/prd.md) / [`docs/spec-fonctionnelle.md`](../docs/spec-fonctionnelle.md) /
   [`docs/spec-technique.md`](../docs/spec-technique.md) — why / what /
   how, in that order of increasing detail.

## OpenWiki sections

- [**Architecture**](architecture.md) — `cockpit`'s role in the dependency
  graph, `platform.yml` as an override profile, the `scripts/` inventory and
  how responsibility is split with sibling repos' own scripts.
- [**Workflows**](workflows.md) — the operator bootstrap sequence
  (`make platform-up`, resumable/self-verifying), the application
  onboarding journey, and the full `make` targets reference.
- [**Operations**](operations.md) — security posture (SOPS/age secrets,
  self-signed TLS, bootstrap accounts), the dual-remote Git workflow
  (GitHub source of truth + local GitLab), governance rules, and known
  production gaps.

## What NOT to expect here

This repo has no source code domains (no server, no UI, no database
schema) — it is pure orchestration. There is therefore no `domain/` or
`data-models/` section in this wiki: all "business logic" (CI/CD flow,
promotion gates, environment sequencing) is implemented in the sibling
repos and only referenced here, per the "one repo documents its own
internals" convention already enforced in this workspace (see
[`.agents/skills/poc-devops-docs/SKILL.md`](../.agents/skills/poc-devops-docs/SKILL.md)).

## Conventions to know before changing anything

- **Docs are French**, deliberately (this OpenWiki layer is English for
  consistency with the tool, but always link to and trust the French
  source docs for exact wording/values).
- **Governance rule** (`AGENTS.md`): a product idea needs a backlog entry
  ([`docs/backlog.md`](../docs/backlog.md)) *before* implementation; a fix
  or chore needs one *at commit time* at the latest.
- **Never edit sibling repos from `cockpit`** — always go through their own
  Makefiles.
- **Every commit ends up on GitHub** (`origin`), even if the local GitLab
  remote is unreachable — see [Operations](operations.md#git-workflow).
