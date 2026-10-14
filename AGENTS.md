# Khan Cloud — Codex Development Contract

## 1. Repository Authority

This repository is the active Khan Cloud development worktree.

Repository root:

    /opt/khan-cloud/source

Primary development host:

    khan-mgmt

At the time this contract was installed, the active development branch was:

    feature/kg009-gaming-runtime-orchestrator

and the base HEAD was:

    70260fba00b800bef15916cafde229d9d5e3ceda

IMPORTANT:

The working tree already contains substantial active, intentionally
uncommitted development.

Existing modifications and untracked files MUST be treated as valuable
in-progress work.

Never assume that a dirty worktree was created by Codex.

Before making changes, always inspect:

    git branch --show-current
    git rev-parse HEAD
    git status --short
    git diff --stat
    git diff

Do not require a clean worktree before continuing development.

## 2. Absolute Git Safety Rules

Unless the user explicitly authorizes a specific action, NEVER run:

    git reset
    git reset --hard
    git clean
    git checkout -- .
    git restore .
    git stash
    git rebase
    git merge
    git cherry-pick
    git revert

Do not discard, overwrite, hide, or normalize pre-existing local changes.

Do not switch branches unless explicitly authorized.

Do not amend or rewrite existing commits unless explicitly authorized.

Do not commit automatically.

Do not create tags automatically.

Do not push automatically.

Do not force-push.

A Git commit is a validated checkpoint, not a save button.

The normal development flow is:

    inspect
      -> understand
      -> edit locally
      -> targeted validation
      -> fix
      -> retest
      -> broader regression
      -> runtime validation where applicable
      -> review git diff
      -> checkpoint only when explicitly authorized

When a validated checkpoint is explicitly authorized for closure,
the expected Khan Cloud workflow includes:

    commit
      -> validation tag where applicable
      -> push branch/commit
      -> push validation tag
      -> verify local/remote branch and tag parity

Do not perform those checkpoint-closing actions without authorization.

## 3. Existing Worktree Protection

Pre-existing changes belong to the current Khan Cloud development effort.

When starting a task:

1. Capture current branch, HEAD, and git status.
2. Determine which changes existed before the current Codex task.
3. Preserve unrelated existing modifications.
4. Modify only files necessary for the requested task.
5. Never revert another developer's or previous session's work merely
   because it appears unrelated or incomplete.
6. At completion, clearly identify:
   - files Codex changed,
   - files that were already modified,
   - tests run,
   - tests passed,
   - tests failed or skipped,
   - remaining runtime validation.

If uncertain whether an existing change is intentional, preserve it.

## 4. Anti-Time-Waste Engineering Rule

Before writing executable diagnostic, deployment, migration,
control-plane, Windows, Hyper-V, driver, or production-management code:

1. Inspect the authoritative implementation and interfaces first.
2. Verify actual field names, method signatures, schemas, enum values,
   command-line arguments, paths, and API contracts from repository source
   or authoritative documentation where available.
3. Do not guess schemas, attributes, API signatures, or PowerShell fields.
4. Validate syntax in the correct target environment or with an
   appropriate parser before asking the user to execute it.
5. Consolidate diagnostics where practical so the user is not used as
   a parser/debugger for assistant-generated scripts.
6. Prefer a complete tested script over a sequence of speculative fragments.

## 5. Testing Policy

Do not claim a change is validated merely because the code looks correct.

Use the smallest relevant tests first, then broaden validation.

Typical sequence:

    focused/unit tests
      -> subsystem regression
      -> broader package regression
      -> migration/schema checks where applicable
      -> actual runtime validation where required

Do not silently weaken, delete, skip, or rewrite tests merely to obtain
a passing result.

Do not modify expected results to hide a regression.

If a test fails, investigate the implementation first.

Report exact test commands and final counts.

## 6. Database and Alembic Safety

Never mutate production data merely to test code.

Never run destructive database commands without explicit authorization.

Never drop databases, schemas, tables, columns, or production data.

For Alembic work:

1. inspect current/head revisions first;
2. inspect existing migration history;
3. detect multiple heads;
4. validate upgrade/downgrade logic where appropriate;
5. do not upgrade a production database without explicit authorization.

Do not fabricate migration revision IDs or schema fields.

## 7. Secrets and Credentials

Do not print, copy, commit, or expose:

- passwords
- private keys
- API keys
- access tokens
- refresh tokens
- OAuth credentials
- database passwords
- WireGuard private keys
- service credentials
- node enrollment credentials

Do not add secrets to Git.

Use existing secure configuration mechanisms.

If secret material is encountered, avoid reproducing it in output.

## 8. Infrastructure Mutation Boundary

Source development on khan-mgmt is allowed within the user's task.

The following actions require explicit authorization before execution:

- reboot or shutdown
- kernel activation reboot
- service disruption affecting production
- Docker destructive operations
- production database mutation
- firewall or routing changes
- MikroTik configuration changes
- Proxmox destructive operations
- VM deletion/reset
- Hyper-V destructive operations
- GPU/GPU-P assignment changes
- Windows driver installation/removal
- Driver Store mutation
- Khan VDD deployment/removal
- production agent deployment
- Sunshine destructive configuration changes
- Steam/game destructive changes
- production runtime deployment
- credential rotation

Prefer read-only diagnostics before mutations.

## 9. Gaming Architecture Invariant

Do not collapse the physical Hyper-V host and customer gaming endpoint
into the same logical role.

Authoritative production path:

    khan-mgmt
      -> physical R7425 / KC-01 Hyper-V host
      -> Khan-managed Windows gaming VM
      -> allocated vCPU/RAM/GPU or GPU-P
      -> KhanGaming interactive session
      -> Khan Virtual Display Driver
      -> Steam/game
      -> Sunshine
      -> Moonlight client

The physical host is infrastructure.

The Khan-managed gaming VM is the customer workload boundary unless the
user explicitly changes this architecture.

Host-only success is not sufficient for end-to-end qualification.

## 10. Windows and Gaming Runtime Validation

For Windows/Hyper-V/gaming changes, distinguish:

- source validation on khan-mgmt
- standalone Windows package validation
- KC-01 host validation
- gaming VM validation
- interactive KhanGaming-session validation
- VDD validation
- Sunshine validation
- Moonlight streaming validation

Do not describe an earlier layer as proving later layers.

Avoid unnecessary Windows reboots.

Batch safe checks before a reboot.

Do not change Khan VDD merely to solve Windows session-management problems.

## 11. Presentation / Streaming Recovery

Known Sunshine/Moonlight/GameStream failure states must ultimately support
production self-healing rather than depending on manual restart.

Recovery architecture should follow:

    detect
      -> classify
      -> controlled recovery
      -> verify endpoint/session health
      -> bounded retry/backoff
      -> audit event
      -> fail safely/escalate if recovery fails

A running Sunshine process alone does not prove streaming readiness.

## 12. Current Development Continuity

The current worktree contains ongoing KG-009 / Q38-series gaming runtime,
Windows presentation, process ownership, launch/recovery, and related work.

Do not restart this implementation from a clean baseline merely because
Codex is newly installed.

Continue from the actual local state after inspecting it.

Recent Windows candidate qualification evidence may exist outside Git.
Runtime qualification results are evidence, not automatically Git state.

## 13. Code Quality

Prefer production-ready integrated changes over parallel temporary systems.

Reuse/refactor existing Khan Cloud mechanisms where appropriate.

Avoid introducing duplicate authorities, duplicate ledgers, duplicate
runtime ownership systems, or competing orchestration paths.

Maintain backward compatibility intentionally, not accidentally.

Add tests for newly introduced invariants and failure modes.

## 14. Task Completion Report

Before declaring a coding task complete, report:

    branch
    HEAD
    git status summary
    files changed by this task
    targeted tests
    broader regression tests
    runtime tests
    migrations/schema status if relevant
    unresolved issues
    whether commit/tag/push occurred

Never claim a runtime layer was tested if it was not actually exercised.

