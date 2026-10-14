# Khan Cloud durable development handoff

Updated: 2026-09-11 UTC

This is local continuity evidence, not a Git checkpoint. Keep it untracked and
never store credentials or secret material here. At every resume, read root
`AGENTS.md`, read this file, inspect current Git status/diff, and reconcile this
record against the authoritative dirty worktree before continuing.

## Repository authority

- Repository: `/opt/khan-cloud/source`
- Branch: `feature/kg009-gaming-runtime-orchestrator`
- HEAD: `70260fba00b800bef15916cafde229d9d5e3ceda`
- Warning: the dirty worktree is authoritative, valuable in-progress KG-009/Q38
  work. Do not clean, reset, restore, stash, rebase, switch branches, or discard
  changes.
- Q38IU-XR baseline status: 16 modified tracked files, 16 untracked source/development
  files, no staged files; tracked diff 3,580 insertions and 106 deletions.
- Q38IU-XR source changes: NONE. Its only repository write is this authorized
  untracked handoff. Its temporary operator guard is under `/tmp`.

Current modified tracked files:

- `khan-virtual-display/consumer/KhanFrameConsumer/KhanFrameConsumer.cpp`
- `khan-virtual-display/driver/KhanVirtualDisplay/Driver.cpp`
- `node-agent/deploy/apply-runtime-update.ps1`
- `node-agent/deploy/install-runtime.ps1`
- `node-agent/deploy/universal-bootstrap.ps1`
- `node-agent/khan_agent/gaming_launchers.py`
- `node-agent/khan_agent/gaming_runtime.py`
- `node-agent/khan_agent/runtime_ownership.py`
- `node-agent/khan_agent/windows_session_broker.py`
- `node-agent/requirements.txt`
- `node-agent/tests/test_gaming_runtime_execution_v1.py`
- `node-agent/tests/test_runtime_ownership_kg009d1.py`
- `node-agent/tests/test_windows_installer_transaction_kg009d3.py`
- `node-agent/tests/test_windows_python_single_owner_v1.py`
- `node-agent/tests/test_windows_session_broker_kg009d2.py`
- `node-agent/tests/test_windows_session_integration_kg009d2.py`

Current untracked development files before this handoff:

- `AGENTS.md`
- `node-agent/khan_agent/windows_presentation.py`
- `node-agent/khan_agent/windows_verified_process.py`
- `node-agent/tests/test_late_steam_launch_authority_q38it.py`
- `node-agent/tests/test_launch_recovery_lifecycle_q38iu.py`
- `node-agent/tests/test_pending_launch_sanitation_q38iu.py`
- `node-agent/tests/test_presentation_startup_probe_q38iu.py`
- `node-agent/tests/test_steam_async_observation_q38ir.py`
- `node-agent/tests/test_steam_broker_request_q38dt.py`
- `node-agent/tests/test_windows_brokered_ownership_q38df.py`
- `node-agent/tests/test_windows_presentation_kg009e.py`
- `node-agent/tests/test_windows_runtime_commit_boundary_q38fj.py`
- `node-agent/tests/test_windows_runtime_dependencies_q38fc.py`
- `node-agent/tests/test_windows_runtime_quiescence_q38dy.py`
- `node-agent/tests/test_windows_runtime_rollback_generation_q38fu.py`
- `node-agent/tests/test_windows_verified_process_exit_q38fp.py`

## Q38IU-S / Q38IU-U

- Objective: remove temporary Q38AL presentation startup-probe leakage and
  qualify the repaired Windows candidate.
- Result: PASS.
- Proven: Q38IU-S removed temporary exit 91/startup-probe behavior; Q38IU-U
  qualified the repaired candidate on Windows.
- Current source proof: `node-agent/khan_agent/windows_presentation.py` contains
  the real helper path and no startup-probe/`return 91`; focused coverage is in
  `node-agent/tests/test_presentation_startup_probe_q38iu.py`.
- Exact historical focused commands/counts were not recovered. Do not rerun
  Windows qualification merely to reconstruct conversational output.

## Q38IU-W production deployment

- Objective: transactionally deploy the repaired presentation path.
- Result: PASS.
- Deployment: `BOOTSTRAP_RC=0`; real presentation path deployed; Q38AL
  startup-probe short-circuit absent; KhanCloudAgent Running afterward.
- Packaged qualification: 508 passed, 2 skipped, 2 deselected.
- Deployed/current `windows_presentation.py` SHA256:
  `A4D655D999008DE0C13317DCB95D9A35983120D01A0EEB698E74E8FF42DECE7A`.
- Runtime evidence: Sunshine PID 9812 preserved; Steam PID 19104 preserved;
  `CS2_COUNT_AFTER=0`; configuration preserved; heartbeat HTTP 200;
  runtime ownership reconciliation emitted `state="verified"`; jobs/next 204.
- Production mutation: YES, transactional agent deployment only.
- Database/job mutation: NO. Reboot: NO.
- Proven: the repaired package is deployed and the agent/streaming prerequisites
  remained healthy. Not proven: a new post-deployment canonical START, live CS2,
  customer presentation, or Moonlight streaming.
- Do not repeat Q38IU-W, package qualification, or Windows qualification solely
  to recreate evidence.

## Q38IU-X / Q38IU-XR lifecycle recovery

- Objective: recover current commercial-session lifecycle authority and decide
  the next legal canonical action without production mutation.
- Result: PASS.
- Classification: `START_ELIGIBLE`.
- Commercial GamingSession: `59f0874e-69c6-4e59-bb46-1bb18e104375`.
- Runtime: `kc-gaming-59f0874e-69c6-4e59-bb46-1bb18e104375`.
- Node: `ae52e6cb-4cc9-4797-afcc-4f92042b1b90`.
- Guest node: null. Deployment mode: `bare_metal`.
- Durable state: status `error`; desired_state `running`; deployment_stage
  `stopped`; connection_info `{}`; started_at
  `2026-09-06T11:35:56.325307+00:00`; ended_at null.
- Failure: category `node_job_failed`; message
  `Customer game presentation was not verified on Khan VDD before stream readiness: Presentation helper failed with exit code 91.`
- Runtime health: failure_count 0; last_checked_at
  `2026-09-07T21:23:10.800120+00:00`; last_failure_at null; recovery_count 0.
- Sanitation: state empty string; attempt_count 0; last_checked_at null;
  sanitized_at null.
- Quarantine: reason/state/source/message empty strings; attempt_count 0;
  requested_at/last_attempt_at/recovered_at null; evidence `{}`.
- Billing: billing_finalized_at null; billing_stop_reason empty string;
  last_metered_at null; price 117 minor units/minute; admission reserve 585.
- UsageReservation ID:
  `bc02acda-0a33-4bba-9247-5413f6a28595`, loaded directly through the current
  `UsageReservation` model. Status `reserved`; reserved 585; consumed 0;
  released 0; remaining 585 PKR minor units. The authoritative minimum is
  `METERED_MINIMUM_START_MINUTES=5`, so required coverage is exactly 585.
- NodeJobs: total 23; START 13; STOP 7; DELETE 0; in-flight 0.
- Last canonical START: `7c89aec3-f69a-4327-a2af-b77136287666`, type
  `gaming.session.start`, status `blocked`, attempt_count 1, result `{}`;
  created `2026-09-09T20:35:00.461827+00:00`, claimed
  `2026-09-09T20:35:16.660591+00:00`, completed
  `2026-09-09T20:35:26.691392+00:00`, updated
  `2026-09-09T20:35:26.687116+00:00`; error is the exit-91 message above.
- Jobs after last START: none. Later STOP/DELETE count: 0.

### Source-backed lifecycle meaning

- Backend START admission is `queue_gaming_action` in
  `backend/app/services/gaming_service.py`: supported action, session not in
  terminal `{terminated, failed}`, no pending/running NodeJob, and assigned
  node. It calls `reopen_gaming_billing`, sets desired_state `running`, sets
  status `starting`, and queues one deployment-specific START job.
- `reopen_gaming_billing` in
  `backend/app/services/gaming_billing_service.py` does not block on prior
  finalization. When billing is finalized it creates a new reservation; when it
  is not finalized it ensures coverage. Current billing is open and has exactly
  the required five-minute coverage.
- Backend STOP is not a prerequisite for this state. It changes desired_state to
  `stopped`, prepares connection shutdown, and queues STOP when ready. The agent
  requires STOP/DELETE only for `launch_recovery_pending` or `cleanup_required`.
- The prior presentation failure occurred after a new ownership boundary was
  returned. The readiness exception path in
  `node-agent/khan_agent/gaming_runtime.py` called `_cleanup_failed_launch`;
  verified termination persisted status/runtime_stage `stopped`, a clean
  terminated ownership proof with zero remaining processes, and removed
  launch/readiness authority. D1 ownership was retired, not retained live.
- `reconcile_runtime_ownership` first handles pending launch and cleanup states,
  then verifies the structural ownership descriptor. A running/starting state
  with zero owned processes becomes `workload_retired`; cleanup failures remain
  `cleanup_required`; a surviving starting workload becomes
  `readiness_pending`. A clean stopped terminal proof falls through to
  `runtime_reconciliation.state="verified"`.
- Therefore Q38IU-W's `verified` means the stopped ownership descriptor was
  successfully inspected and found structurally consistent. It does not assert
  a live game process. `CS2_COUNT=0` is expected for that stopped state.
- No unresolved launch-recovery, cleanup, sanitation, quarantine, STOP, or
  DELETE authority remains. Current DB admission permits START.
- Source defect found by Q38IU-XR: NONE.
- Tests rerun by Q38IU-XR: NONE_REQUIRED_FOR_READ_ONLY_RECOVERY.

### Operator guards

- Original `/tmp/q38iu_x_guarded_start.py`: 2,585 bytes; SHA256
  `7CFE...` (full: `7CFEDF6BB918F8A5894E3CB7C91A081B9A9F7FADA7DA905FC5ED180B86D21DE6`).
  Its read-only invocation passed, but it is insufficient for execution because
  it does not pin all identity, billing, quarantine, and job-history evidence.
- Corrected `/tmp/q38iu_xr_guarded_start.py`: 7,088 bytes; SHA256
  `7E17B7228DA21839FA65669A44E3E0069E7369A529B8D60A57C6C25DC320561E`.
  It pins the exact current ORM representations, reservation identity/coverage,
  node/runtime/deployment identity, last failure, exact job counts, no jobs
  after LAST_START_ID, and zero in-flight jobs.
- Corrected dry-run result: PASS — `guard passed; dry-run, no job queued`.
- Final read-only verification after dry-run: status `error`, desired `running`,
  deployment `stopped`, total jobs 23, in-flight 0, jobs after last START 0.

## Q38IU-XR closed next gate

- The then-authorized controlled production action was:
  run exactly once:
  `PYTHONPATH=/opt/khan-cloud/source/backend /opt/khan-cloud/source/backend/.venv/bin/python /tmp/q38iu_xr_guarded_start.py --execute`
- Expected mutation: exactly one canonical `gaming.session.start` NodeJob. Then
  observe that job and validate the real Windows gaming VM/customer path: new
  ownership boundary, CS2 live, Khan VDD presentation, Sunshine readiness, and
  Moonlight streaming as applicable.
- Do not execute the older guard. Do not perform a preliminary STOP or DELETE;
  neither is required by the current lifecycle state.
- Current blocker: explicit authorization for the production START mutation.
- Until authorized: do not queue START/STOP/DELETE, mutate the database, touch
  KC-01, deploy, reboot, control production services/processes, modify VDD,
  Sunshine, or Steam, or commit/tag/push.

## Mutation ledger for Q38IU-XR

- Production mutation: NO.
- Database mutation: NO.
- Job queued: NO.
- KC-01 touched: NO.
- Source files changed: NONE.
- Git history/index mutation: NO.
- Local artifacts created: `/tmp/q38iu_xr_guarded_start.py` and this authorized
  untracked continuity handoff.

## Q38IU-Y guarded canonical START and raw production E2E

- Objective: execute exactly one guarded canonical START and prove the repaired
  real `windows_native` raw gaming/presentation path through stream readiness.
- Result: BLOCKED at the CS2 presentation window-discovery gate. Stream readiness
  and Moonlight acceptance were not reached.
- Guard boundary: `/tmp/q38iu_xr_guarded_start.py` existed at exactly 7,088 bytes
  with SHA256
  `7E17B7228DA21839FA65669A44E3E0069E7369A529B8D60A57C6C25DC320561E`.
  Its immediately preceding dry-run returned
  `guard passed; dry-run, no job queued`.
- Authorized production mutation executed exactly once:
  `PYTHONPATH=/opt/khan-cloud/source/backend /opt/khan-cloud/source/backend/.venv/bin/python /tmp/q38iu_xr_guarded_start.py --execute`.
  Output: `exactly one canonical START queued`.
- New canonical START NodeJob:
  `ba5e180e-7973-4b28-856c-555545894e3b`.
  Type `gaming.session.start`; status `blocked`; attempt_count 1; result `{}`;
  created `2026-09-09T22:50:22.514590+00:00`; claimed
  `2026-09-09T22:50:36.711061+00:00`; completed
  `2026-09-09T22:53:25.567759+00:00`; updated
  `2026-09-09T22:53:25.562527+00:00`.
- Exact job error:
  `Customer game presentation was not verified on Khan VDD before stream readiness: No visible game window appeared before timeout.`
- Uniqueness proof: total jobs 23 -> 24; START jobs 13 -> 14; STOP jobs
  remain 7; DELETE jobs remain 0; the new ID occurs exactly once; jobs after
  the new START 0; in-flight jobs 0. No duplicate START was created.
- Final GamingSession DB state: session
  `59f0874e-69c6-4e59-bb46-1bb18e104375`; runtime
  `kc-gaming-59f0874e-69c6-4e59-bb46-1bb18e104375`; node
  `ae52e6cb-4cc9-4797-afcc-4f92042b1b90`; status `error`;
  desired_state `running`; deployment_stage `stopped`; failure_category
  `node_job_failed`; connection_info `{}`. Billing remains open:
  billing_finalized_at null, billing_stop_reason empty string, last_metered_at
  null.

### Q38IU-Y runtime and presentation evidence

- Control-plane evidence: the assigned Windows node claimed the one job, posted
  its blocked result, then resumed heartbeat/desired-state polling and received
  jobs/next 204. No manually manufactured success or database row was used.
- Assigned endpoint identity remained `DESKTOP-4ROCVUH` / node name
  `KC-GAME-7CN69R2-01`. KhanCloudAgent remained Running.
- Managed interactive authority was KhanGaming Session 1, broker mode
  `managed_autologon`, source `managed_console`, validated true. No password was
  read/reset/revealed and no manual login occurred.
- Steam broker/AppID evidence: Steam launched AppID 730. Steam
  `gameprocess_log.txt` recorded PID 24216 at the exact executable
  `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe`
  with `-steam`; the overlay log independently recorded `cs2.exe`, PID 24216,
  GameID 730 and OverlayGameID 730. Current installed build authority is
  BuildID 25218825.
- New D1 boundary: the durable pre-process authority was
  `steam_verified_process_launch_attempt`, attempt
  `f7c54953-6027-475d-abcf-32e3329e5f82`, with an empty pre-launch baseline,
  exact AppID/install root, runtime, and expected Session 1. The current source
  can invoke presentation only after `launch_prepared_game` returns the new
  filtered `windows_verified_process` ownership. Helper observation of PID
  24216 therefore proves the new START crossed that ownership boundary.
- Real deployed presentation helper executed under the agent runtime Python.
  Q38AL startup-probe/exit-91 behavior did not occur.
- Dynamic VDD discovery selected `\\.\DISPLAY6`, monitor handle 131073, bounds
  `(1024, 0)-(2944, 1080)` (1920x1080).
- The helper repeatedly found game PID 24216 for its full presentation timeout.
  `_game_pids` filters by the exact CS2 install root and expected Session 1, so
  this is process/root/session proof.
- Failure layer: no visible, unowned, top-level window at least 64x64 appeared
  for PID 24216 before timeout. The helper returned its no-window failure
  (exit 21), which propagated as the exact NodeJob error. Because no candidate
  HWND was discovered, `SetWindowPos` and `MonitorFromWindow` verification were
  never reached. Presentation result: FAIL.
- Steam overlay logging during the attempt showed CEF paint-event creation error
  2, shell32 loading failure, and later hook-mutex wait failures. These are
  correlated evidence, not yet proof of the primary cause of the missing CS2
  top-level window.
- No new CS2 dump was created. The only Steam dump files predate this attempt
  (2026-09-06). Windows Application-event filtering returned no matching crash
  record for the attempt.
- Automatic failed-readiness cleanup retired the new boundary. Steam logged PID
  24216 no longer tracked with exit code 1 after the cleanup. Final production
  runtime state is status/runtime_stage `stopped`, ownership type `terminated`,
  boundary_verified true, termination_verified true, clean true, zero remaining
  processes, reconciliation state `verified`, and no `launch_info`.
- Final processes: CS2 count 0; persistent Steam PID 19104 Session 1 preserved;
  persistent Sunshine PID 9812 Session 1 preserved. Sunshine was not restarted
  or reconfigured. Stream readiness was not reached, so no connection info or
  Moonlight acceptance exists.

### Q38IU-Y source defect and local repair

- Concrete secondary defect discovered: the verified restart-readiness cleanup
  in `node-agent/khan_agent/gaming_runtime.py` removed live launch/readiness
  state but failed to remove `launch_attempt`, `launch_failure`, and
  `pre_launch_runtime_ownership`. Production therefore still has the stale
  attempt `f7c54953-6027-475d-abcf-32e3329e5f82` despite a clean terminated
  proof. This defect did not cause the no-visible-window presentation failure.
- Smallest local repair: when failed-readiness cleanup is verified, pop those
  three temporary authority fields alongside `launch_info`,
  `readiness_failure`, and `cleanup`.
- Regression update: the existing
  `test_d1_failed_restart_readiness_persists_terminal_cleanup_proof` now asserts
  that all three temporary fields are absent after verified cleanup.
- Q38IU-Y source files changed:
  `node-agent/khan_agent/gaming_runtime.py` (12 added lines) and
  `node-agent/tests/test_runtime_ownership_kg009d1.py` (3 added assertions).
  Both files were already modified by the broader authoritative KG-009/Q38
  work; preserve their entire existing diffs.
- Current file SHA256 values after local repair:
  `gaming_runtime.py` =
  `0E008111A3D925CE8E18E9B26CFC147188679B5503FC00F0DEC027469864FE18`;
  `test_runtime_ownership_kg009d1.py` =
  `72D2C8BA81D95083EE2030A8FB33028DE3B3C963B1D9A0BFEC60B486482584BB`.
- Focused repair test:
  `node-agent/.venv/bin/python -m pytest -q node-agent/tests/test_runtime_ownership_kg009d1.py::test_d1_failed_restart_readiness_persists_terminal_cleanup_proof`
  -> 1 passed.
- Focused subsystem regression, run from `node-agent`:
  `.venv/bin/python -m pytest -q tests/test_runtime_ownership_kg009d1.py tests/test_launch_recovery_lifecycle_q38iu.py tests/test_pending_launch_sanitation_q38iu.py tests/test_presentation_startup_probe_q38iu.py`
  -> 57 passed.
- One earlier invocation of that same group from the repository root produced
  55 passed and 2 failed because two source-contract tests require the
  `node-agent` working directory. The corrected invocation above passed all 57;
  this was not an implementation failure.
- Broader node-agent regression, run from `node-agent`:
  `.venv/bin/python -m pytest -q` -> 511 passed, 1 skipped.
- `git diff --check` for both repair files: PASS.
- The local cleanup repair is not deployed. No production package was built or
  deployed in Q38IU-Y.

## Current next gate after Q38IU-Y

- Classification: `PRESENTATION_BLOCKED_NO_VISIBLE_CS2_WINDOW`.
- Do not run another START. Do not queue STOP/DELETE: production already has a
  verified clean terminated boundary, zero CS2, and zero in-flight jobs.
- The next controlled development gate is to determine and repair/qualify why
  the valid Session-1 CS2 process never creates an eligible visible top-level
  window. Preserve the overlay errors and exact helper evidence as the starting
  point. Any future production retry requires a separately reviewed and
  authorized package/deployment plan; it must also include or intentionally
  account for the tested stale-launch-authority cleanup repair.
- Moonlight visual/input testing is not yet applicable because presentation and
  stream readiness were not achieved.
- After a future successful stream-ready gate and user Moonlight acceptance,
  the planned subsequent lifecycle gate remains `Q38IU-Z — CANONICAL STOP +
  TERMINATION + METERING + SANITATION + REPOOL`.
- Do not repeat Q38IU-W, package qualification, Windows qualification, Q38IU-XR
  reconstruction, or this Q38IU-Y START merely to reconstruct evidence.

## Mutation ledger for Q38IU-Y

- Production/control-plane mutation: YES — exactly one explicitly authorized
  canonical START NodeJob, and only its normal session/job lifecycle updates.
- Database mutation: YES — canonical `queue_gaming_action`/agent result updates;
  no manual SQL/ORM row mutation.
- Job queued: YES — exactly one START
  `ba5e180e-7973-4b28-856c-555545894e3b`; no STOP/DELETE and no duplicate START.
- Production process mutation: YES — the authorized agent job launched and then
  automatically cleaned up CS2 PID 24216. No manual game/process/service action.
- KC-01/operator action: read-only SSH/log/process inspection only; no service,
  process, VM, Hyper-V, VDD, Sunshine, Steam, network, or reboot control.
- Source files changed locally: the two cleanup repair/test files listed above.
- Deployment: NO. Reboot: NO. Manual game launch: NO. Manual window movement: NO.
- Git history/index mutation: NO. No commit, tag, push, reset, clean, restore,
  checkout/switch, stash, rebase, or staged files.
- Current Git status remains 16 modified tracked files; tracked diff 3,595
  insertions and 106 deletions; `.codex/`, `AGENTS.md`, and 15 source/test files
  are untracked. The dirty worktree remains authoritative and uncommitted.

## Session pause — 2026-09-09 UTC

- Q38IU-Y is closed at `PRESENTATION_BLOCKED_NO_VISIBLE_CS2_WINDOW`.
- Work is saved locally and remains deliberately uncommitted.
- Resume from `Current next gate after Q38IU-Y`; do not repeat the guarded START,
  Q38IU-W deployment/qualification, or Q38IU-XR reconstruction.
- First resume checks: read `AGENTS.md`, read this handoff, inspect Git
  status/diff, and reconcile the recorded state with the authoritative worktree.
- No commit, tag, push, deployment, START, STOP, or DELETE is authorized by this
  pause instruction.



## SSH-reset recovery and desktop-affinity gate — 2026-09-10 UTC

- Patch-integrity result: the malformed patch applied zero hunks to the live
  authoritative untracked `node-agent/khan_agent/windows_presentation.py`.
  The live file and patch-created `.orig` were byte-identical at 18,503 bytes
  with SHA256
  `A04CF6C16048B130263391FD48E5F7B1003E70ADD4E484F3E928D5A46F78FCF7`.
  None of `WINDOW_PROBE`, `helper_loop_started`, or `window_probe_process`
  occurred in the live file. The `.rej` contained the entire rejected large
  probe hunk; no attempted hunk was present in the live file.
- Failed-attempt artifacts removed after audit:
  `windows_presentation.py.orig`, `windows_presentation.py.rej`, and the
  incomplete untracked `windows_presentation_probe.py`. No legitimate Q38
  presentation content was removed; `windows_presentation.py` was not edited.
- Exact direct CreateProcessAsUser boundary: both the transient
  `steam.exe -applaunch 730` request and the Python presentation helper call
  `windows_interactive.launch_in_active_session`. CS2 itself is not directly
  created by this call; the existing Steam client launches it after receiving
  the broker request.
- Pre-repair STARTUPINFO was pywin32-zero-initialized and set only
  `STARTF_USESHOWWINDOW` plus `SW_SHOWNORMAL`; `lpDesktop` remained null.
  `WTSQueryUserToken(Session 1)` and `DuplicateTokenEx` established user/token
  and session affinity, but source neither selected `winsta0\default` nor
  changed or verified its ACL. Therefore the path did not guarantee the
  interactive window station/default desktop.
- Microsoft semantics reviewed: CreateProcessAsUser requires explicit
  `winsta0\default` for an interactive process; null `lpDesktop` inherits the
  parent process window station and desktop. A desktop owns its window objects,
  so helper-context EnumWindows cannot prove windows on another desktop.
- A-F classification from existing evidence: C is the strongest source-backed
  lead but is not historical runtime proof. A/B remain unruled-out because the
  old helper silently rejected invisible, owned, and sub-64x64 windows and did
  not report cloak/tool style. D/E remain possible. F is weakened by repeated
  PID observation and 400-ms polling for the full 75-second timeout.
- Coherent local repair: `node-agent/khan_agent/windows_interactive.py` now sets
  `startup.lpDesktop = r"winsta0\default"` before CreateProcessAsUser. This
  applies to both direct launch paths. It does not assert or force the desktop
  used by CS2 when the existing Steam process creates it.
- Focused invariant coverage added in
  `node-agent/tests/test_interactive_runtime_execution_kg009d3.py`.
- Focused validation from `node-agent`:
  `.venv/bin/python -m pytest -q tests/test_windows_interactive_kg002.py tests/test_windows_interactive_fail_closed_kg009d3.py tests/test_interactive_runtime_execution_kg009d3.py tests/test_windows_presentation_kg009e.py tests/test_presentation_startup_probe_q38iu.py`
  -> 30 passed.
- No full regression was run. No Windows/runtime qualification was run. The
  repair is not deployed; no production START, database/job mutation, KC-01
  control mutation, Sunshine/Steam/VDD change, reboot, Hyper-V work, commit,
  tag, or push occurred.

## Current next gate after desktop-affinity repair

- Review/package/standalone-Windows qualification and any production deployment
  require separate authorization. A future authorized canonical START must
  verify the helper is on `WinSta0\Default`, establish CS2 desktop affinity,
  and retain bounded HWND evidence sufficient to separate A/B/C/D/E/F before
  claiming the no-window root cause closed.
- The earlier Q38IU-Y stale launch-authority cleanup repair remains local and
  must be included or intentionally accounted for in any future candidate.


## E2E-first and future lifecycle architecture - recorded 2026-09-10 UTC

### Priority and sequencing

- Immediate priority is one complete real RAW E2E path in the current
  `windows_native` Mode A implementation:
  control plane -> canonical START -> KhanCloudAgent -> managed KhanGaming
  session -> Steam -> game process -> verified ownership -> game window ->
  Khan VDD presentation -> Sunshine -> Moonlight -> visible game -> keyboard
  and mouse input -> metering evidence -> canonical STOP -> cleanup ->
  sanitation -> repool.
- Do not implement the generalized recovery state machine or multimode backend
  abstraction before this E2E path succeeds unless the current blocker requires
  a small compatibility-preserving change.
- Current execution order remains: qualify the local desktop-affinity repair;
  prepare a controlled transactional deployment if qualified; obtain separate
  authorization for exactly one canonical START; capture bounded HWND,
  desktop, and window-state evidence; reach VDD and Sunshine readiness; obtain
  real Moonlight visual/input acceptance; then canonical STOP, cleanup,
  sanitation, and repool.
- Reuse authoritative Q38 evidence. Do not rerun completed broad qualification,
  broaden into billing/accounting, or redesign orchestration during this gate.

### Required future lifecycle meanings

- START: fresh allocation with no Khan-owned game workload for that allocation;
  establish a new launch and ownership boundary.
- RECOVER: a valid customer workload still exists; preserve the game whenever
  possible and recover only the failed layer, including client/network,
  Sunshine/GameStream, VDD/presentation, input, or another recoverable
  dependency.
- RELAUNCH: the allocation and customer session remain valid but the game
  workload is gone or unrecoverable; safely retire old ownership and establish
  a new game ownership boundary for the same allocation.
- STOP: intentional workload termination.
- SANITIZE/REPOOL: verify owned processes terminated, clean runtime state, clear
  customer authority, and return capacity to the scheduler.
- Intended common upper lifecycle states are STARTING, PLAYABLE, DEGRADED,
  RECOVERING, RELAUNCHING, STOPPING, SANITIZING, and READY.

### Fresh-allocation and ownership invariants

- A fresh unallocated runtime has no active Khan-owned game ownership for the
  allocation, no incompatible in-flight lifecycle command for the same
  allocation/runtime, and no unresolved launch-recovery or cleanup authority.
- Persistent Steam and Sunshine may remain running, and VDD may remain
  installed and healthy. A canonical START establishes fresh workload
  ownership; those persistent prerequisites are not game ownership.
- Process name alone is never workload authority. Runtime identity continues to
  require allocation/session identity, runtime identity, verified PID and
  process-creation identity, Windows Session ID, authorized executable/install
  root, launch-attempt or ownership proof, and lifecycle state.
- A host/operator process or another user process must never be captured,
  terminated, billed, presented, or treated as Khan-owned merely because its
  executable name matches.
- The in-flight rule is not zero jobs globally. Reject only an incompatible
  in-flight lifecycle command for the same allocation/runtime: duplicate START,
  START during STOP, or independent RELAUNCH during RECOVER are incompatible.
  A compatible health observation may coexist when its source contract allows.

### Mode-independent boundary and capacity policy

- The future conceptual boundary is a common `GamingRuntimeOrchestrator` over
  a `RuntimeBackend`, with `WindowsNativeBackend` and
  `HyperVWindowsBackend` implementations. Keep upper lifecycle semantics
  mode-independent where practical; allocation, interactive session, GPU or
  GPU-P, VDD, Steam, Sunshine, ownership, sanitation, and VM lifecycle may be
  backend-specific.
- Until architecture is explicitly changed, Mode A `windows_native` capacity
  is exactly one active Khan Cloud gaming allocation. Never assign a second
  customer workload to an occupied Mode-A runtime.
- Future Mode B `hyperv_windows_vm` may support multiple isolated allocations,
  such as one gaming VM per customer/session, subject to GPU-P/resource
  admission and streaming capacity.
- Evaluate and implement generalized START/RECOVER/RELAUNCH/multimode behavior
  only after the current production E2E path has succeeded.


## Q38IU-Y1 Windows/package qualification — partial gate 2026-09-10 UTC

- Source authority: branch `feature/kg009-gaming-runtime-orchestrator`, HEAD
  `70260fba00b800bef15916cafde229d9d5e3ceda`, no staged files. The repair
  occurs exactly once at `windows_interactive.py:178` as
  `startup.lpDesktop = r"winsta0\default"`; its invariant test is present.
  No failed-patch markers, `.rej`, `.orig`, or incomplete probe artifacts
  remain. Authoritative `windows_presentation.py` is unchanged at 18,503
  bytes, SHA256
  `a04cf6c16048b130263391fd48e5f7b1003e70add4e484f3e928d5a46f78fcf7`.
- Contract review: managed-session discovery, WTS token acquisition,
  DuplicateTokenEx, environment/profile creation/destruction, command/working
  directory, CreateProcessAsUser flags, optional Job Object ownership,
  fail-closed cleanup, and handle/token closing are unchanged. Direct callers
  remain the Steam broker request and presentation helper. CS2 remains an
  indirect child of persistent Steam.
- Immutable candidate:
  `/tmp/khan-node-agent-q38iu-y1-windows-candidate.tar.gz`, SHA256
  `45425755c7dfbc888e1d755fa2f349b97ccc06fffc3c3d59ec8deb797c06ba2a`,
  170,460 bytes. Manifest sanitation and complete source/package parity passed.
  Critical hashes matched locally, in the extracted package, and on Windows:
  `windows_interactive.py`
  `dc622f9a7c5ce9235f887e67a563fd3e2148df57c77534c5c529985cb220a335`,
  `windows_presentation.py`
  `a04cf6c16048b130263391fd48e5f7b1003e70add4e484f3e928d5a46f78fcf7`,
  `gaming_runtime.py`
  `0e008111a3d925ce8e18e9b26cfc147188679b5503fc00f0dec027469864fe18`.
- The exact package was transferred but not deployed. Windows hash/size matched;
  extraction was isolated at
  `C:\Users\LAPTECH PK\Desktop\cloud Software\q38iu-y1-qual-45425755`,
  outside the production agent runtime. Windows Python 3.12.10 compile/import,
  candidate-path module authority, pywin32, and psutil 7.2.2 passed. A first
  report-formatting command had a quoting-only NameError after compile and was
  corrected without source/runtime changes.
- Focused isolated Windows matrix -> **31 passed** in 5.68 seconds. It covered
  windows_interactive, fail-closed and runtime interactive execution,
  presentation/startup probe, and the stale-launch cleanup regression.
- Deployment-contract isolated Windows package regression ran exactly once:
  `pytest -q -m "not source_tree_only"` -> **509 passed, 2 skipped,
  2 deselected** in 98.28 seconds.
- Audited local-only probes (not transferred or executed):
  `/tmp/q38iu_y1_desktop_child.py` SHA256
  `85bb8e512d59833e9c9cd8c407a6b10cd6b34195af46914b88fd2aae4ca54c62`;
  `/tmp/q38iu_y1_desktop_parent.py` SHA256
  `1bf70f3f54630b2e6091a3f180d9cb04121751572176c18fdc8d49733a28dbe4`.
  Both compile locally. The child has explicit 64-bit-safe ctypes prototypes
  for all five APIs and treats GetUserObjectInformationW sizes as bytes. The
  parent declares and forwards all ten CreateProcessAsUser arguments unchanged
  to exactly one original call, restores the monkeypatch in inner/outer finally
  blocks, and limits cleanup to the returned PID after matching creation time.
  AST validation passed: one original call, ten forwarded arguments.
- Per the user hold, the harmless actual launch probe was not transferred or
  run. Actual-call `lpDesktop`, Session 1, and `WinSta0\Default` evidence
  remain unproven. Q38IU-Y1 is BLOCKED at this explicit execution hold and the
  candidate is not deployment-eligible yet.
- No production START/STOP/DELETE, database/job mutation, deployment/runtime
  write, CS2 action, persistent Steam/Sunshine/VDD change, reboot,
  Hyper-V/networking work, commit, tag, or push occurred.


## Q38IU-Y1B read-only scheduled-probe forensics — 2026-09-10 UTC

- Result: `DIAGNOSED_PRE_CREATEPROCESS_ARGUMENT_QUOTING_FAILURE`.
- Existing task `KhanCloud-Q38IU-Y1A-45425755` was inspected only and was not
  rerun or changed. It remained `Ready`; `LastTaskResult=1` (`0x1`) and
  `LastRunTime=2026-09-10T11:56:05.0000000Z`.
- The task action runs the production runtime venv interpreter as `SYSTEM`, with
  working directory
  `C:\Users\Public\Documents\KhanCloud-Q38IU-Y1A-45425755`. Its argument
  string does not quote the candidate root
  `C:\Users\LAPTECH PK\Desktop\cloud Software\q38iu-y1-qual-45425755`.
  Windows argument tokenization therefore supplied `C:\Users\LAPTECH` as
  `sys.argv[1]`, rather than the full candidate root; the following space-
  separated fragments shifted every subsequent positional argument.
- The parent inserts resolved `sys.argv[1]` into `sys.path` and then imports
  `khan_agent` at line 18, before entering `main()`. Read-only deployed-runtime
  inspection established that the venv has no `khan_agent` package, no
  project-path `.pth` (only `pywin32.pth`), no `easy-install.pth`, no Machine
  or SYSTEM-user `PYTHONPATH`, and `include-system-site-packages = false`.
  The probe working directory contains no `khan_agent` package. The earliest
  failure is therefore the parent module import at line 18:
  `ModuleNotFoundError: No module named 'khan_agent'`.
- The exception was not captured to a file: recursive artifact inspection found
  exactly the two transferred scripts and no parent result, child result,
  stdout, stderr, traceback, or log artifact. The exact exception text above is
  reconstructed from the deterministic argument/module-resolution boundary,
  not quoted from a retained stderr artifact.
- Remote script hashes matched the audited originals:
  child `85BB8E512D59833E9C9CD8C407A6B10CD6B34195AF46914B88FD2AAE4CA54C62`;
  parent `1BF70F3F54630B2E6091A3F180D9CB04121751572176C18FDC8D49733A28DBE4`.
- Because import failed before `main()`, managed-session broker discovery was
  not reached, the CreateProcessAsUser interception/call was not reached, and
  no child was created. Consequently `lpDesktop`, broker session, child
  session, window station, and desktop were not observed.
- No matching Python probe process remained at final inspection. The earlier
  broad process query matched only its own `cmd.exe`/`powershell.exe`; the
  corrected Python-only query and final snapshot returned an empty set.
- Task Scheduler Operational history was disabled and contained no records.
  Security process-creation auditing was disabled, there were no matching 4688
  events in the exact two-minute run window, and no Sysmon log was installed.
  These absences are not being used to infer that the SSH disconnect caused the
  task failure.
- Smallest later one-shot correction, not applied: change only the scheduled
  action's argument quoting so the full candidate root is one argv value,
  preferably quoting every path argument. At minimum the second argument must
  be `"C:\Users\LAPTECH PK\Desktop\cloud Software\q38iu-y1-qual-45425755"`.
  Review the resulting stored action string before any separately authorized
  one-time retry.
- Q38IU-Y1B production/control-plane mutation: NO. Database mutation: NO. Job
  queued: NO. CS2 launched: NO. Agent/Sunshine/Steam/VDD changes: NO. Reboot:
  NO. The only write was this authorized local durable-handoff update.


## Q38IU-Y1D LocalSystem real-Windows desktop-affinity probe — 2026-09-10 UTC

- Result: PASS. Q38IU-Y1 Windows/package qualification is complete. The
  immutable candidate is deployment-eligible for the separate Q38IU-Y2
  transactional production-deployment gate; no deployment occurred here.
- Preflight reverified the immutable Windows archive at 170,460 bytes and
  SHA256 45425755C7DFBC888E1D755FA2F349B97CCC06FFFC3C3D59EC8DEB797C06BA2A.
  The isolated candidate tree remained at
  C:\Users\LAPTECH PK\Desktop\cloud Software\q38iu-y1-qual-45425755.
  Candidate hashes remained windows_interactive.py
  DC622F9A7C5CE9235F887E67A563FD3E2148DF57C77534C5C529985CB220A335,
  windows_presentation.py
  A04CF6C16048B130263391FD48E5F7B1003E70ADD4E484F3E928D5A46F78FCF7,
  and gaming_runtime.py
  0E008111A3D925CE8E18E9B26CFC147188679B5503FC00F0DEC027469864FE18.
  Candidate windows_interactive.py:178 remained exactly
  startup.lpDesktop = r"winsta0\default".
- Remote probe hashes matched the audited originals: parent
  1BF70F3F54630B2E6091A3F180D9CB04121751572176C18FDC8D49733A28DBE4
  and child
  85BB8E512D59833E9C9CD8C407A6B10CD6B34195AF46914B88FD2AAE4CA54C62.
  KhanGaming console Session 1 was Active, CS2 count was zero, no matching
  Python probe process existed, and no Y1D result file existed before launch.
- The old failed Y1A task remained untouched. A separate task
  KhanCloud-Q38IU-Y1D-45425755 was registered with no triggers and a
  two-minute execution limit. Its first locally constructed definition stored
  literal variable fragments due transport quoting; pre-start inspection
  caught this, and it was never executed. The unused definition was corrected
  with an encoded, inspected PowerShell script. The final stored action exactly
  matched five individually quoted path arguments, including the candidate
  root as one argv item.
- Required pre-start task fields were: Execute
  C:\ProgramData\KhanCloud\Agent\runtime\.venv\Scripts\python.exe;
  Principal.UserId SYSTEM; LogonType ServiceAccount; RunLevel Highest.
  Exported XML contained an empty Triggers element, live trigger count was
  zero, and the action working directory was the isolated public probe
  directory.
- Exactly one task start was issued at 2026-09-10T19:42:35.7268470Z. Task
  Scheduler recorded LastRunTimeUtc=2026-09-10T19:42:35.0000000Z and
  LastTaskResult=0. No retry or second start was issued.
- Retained parent result: candidate module resolved to
  C:\Users\LAPTECH PK\Desktop\cloud Software\q38iu-y1-qual-45425755\khan_agent\windows_interactive.py;
  create_process_call_count=1; create_process_lpDesktop=winsta0\default;
  broker_session_id=1; launch_result_session_id=1; child Session ID 1,
  window station WinSta0, desktop Default; child exit code 0;
  child_process_gone=true; monkeypatch_restored=true.
- Final checks found zero matching probe processes and zero CS2 processes;
  KhanGaming Session 1 remained Active. Both JSON evidence files were retained.
  The completed Y1D scheduled-task definition was unregistered and verified
  absent, making the mechanism nonrecurring and non-reinvocable.
- Production/control-plane mutation: NO. Database mutation: NO. Job queued: NO.
  CS2 launched: NO. No agent service, production runtime, Sunshine, Steam, VDD,
  Hyper-V, network, or reboot action occurred. No commit, tag, or push occurred.

## Next gate after Q38IU-Y1D PASS

- Q38IU-Y2 — separately authorized transactional production deployment
  (completed PASS below).
- Do not deploy from the Y1D qualification gate and do not rerun the Y1D probe.

## Q38IU-Y2 transactional production deployment — 2026-09-10 UTC

- Result: **PASS / COMPLETE**. Stop at Y2; do not proceed to Y3 in this task.
- Exact candidate: /tmp/khan-node-agent-q38iu-y1-windows-candidate.tar.gz,
  170,460 bytes, SHA256
  45425755c7dfbc888e1d755fa2f349b97ccc06fffc3c3d59ec8deb797c06ba2a.
  Complete 125-file source/package parity had zero missing, extra, or
  mismatched files. The existing Windows archive matched this size/hash.
- Pre-mutation: KhanCloudAgent Running/Automatic; KhanGaming console Session
  1 Active; CS2 count 0; Sunshine PID 13032 in Session 1 with TCP 47990
  reachable; Steam PID 18572; config 888 bytes with SHA256
  960B7C8B66D15FBE49597B22A7063A288391AE7D1ED3F20299A7AED728CC1189.
  Session/node in-flight and incompatible lifecycle-job counts were zero.
  There was no Y2 staging artifact, active deployment process, dependency
  probe, or rename canary. One expected prior rollback generation was valid.
- Fresh extraction to
  C:\Users\Public\Documents\KhanCloud-Q38IU-Y2-45425755\source contained
  125 files. Critical hashes matched Y1: windows_interactive.py
  DC622F9A7C5CE9235F887E67A563FD3E2148DF57C77534C5C529985CB220A335;
  windows_presentation.py
  A04CF6C16048B130263391FD48E5F7B1003E70ADD4E484F3E928D5A46F78FCF7;
  gaming_runtime.py
  0E008111A3D925CE8E18E9B26CFC147188679B5503FC00F0DEC027469864FE18.
  windows_interactive.py:178 was exactly:
      startup.lpDesktop = r"winsta0\default"
- Deployment used the packaged deploy\universal-bootstrap.ps1 and its
  guarded transactional install-runtime.ps1 engine with the installed config
  path. No file-copy/pip bypass or service-start workaround was used.
  Quiescence and rename-readiness passed, config was preserved in place, and
  commit occurred only after health validation.
- Installed-package regression: 509 passed, 2 skipped, 2 deselected in
  15.61s. Dependency imports, compile, protected Sunshine credential, and
  managed session broker checks passed. Sunshine credential was preserved,
  not created or rotated.
- Transaction heartbeat returned HTTP 200. Both known runtime
  reconciliations reported state=verified; jobs/next returned HTTP 204;
  heartbeat_success reported the node online.
- Post-commit comparison of all 124 Windows-installed candidate files had
  zero missing files and zero hash mismatches. The archive's one systemd
  file is intentionally outside the Windows runtime layout. The deployed
  lpDesktop line remained exact.
- Config bytes and SHA256 were unchanged. Its mtime changed during the
  installer policy/scrub pass, but its content did not. KhanCloudAgent was
  Running/Auto at PID 8448 from the new runtime.
- KhanGaming Session 1 remained Active; CS2 remained zero. Sunshine PID
  13032 and Steam PID 18572 retained their start times and Session 1;
  Sunshine TCP 47990 remained reachable.
- Existing rollback generation
  runtime.rollback.01c68f128c9a46139bd9c264166c48e5 remained structurally
  valid. The fresh transaction rollback protected Y2 until commit and the
  authoritative installer removed that fresh generation after verification.
- Transaction closed: runtime and completed checkpoint present; no canary,
  dependency probe, deployment process, or Y2 scheduled task remained.
- Final database inspection found zero session/node in-flight jobs and zero
  jobs created during Y2 (cutoff 2026-09-10T20:25:00Z). The old XR exact-
  history guard is stale because pre-Y2 START
  ba5e180e-7973-4b28-856c-555545894e3b was created 2026-09-09T22:50:22Z
  and completed blocked before Y2; this read-only mismatch is not a Y2
  deployment failure.
- CONFIG_PRESERVED=YES
- KHANGAMING_SESSION=1 Active
- CS2_COUNT=0
- SUNSHINE_STATE=RUNNING_PRESERVED_PID_13032_TCP_47990_REACHABLE
- ROLLBACK_VALID=YES
- DEPLOYMENT_TRANSACTION_CLOSED=YES
- DATABASE_MUTATION=NO
- JOB_QUEUED=NO
- VDD_MUTATION=NO
- REBOOT=NO
- COMMIT_TAG_PUSH=NO

## Q38IU-Y3 server presentation, Moonlight recovery, and billing defect — 2026-09-11 UTC

- Exactly one Q38IU-Y3 canonical START was consumed: NodeJob
  `3ffe8024-9c85-4c61-b5ff-a56d25c6550c`. It succeeded. Server-side CS2
  launch and Khan VDD presentation succeeded, closing the earlier
  no-visible-window blocker.
- Moonlight then failed with Error 99. A later full KC-01 power cycle restored
  Moonlight without re-pairing; Moonlight connected, opened Steam, and showed
  the KhanGaming desktop. The preserved pairing and recovery exclude a durable
  pairing/configuration defect. Post-power-cycle Sunshine evidence showed an
  initial Microsoft Basic Render Driver at 1024x768/1 Hz, followed by RTX 3080
  re-enumeration at 3840x2160/60 Hz, NVENC creation, a new streaming session,
  and `CLIENT CONNECTED`. This supports a transient Windows GPU/display/
  encoder/session-readiness condition, but the pre-power-cycle Sunshine log
  was not retained, so the exact Error-99 subsystem is not proven.
- A separate canonical STOP appeared as NodeJob
  `a022e1fc-dacb-4067-9afb-8c23f1df0739`; it succeeded. Codex did not issue
  this STOP, and request/audit evidence showed no customer session action or
  connection event in the trigger window.
- Authoritative STOP chain: KC-01 heartbeat -> `POST /api/v1/nodes/heartbeat`
  -> `reconcile_gaming_billing_for_node` -> final reserved billable minute
  consumed -> `meter_gaming_session` set desired_state `stopped` with initial
  reason `reserved_funds_exhausted` -> canonical
  `queue_gaming_action(action="stop")` -> STOP `a022e1fc-...` -> successful
  result finalization overwrote the persisted reason with `customer_stop`.
- Billing evidence: five charges of 117 PKR-minor at 21:13:15Z, 21:14:22Z,
  21:15:29Z, 21:16:35Z, and 21:17:09Z consumed all 585 reserved minor units.
  The next KC-01 heartbeat at 21:18:16Z created the STOP. There was no active
  connection lease, runtime-health failure count remained zero, and there was
  no surrounding audit event.

### Reservation-extension collision root cause and local fix

- Root cause confirmed: the old gaming extension key was
  `gaming:<session-id>:extend:<target-total>:v1`. It omitted reservation
  identity. An extension transaction from a prior reservation for the same
  GamingSession/target was therefore replayed. `extend_reservation()` returned
  that old transaction without extending the current reservation, allowing the
  current five-minute minimum reservation to drain despite sufficient wallet
  funds.
- Forward-only fix in
  `backend/app/services/gaming_billing_service.py`: extension keys are now
  `gaming:<session-id>:reservation:<reservation-id>:extend:<target-total>:v2`.
  The current reservation UUID makes different reservation lifecycles
  collision-free while the same reservation/target remains deterministic and
  retry-idempotent. There is intentionally no v1 fallback because it would
  recreate the cross-reservation collision.
- Existing historical v1 ledger rows remain immutable. A legitimately
  committed v1 extension already advanced `reserved_minor`, so after
  deployment its next required target is higher and receives a v2 key. A prior
  collided/no-op v1 attempt can safely post the missing extension under its
  reservation-specific v2 key.
- Defensive hardening in `backend/app/services/wallet_service.py`: an existing
  extension transaction is accepted as a replay only when transaction type,
  currency, reservation external reference, entry count, and amount match.
  A foreign reservation or different contents now fail explicitly instead of
  silently suppressing the current extension.
- Focused regression module:
  `backend/tests/test_gaming_reservation_extension_q38iu.py`. Coverage includes
  same-reservation/same-target retry with one ledger movement; same-session,
  different-reservation/same-target success; foreign replay rejection; five
  Y3-shaped metering cycles in the presence of colliding historical v1 keys;
  committed-v1 to next-v2 in-progress compatibility; and unchanged
  insufficient-funds STOP behavior.
- Focused command from `backend`:
  `.venv/bin/python -m pytest -q tests/test_gaming_reservation_extension_q38iu.py`
  -> **6 passed**.
- Affected gaming billing command from `backend`:
  `.venv/bin/python -m pytest -q tests/test_gaming_reservation_extension_q38iu.py tests/test_gaming_billing_kg009c2.py`
  -> **16 passed** before the final compatibility test was added. The final
  focused and grouped runs below supersede it.
- Final grouped command from `backend`:
  `.venv/bin/python -m pytest -q tests/test_gaming_reservation_extension_q38iu.py tests/test_gaming_billing_kg009c2.py tests/test_kf001_ledger_rules.py tests/test_kf001_financial_lifecycle_static.py tests/test_kf002c_enterprise_settlement_hardening.py`
  -> **55 passed**.
- `git diff --check` for the focused source/test paths: PASS before the handoff
  update; final validation repeated after the handoff update.
- Local source files changed by this commercial fix:
  `backend/app/services/gaming_billing_service.py`,
  `backend/app/services/wallet_service.py`, and
  `backend/tests/test_gaming_reservation_extension_q38iu.py`. This handoff was
  also updated as required.
- The backend fix is local and qualified but not deployed. No control-plane
  service restart occurred. Do not issue another real START until deployment
  and the currently working Moonlight/Sunshine state are separately reviewed.
- Production database mutation: NO. Gaming START/STOP/DELETE issued by this
  fix gate: NO. Windows/runtime/Sunshine/VDD/Hyper-V mutation: NO. Reboot: NO.
  Commit/tag/push: NO.

## Next gate after Q38IU-Y3 billing fix

- Review the local commercial fix and authorize its controlled backend
  deployment separately. Revalidate the currently working Sunshine/Moonlight
  state without re-pairing or unrelated Windows mutation.
- Only after that review may a separately authorized canonical START be used
  for the next controlled Moonlight validation hold. Do not issue that START
  automatically from this gate.

## Q38IU-Y4 backend deployment and pre-RAW readiness — 2026-09-11 UTC

- Source qualification was reused without rerunning it: focused reservation-
  extension regression **6 passed**; final grouped gaming-billing/ledger/
  financial-lifecycle/settlement regression **55 passed**. The qualified key
  remains
  `gaming:<session-id>:reservation:<reservation-id>:extend:<target-total>:v2`.
  No migration or schema change is required.
- Pre-deployment Git safety passed: branch
  `feature/kg009-gaming-runtime-orchestrator`, HEAD
  `70260fba00b800bef15916cafde229d9d5e3ceda`, no staged changes, and the
  existing dirty worktree was preserved. The focused backend changes remain
  limited to `backend/app/services/gaming_billing_service.py`,
  `backend/app/services/wallet_service.py`, and the untracked focused test
  `backend/tests/test_gaming_reservation_extension_q38iu.py` (plus this
  handoff).
- Authoritative deployment contract: the installed
  `/etc/systemd/system/khan-cloud-control-plane.service` is byte-for-byte
  identical to `backend/deploy/systemd/khan-cloud-control-plane.service`. It
  runs `/opt/khan-cloud/source/backend/.venv/bin/python -m uvicorn app.main:app`
  directly from `/opt/khan-cloud/source/backend` and has no auto-reload. Thus
  this source-only change requires only a controlled restart of
  `khan-cloud-control-plane.service`; no copy, build, dependency, daemon-reload,
  migration, database, or other-service step is required.
- Deployment is **BLOCKED / NOT PERFORMED** by host authorization. Both
  `sudo -n systemctl restart khan-cloud-control-plane.service` and direct
  `systemctl restart khan-cloud-control-plane.service` were rejected because
  interactive authentication is required. The service retained PID 297982,
  started 2026-09-11 06:35:39Z, earlier than the qualified source edits at
  11:56-11:58Z. It therefore still has the old v1 implementation loaded.
  No force-kill or ad-hoc process replacement was used to bypass systemd.
- The unchanged control plane remained healthy after the denied attempts:
  `/health` reported healthy/database connected, `/ready` reported ready, and
  KC-01 continued heartbeat/desired-state/jobs-next cycles with HTTP
  200/200/204. The 12:32:50Z database snapshot had KC-01 last seen at
  12:32:24Z (25.7 seconds old), node online/approved/connectivity online,
  gaming healthy and accepting work, and admission not auto-blocked.
- No reconciliation side effect occurred. Session job count remained 26,
  session and node in-flight counts remained zero, and the newest job remained
  the already-known successful STOP `a022e1fc-dacb-4067-9afb-8c23f1df0739`
  created 2026-09-10 21:18:16Z. No START or STOP was queued in Y4.
- Commercial state is otherwise ready. The session is stopped/stopped,
  billing finalized, and still references historical reservation
  `bc02acda-0a33-4bba-9247-5413f6a28595`, which remains immutable/closed at
  585 reserved, 585 consumed, 0 released. The sole active PKR wallet has
  66,187 minor available and 0 reserved. SKU `gaming-rtx-3080-10g` is active,
  sellable, and metered; the PK hourly rate is 7,000 minor, yielding 117 minor
  per minute and a five-minute/585-minor initial hold.
- Once separately authorized after a successful backend restart, canonical
  START calls `reopen_gaming_billing`: because billing is finalized, it will
  create a new `gaming_session_restart` UsageReservation for 585 minor and
  point the session at that new reservation. Runtime coverage top-ups then use
  the current reservation-specific v2 key. At the observed balance/rate, the
  wallet can fund 565 whole billed minutes (66,187 / 117, remainder 82),
  assuming no concurrent spend or pricing/balance change; the mechanism starts
  with five minutes and restores rolling five-minute coverage after metering.
  The old closed reservation requires no repair.
- KC-01 read-only preflight passed after its power cycle: KhanCloudAgent
  Running/Automatic (PID 8780); KhanGaming console Session 1 Active; CS2 count
  0; Sunshine exactly one process in Session 1 (PID 8224) with TCP 47990
  reachable; Steam PID 20932 in Session 1; Khan Virtual Display
  `ROOT\\DISPLAY\\0000` status OK/problem code 0. Runtime state is
  stopped/stopped with reconciliation verified, ownership termination verified,
  zero owned processes remaining, and no stale launch attempt. Deployment
  transaction and prior Y3 observer state are clean; the installed config hash
  remains preserved.
- User-supplied physical-client evidence remains authoritative:
  POST_BOOT_MOONLIGHT_CONNECTION=PASS and POST_BOOT_VIDEO_STREAM=PASS without
  re-pairing. Desktop exposure, restricted Steam/kiosk UX, input restrictions,
  and pre-launch-before-stream design remain explicitly deferred until after
  RAW E2E proof.
- Gate result: `RESERVATION_FIX_DEPLOYED=NO`, `RUNNING_KEY_VERSION=v1`, and
  `READY_FOR_ONE_RAW_E2E_START=NO`. The single remaining prerequisite is an
  authorized `systemctl restart khan-cloud-control-plane.service`, followed by
  health/new-PID/current-heartbeat/no-new-job proof. Do not issue START as part
  of that deployment verification.
- Production database/financial mutation: NO. Windows runtime/Sunshine/VDD/
  Steam/Hyper-V mutation: NO. Reboot: NO. Commit/tag/push: NO.

## Q38IU-Y4 continuation — authenticated backend restart verification — 2026-09-11 UTC

- The operator completed the authenticated, authoritative systemd restart.
  khan-cloud-control-plane.service now reports active/running with MainPID and
  ExecMainPID 312447, started 2026-09-11 12:44:57Z. The old PID was 297982.
  PID 312447 runs the unit's exact Uvicorn command from
  /opt/khan-cloud/source/backend; shutdown/startup completed normally.
- Running implementation proof: both qualified source files predate the new
  process. The source-valid CPython bytecode exactly matches
  gaming_billing_service.py by embedded source mtime and size and contains
  the v2 helper/constants gaming:, :reservation:, :extend:, and :v2.
  The exact read-only helper rendering was
  gaming:59f0874e-69c6-4e59-bb46-1bb18e104375:reservation:bc02acda-0a33-4bba-9247-5413f6a28595:extend:702:v2.
  Targeted application-source search found the extension builder only at its
  definition and the canonical ensure_runtime_coverage call; no old v1
  extension constructor remains. Post-start KC-01 heartbeats exercised the
  billing reconciliation import path. Therefore v2 is authoritative for all
  new reservation-extension operations; historical v1 rows remain immutable
  data only.
- Control-plane /health and /ready passed with the database connected.
  KC-01 repeatedly completed heartbeat/desired-state/jobs-next as HTTP
  200/200/204 through PID 312447. The final database snapshot at 12:51:14Z had
  KC-01 last seen at 12:51:09Z (5.1 seconds old), online/approved, gaming
  healthy and accepting work.
- Restart produced no lifecycle or financial side effect. Session job count
  remained 26, session/node in-flight counts remained zero, and the newest job
  remained historical STOP a022e1fc-dacb-4067-9afb-8c23f1df0739 from
  2026-09-10. Counts at/after the 12:44:50Z restart cutoff were zero
  LedgerTransactions and zero UsageReservations; the latest ledger timestamp
  remained 2026-09-10 21:17:09Z.
- Commercial state remains ready and unchanged: wallet available/reserved is
  66,187/0 PKR-minor; rate is 117 minor/minute; SKU is active/sellable/metered.
  Exhausted Y3 reservation bc02acda-0a33-4bba-9247-5413f6a28595 remains
  closed at 585 reserved, 585 consumed, 0 released and was not repaired.
  Canonical next START will invoke reopen_gaming_billing, create a new
  585-minor restart reservation, bind the session to it, and use that current
  reservation identity for deterministic v2 coverage extensions.
- Fresh read-only KC-01 preflight passed: KhanCloudAgent Running/Automatic PID
  8780; KhanGaming console Session 1 Active; CS2 count 0; Sunshine PID 8224 in
  Session 1 with TCP 47990 reachable; Khan Virtual Display
  ROOT\\DISPLAY\\0000 OK/problem code 0; deployment transaction clean.
  Runtime remains stopped/stopped with reconciliation verified, terminated
  ownership boundary verified, zero owned processes remaining, and no stale
  launch attempt.
- Final continuation result: RESERVATION_FIX_DEPLOYED=YES,
  RUNNING_KEY_VERSION=v2, RESERVATION_EXTENSION_V2_READY=YES, and
  READY_FOR_ONE_RAW_E2E_START=YES.
- No START/STOP was issued. No production financial or Windows runtime mutation
  occurred. No Sunshine/VDD/reboot action occurred. No commit/tag/push occurred.
  Stop and wait for explicit authorization before the single RAW E2E START.

## Q38IU-Y5 one authorized RAW E2E START — 2026-09-11 UTC

- Exactly one new canonical START was committed through
  queue_gaming_action(db, session=session, action="start", commit=True):
  NodeJob 9a92204f-c108-4293-bddd-6444e030470c. No historical job was reused
  and no second START was issued.
- Atomic post-commit proof found exactly one new gaming.session.start job,
  exactly one new UsageReservation
  e5465a74-3a15-4c0d-a319-2a769dff7913, and exactly one new reservation ledger
  transaction. Initial reservation was 585 minor; wallet moved once from
  66,187/0 to 65,602/585 available/reserved. The exhausted Y3 reservation
  remained historical and unchanged.
- The agent claimed the START once at 12:58:15Z. The presentation helper
  (PID 24608) dynamically resolved the Khan VDD as \\.\DISPLAY6 for this boot
  and continuously discovered CS2 PID 8652 during its 12:58:28Z-12:59:43Z
  probe window. The managed interactive execution context was validated as
  KhanGaming Session 1 and the recorded CS2 install root remained
  C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive.
- The START failed at the first presentation gate. It never produced a
  qualifying visible top-level CS2 HWND, so no WinSta0\Default window,
  visibility/cloak/owner/tool/iconic qualification, or MonitorFromWindow mapping
  could be proven. NodeJob completed blocked at 12:59:41Z with:
  "Customer game presentation was not verified on Khan VDD before stream
  readiness: No visible game window appeared before timeout."
- After failure CS2 was absent. Sunshine remained unchanged at PID 8224 in
  Session 1. The agent state already proved stopped/stopped, verified
  reconciliation, terminated/verified ownership, and zero owned processes.
  No manual launch, Sunshine restart, VDD mutation, or second START occurred.
- Because failed START intentionally retained the 585-minor reservation and
  desired_state=running, canonical cleanup was required. One guarded canonical
  STOP was issued as NodeJob 9ac5b883-5cbf-47cf-9ce8-48376921b841. It succeeded
  idempotently at 13:04:13Z, finalized the session stopped/stopped, closed the
  Y5 reservation at 585 reserved / 0 consumed / 585 released, and restored the
  wallet to 66,187 available / 0 reserved.
- Time-bounded ledger audit showed exactly two Y5 postings: one
  wallet_reservation for the canonical restart and one
  wallet_reservation_release keyed to the new reservation. There was no usage
  charge and no reservation extension transaction. Therefore the live v2
  extension proof was not reached; this is not an extension collision or
  five-minute-boundary failure.
- Final result: SERVER_SIDE_RAW_PATH=FAIL,
  LIVE_GAME_HELD_FOR_MOONLIGHT=NO, PRESENTATION_HELPER=FAIL,
  V2_EXTENSION_ACTIVE=NO, SECOND_START_ISSUED=NO, STOP_ISSUED=YES_CANONICAL_CLEANUP.
  Do not ask the user to open Moonlight for this attempt.

## Q38IU-Y5A Y3-versus-Y5 presentation differential — 2026-09-11 UTC

- This was a read-only production diagnosis. No START, STOP, manual game
  launch, process/service restart, display change, financial/session/job
  mutation, test run, deployment, or commit/tag/push occurred. The only write
  was this requested durable-handoff update.
- Steam retained the exact Y5 executable and command line. PID 8652 was
  `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe`
  with argument `-steam`, AppID 730, in Session 1. This matches Y3 PID 8616.
  Both canonical requests were exactly
  `"C:\Program Files (x86)\Steam\steam.exe" -applaunch 730`; the deployed
  broker path used the managed Session 1 token, inherited user environment,
  Steam working directory, and explicit `winsta0\default`. Historical parent
  PID, CS2 token integrity/elevation, and exact Y5 creation FILETIME were not
  retained and must not be guessed.
- Earliest retained pre-launch divergence is Steam state. Before Y3, Steam
  received `steam://close/bigpicture` and remained in its logged UI mode 7.
  After the power cycle and physical transport check, Y5's still-running Steam
  PID 20932 had been launched by Sunshine PID 8224 as
  `steam.exe -- steam://open/bigpicture`, transitioned UI mode 7 -> 4, and
  remained that Big Picture instance when canonical `-applaunch 730` arrived.
  This state difference is proven; that it caused the later renderer stall is
  not proven.
- First retained post-process functional divergence is renderer/window
  materialization. Y3's Steam launch task passed `WaitingGameWindow`
  immediately; its overlay renderer began DXGI setup about 9 seconds after
  process creation, created a D3D11 swap chain at 21:12:01Z, and the independent
  observer recorded the qualifying SDL_app HWND 393378 at that exact second.
  Y5 remained in Steam's `WaitingGameWindow` task for about 16 seconds; its
  overlay renderer did not begin DXGI setup until about 50 seconds after
  process creation, logged two `Failure waiting for hooking mutex!` records,
  and never recorded swap-chain creation before failed-readiness ownership
  cleanup terminated PID 8652. Steam removed PID 8652 at 12:59:46Z with exit
  code 1, five seconds after the blocked START result; this aligns with the
  source-defined `_cleanup_failed_launch()` teardown and not an internal crash.
- No Windows Application/System event in 12:58:20Z-13:00:00Z reported a CS2
  crash, hang, WER, NVIDIA, display, Vulkan, DXGI, or GPU failure. No WER,
  CrashDumps, or Steam dump artifact was created in the interval, and no CS2
  game/user-data file was modified in the interval. Current device inspection
  still reports the RTX 3080 and Khan Virtual Display healthy/problem code 0.
  Sunshine's retained post-boot stream log proves RTX 3080 DXGI capture and
  NVENC operation at 3840x2160 before Y5; therefore this was not evidence of
  system-wide GPU or Sunshine loss.
- Launch-time VDD evidence is materially equivalent at the helper boundary:
  both runs resolved `\\.\DISPLAY6`, handle 131073, bounds
  `[1024,0,2944,1080]` (1920x1080). Y3 independently observed DISPLAY1 as the
  1024x768 primary and DISPLAY6 as the non-primary VDD. Y5 did not capture a
  full launch-time monitor/adapter enumeration. Its post-boot Sunshine stream
  had previously used the VDD at 3840x2160, so a preceding 4K-to-1080 policy
  transition existed, but no retained evidence establishes it as causal.
- The Y5 helper repeatedly proved PID 8652 was a Session 1 process beneath the
  expected install root, but its current filter records no per-HWND telemetry.
  It enumerates only its current desktop and accepts only visible, unowned
  top-level windows at least 64x64. It does not log hidden, owned, small,
  off-screen, cloaked, tool, iconic, other-desktop, or transient rejected
  windows. Unlike Y3, no independent all-window observer ran for Y5. Therefore
  the authoritative distinction is: no qualifying CS2 top-level HWND was
  observed; whether PID 8652 created no HWND at all or created only a rejected
  HWND is not retrospectively recoverable. No SDL_app window was observed, and
  presentation-filter false-negative status is UNKNOWN.
- Evidence-based diagnosis: the first causal blocker was CS2 renderer/window
  materialization before the 75-second presentation deadline: Y5 reached DXGI
  factory hooks late but never reached the Y3 D3D11 swap-chain/SDL_app-window
  milestone. Root-cause class is `gpu/display-init`; the exact underlying cause
  is not proven. The pre-existing Sunshine-launched Big Picture Steam state and
  preceding VDD mode transition are bounded candidate precursors, not findings
  of causation.
- Another START is not cleared. Smallest corrective gate: first add and qualify
  retained per-sample presentation-helper telemetry for every CS2 HWND and each
  rejection reason; then normalize and verify Steam out of the retained
  Sunshine/Big-Picture state before a separately authorized, instrumented
  one-START A/B. Do not loosen the HWND filter or merely increase the timeout
  without that evidence. `LIVE_V2_EXTENSION_PROOF=PENDING`.

## Q38IU-Y7 continuation — read-only canonical START preflight — 2026-09-13 UTC

- Scope was Phase 1 and Phase 2 only. No KC-01 fresh mutable-precondition check,
  canonical START, STOP, production database mutation, deployment, reboot, or
  commit/tag/push occurred. Existing worktree changes were preserved. This
  handoff entry is the only repository write in this continuation.
- Branch `feature/kg009-gaming-runtime-orchestrator` and HEAD
  `70260fba00b800bef15916cafde229d9d5e3ceda` matched the expected checkpoint.
  The baseline was 20 modified tracked files and existing untracked development
  files; tracked diff summary was 3,661 insertions and 108 deletions.
- Current source verifies `SessionLocal` in `app.db.database`,
  `NodeJob.gaming_session_id`, `wallet_balances(db, wallet)` returning
  `available_minor`/`reserved_minor`, and
  `queue_gaming_action(db, *, session, action, commit=True)` in
  `app.services.gaming_service`. START rejects terminal session states and a
  pending/running session job, requires assigned `node_id`, reopens billing,
  sets desired_state=`running` and status=`starting`, queues one
  `gaming.session.start` job for this bare-metal session, and commits once.
  `reopen_gaming_billing` creates a fresh restart UsageReservation when billing
  is finalized. The existing backend venv imported all required modules.
- The `/tmp/q38iu_y7_readonly_preflight.py` script syntax-checked and ran with
  `PYTHONPATH=/opt/khan-cloud/source/backend .venv/bin/python` from `backend`.
  The PostgreSQL transaction explicitly reported `transaction_read_only=on`;
  it was rolled back. Snapshot time: 2026-09-13T12:23:35Z.
- Session `59f0874e-69c6-4e59-bb46-1bb18e104375` exists and is
  status/desired_state `stopped/stopped`, deployment_mode `bare_metal`, stage
  `stopped`, runtime `kc-gaming-59f0874e-69c6-4e59-bb46-1bb18e104375`,
  sanitation/quarantine states empty, billing finalized at
  2026-09-11T13:52:43Z. No newer legitimate activity was observed.
- There are 30 session jobs. The latest is the historical Y6 STOP
  `be3bb54f-8916-49c6-bff0-a783c5e69ebd`, `gaming.session.stop`,
  `succeeded` and completed 2026-09-11T13:52:43Z; zero jobs followed it.
  Session and node gaming in-flight counts are both zero. Historical Y6 START
  `a91fbe20-9005-4cec-b578-a7d01a612ead` remains blocked; neither job was
  replayed.
- Current usage reservation `0d07ca52-97da-4b6f-ab51-a6d02055ae15` is
  closed: reserved 585, consumed 0, released 585, remaining 0 PKR minor. A
  supplementary read-only query found zero reserved/active usage reservations
  for this session. The sole active PKR wallet has available 66,187 and
  reserved 0 minor. Stored rate is 117 minor/minute; five-minute restart hold
  required by current source is 585 minor.
- Assigned node `ae52e6cb-4cc9-4797-afcc-4f92042b1b90` is online,
  approved, enabled, gaming healthy and accepting work; admission auto-block
  is false. Its last heartbeat was 2026-09-13T12:23:14Z, about 21 seconds
  before the snapshot. `gaming_host_readiness_reasons` returned no reasons.
  Title qualification is current/true; CS2 title enabled; SKU
  `gaming-rtx-3080-10g` active/sellable/metered; PK hourly rate is 7,000.
  Existing gaming capacity reservation is active on the assigned node.
  `NodeCapacity.execution_enabled` and `scheduling_enabled` are false; the
  current *restart* queue path does not check those fields and retains the
  existing gaming reservation. Do not misstate these flags as enabled.
- Phase 2 DB/commercial preflight passed at the snapshot. Fresh KC-01
  service/session/CS2/Sunshine/VDD/Steam preconditions were intentionally not
  checked in this run because the user explicitly limited it to Phases 1–2.
  Consequently the final `Q38IU-Y7 CANONICAL START — READY` gate was not
  asserted. Perform Phase 3 and recheck any volatile DB state before asking
  for explicit approval of exactly one fresh canonical START.

## Q38IU-Y7 continuation — Phase 3/4 READY gate — 2026-09-13 UTC

- Scope: KC-01 read-only volatile checks followed by a minimal read-only DB
  recheck. No START, STOP, agent/Steam/CS2/Sunshine/VDD/Hyper-V/KG008 mutation,
  reboot, credential access, production database mutation, or commit/tag/push.
  Existing dirty source worktree preserved; this append is the only repository
  write in this continuation.
- KC-01 direct authorized SSH succeeded. Read-only `quser` showed
  `khangaming` on console Session 1 Active. At 12:32:39Z, Win32_Service showed
  exactly one KhanCloudAgent service, Running as LocalSystem, PID 8976.
  Win32_Process enumeration for cs2.exe, steam.exe, sunshine.exe returned
  exactly one process: sunshine.exe PID 10272, Session 1, from
  `C:\Program Files\Sunshine\Sunshine.exe`; hence CS2=0 and Steam=0.
  Get-NetTCPConnection filtered to LocalPort 47990/State Listen returned one
  0.0.0.0:47990 listener owned by the same Sunshine PID 10272. No Sunshine
  restart or Steam baseline manipulation occurred.
- `Get-PnpDevice -InstanceId 'ROOT\DISPLAY\0000'` returned Status OK and
  Problem 0. Matching Win32_PnPEntity count was one and
  ConfigManagerErrorCode was 0. No display number, coordinates, LUID, or mode
  was assumed or changed.
- The minimal temporary gate script `/tmp/q38iu_y7_gate_recheck.py` passed
  CPython syntax checking and ran from the existing backend venv using
  `PYTHONPATH=/opt/khan-cloud/source/backend .venv/bin/python`. Its PostgreSQL
  transaction reported `transaction_read_only=on` and was rolled back.
  Snapshot time was 2026-09-13T12:34:28Z.
- Session remained stopped/stopped with deployment_stage stopped and billing
  finalized. Latest job remained the Y6 STOP
  `be3bb54f-8916-49c6-bff0-a783c5e69ebd`, succeeded; newer job count 0,
  session in-flight 0, node gaming in-flight 0. Current Y6 reservation
  `0d07ca52-97da-4b6f-ab51-a6d02055ae15` remained closed at
  585 reserved / 0 consumed / 585 released; open usage reservation count 0.
  Sole active PKR wallet remained 66,187 available / 0 reserved. Required
  fresh restart hold remained 585 minor.
- Assigned node remained online/approved, gaming healthy/accepting work,
  admission auto-block false, readiness reasons empty, last heartbeat
  2026-09-13T12:34:16Z. Existing gaming capacity reservation
  `94242317-c46f-45fa-abb2-36cc83eab25c` remained active on that node.
  CS2 title remained enabled, title qualification true with no reason codes
  and evaluated at the latest heartbeat, and SKU `gaming-rtx-3080-10g`
  remained active/sellable/metered.
- Final source read confirmed
  `queue_gaming_action(db, *, session, action, commit=True)` still calls
  `reopen_gaming_billing`, then sets desired running/status starting, adds
  one `gaming.session.start` NodeJob for this bare-metal deployment, and
  commits once. With finalized billing, `reopen_gaming_billing` calls
  `reserve_funds` for 585 minor. That function locks the wallet, posts the
  available-to-reserved ledger transfer, creates a fresh reserved
  UsageReservation, and flushes it within the same DB transaction. This
  describes the planned effect only; the call was NOT executed.
- Gate result: `Q38IU-Y7 CANONICAL START — READY` at the above snapshots.
  Approval is still required. At execution, a guarded script must recheck all
  volatile KC-01 and DB preconditions and abort before mutation on divergence,
  then call the canonical START exactly once. No historical job may be replayed.

## Q38IU-Y7 — one authorized canonical cleanup STOP — 2026-09-13 UTC

- Authorization was for exactly one fresh Q38IU-Y7 cleanup STOP, read-only
  validation, and a handoff append. No START, historical STOP replay, second
  STOP, reboot, Steam/CS2 manipulation, Sunshine/VDD/Hyper-V/KG008 change,
  source mutation, commit, tag, or push occurred. The existing dirty worktree
  and all earlier handoff history were preserved.
- Branch `feature/kg009-gaming-runtime-orchestrator`; HEAD
  `70260fba00b800bef15916cafde229d9d5e3ceda`. Before this task's append,
  `git status --short` showed the pre-existing 20 modified tracked files and
  untracked development files, including this handoff. No tracked source file
  was edited in this task.
- The canonical route is
  `POST /api/v1/compute/gaming/sessions/59f0874e-69c6-4e59-bb46-1bb18e104375/actions`
  with `{"action":"stop"}`; it calls
  `queue_gaming_action(db, session=session, action="stop")`.
  No reusable authenticated API credential was present in the operator
  environment, so the established guarded production *service* path was used,
  as in the preceding Y7 START. The service performed the DB transaction and
  queued the normal node job; there was no hand-written DB row mutation.
- Temporary guard script `/tmp/q38iu_y7_guarded_stop.py` was syntax-checked
  with `python3 -m py_compile`. Its default dry run used
  `SET TRANSACTION READ ONLY` and passed at 14:46:22Z. The executing call
  rechecked under row locks at 14:47:02.603509Z before invoking the service
  exactly once. At that instant: Y7 START
  `6c83c948-583e-4ba8-8792-a5bd6e93d35d` remained latest/blocked; newer
  STOP count 0; session and node gaming in-flight counts 0; session was
  error/running/stopped; billing not finalized; lease
  `e3106cc5-f1e6-4646-a49e-5f3fbbdd85ed` revoked; Y7 reservation
  `79db80c6-d1fe-46b2-bd36-7eab4bcd97b7` reserved 585/consumed
  0/released 0; wallet available/reserved 65,602/585 PKR minor. Immediate
  KC-01 read-only check still showed stopped runtime, verified termination,
  zero owned processes, and CS2 count 0.
- Exactly one new job was committed:
  `1951349b-878f-42e9-95b6-f10e9b093b98`,
  `gaming.session.stop`, initially pending at 14:47:02.603509Z.
  Immediately after queue: session stopping/stopped with stage stopped;
  reservation still reserved 585/0/0; wallet still 65,602/585. The normal
  KhanCloudAgent claimed the job at 14:47:29.123619Z and it succeeded at
  14:47:29.213433Z on attempt 1, with empty error message. Result:
  runtime stopped, deployment_stage stopped, `idempotent=true` because the
  persisted ownership boundary was already structurally retired and clean.
  Read-only DB verification found exactly one job after the Y7 START.
- Final read-only DB snapshot at 14:47:33Z: session status/desired/stage
  stopped/stopped/stopped, connection info cleared, lease revoked, no inflight
  gaming actions. Billing finalized at 14:47:29.217730Z with reason
  `customer_stop`. Y7 usage reservation closed with reserved 585,
  consumed 0, released 585, remaining 0 PKR minor; no open usage reservation
  remains. Active PKR wallet available/reserved is 66,187/0 minor.
- Final read-only KC-01 check: persisted runtime status stopped; schema-v2
  ownership type terminated, boundary verified, termination verified,
  clean=true, owned_process_count=0, owned_process_count_remaining=0.
  CS2 count 0. Steam PID 24500 remains
  `DESKTOP-4ROCVUH\KhanGaming` in Session 1; it was not manipulated.
- Capacity interpretation follows current source: STOP cleans the runtime
  and releases the *usage-money hold*, but does not release
  `GamingReservation` or subtract `NodeCapacity` allocations.
  Reservation `94242317-c46f-45fa-abb2-36cc83eab25c` remains active,
  unreleased, on node `ae52e6cb-4cc9-4797-afcc-4f92042b1b90`, owning
  8 CPU, 17,179,869,184 memory bytes and 85,899,345,920 storage bytes.
  NodeCapacity allocated values match those amounts. Source
  `finish_gaming_job` leaves capacity assigned after
  `gaming.session.stop`; only a separately authorized delete/sanitation
  path calls `release_gaming_reservation` to repool it. Node remained
  online/approved/healthy/accepting work; execution_enabled and
  scheduling_enabled remain false.
- Verification commands: `python3 -m py_compile
  /tmp/q38iu_y7_guarded_stop.py`; read-only dry run
  `PYTHONPATH=/opt/khan-cloud/source/backend
  /opt/khan-cloud/source/backend/.venv/bin/python
  /tmp/q38iu_y7_guarded_stop.py`; single authorized execution with
  `--execute`; read-only
  `/tmp/q38iu_y7_cleanup_preflight.py` snapshots; targeted read-only
  SQLAlchemy post-result query; direct read-only KC-01 PowerShell runtime,
  process, and service observations. No source test suite or migration was
  run because this task did not change source or schema.
- A final direct KC-01 read-only Get-Service check after the STOP reported
  KhanCloudAgent Status=4 (Running). No service control action was issued.

## Q38IU-Y8 ROOT-CAUSE ANALYSIS — 2026-09-13 UTC

**Scope and outcome.** Y8 was read-only except for this requested handoff append. The Y7 failure is proved at the helper's **current-desktop, target-PID top-level-window discovery boundary**. It is not proved that CS2 never created any top-level window, nor is the underlying renderer/desktop failure proved. No second canonical START is justified on present evidence. The prior authorized Y7 canonical cleanup STOP left the commercial session stopped/stopped, the reservation closed, zero CS2, and no in-flight job. Y8 queued no job or touched any Windows runtime control.

### Clock domains and exact Y7 sequence

- Control-plane/database clock: read-only PostgreSQL `NodeJob` query returned Y7 START `6c83c948-583e-4ba8-8792-a5bd6e93d35d` created `12:43:10.437974Z`, claimed `12:43:18.408763Z`, marked blocked/completed `12:45:49.319225Z`. These are database-side timestamps, not helper event times. The transaction reported `transaction_read_only=on`.
- KC-01 Steam `gameprocess_log.txt` uses second-precision local wall time. A read-only live KC-01 time-zone query returned `Pacific Standard Time`, local offset `-07:00` on 2026-09-13. The Y7 Steam log's `05:44:10` client start/UI `0->7` maps to approximately `12:44:10Z`; `05:44:36` AppID 730 tracking of `cs2.exe -steam` PID **6936** maps to approximately `12:44:36Z`. Overlay attach for the same PID at `12:44:37 UTC` corroborates the offset. Steam tracking is a process observation, not an exact Windows process-creation FILETIME.
- KC-01 overlay log states UTC at whole-second resolution. It identifies `cs2.exe`, PID 6936, GameID/OverlayGameID 730 and injected `gameoverlayrenderer64.dll` at `12:44:37Z`. CEF paint-event error 2 and shell32 hook-load failure occur then; neither proves fatal launch failure.
- KC-01 presentation helper records `time.time()` epoch seconds with microsecond formatting and uses `time.monotonic()` for its deadline. Its PID 11004 entered at epoch `1789303479.639886` (`12:44:39.639886Z`), resolved Khan VDD `\\.\DISPLAY6` by `12:44:40.485607Z`, first completed a successful `EnumWindows` scan at `12:44:40.795715Z`, and logged deadline expiry at epoch `1789303555.665361` (`12:45:55.665361Z`). VDD-resolution-to-timeout wall time is approximately 75.18 seconds; the controlling interval is the helper's 75-second monotonic deadline. Across repeated approximately 400-ms scans, `_game_pids` returned `[6936]`; each retained scan reported `enum_ok=True`, `target_pid_hwnd_count=0`, `rejected_count=0`, `accepted_candidate_count=0`. No placement or monitor verification ran.
- On KC-01's clock, Steam reported `05:45:58` local (approximately `12:45:58Z`) as no longer tracking PID 6936, exit code 1. Source defines verified cleanup after presentation/readiness failure; no retained log timestamps the cleanup call itself.
- **Cross-host caveat:** DB completion precedes the helper-local timeout stamp by about **6.35 seconds**. No historical measurement of database/control-plane versus KC-01 clock offset, synchronization error, timestamp-assignment point, or log-write delay is retained. A present-day clock check cannot calibrate that historical offset. Do not infer job completion before helper timeout. The source call chain makes presentation return a prerequisite for the blocked result; it does not make these two wall-clock stamps directly orderable. KC-01 Steam, overlay, and helper records are comparable to approximately seconds after applying the observed local offset, subject to their different precisions.

The apparent claim-to-Steam-tracking span is approximately **78 seconds**, with cross-host uncertainty on its start. Its apparent first 52 seconds end at Steam's logged `0->7` startup; no retained timestamp apportions that section among runtime preparation, managed-session validation, display policy, Steam inventory/readiness, pre-launch baseline persistence, dispatch of `-applaunch 730`, or Steam authentication. Source shows these operations can occur, but their Y7 durations are **not evidenced**. Within KC-01 Steam's clock, startup-to-tracked-PID spans **26 seconds**; the log does not separately timestamp authentication/UI initialization, AppID request acceptance, or subtasks within launch processing. Thus neither a 78-second CS2 startup nor a 78-second presentation wait is established. The helper began about three seconds after Steam first tracked PID 6936.

### Process and desktop identity

- `SteamLauncherAdapter.build_launch_attempt_authority()` records the pre-launch Session-1/install-root process baseline. `SteamLauncherAdapter.launch()` sends a transient interactive `steam.exe -applaunch 730` request, then `wait_for_new_game_processes()` polls for new `(PID, creation FILETIME)` identities beneath the verified game install root in managed Session 1, with a separate 120-second Steam observation limit and one-second settling interval. It makes `processes[0]["pid"]` the result's `launcher_pid` and persists verified-process ownership. Steam and overlay independently identify PID 6936. The helper does **not** read only `launcher_pid`: `_game_pids()` repeatedly scans all current processes under that root in Session 1, and its Y7 results contained only 6936.
- Steam's retained Y7 AppID log reports one tracked CS2 PID, 6936; overlay reports the same PID; helper sampling saw no other qualifying install-root/Session-1 PID throughout its interval. A descendant outside that root/session, a short-lived intermediate, or replacement between samples remains possible but **not evidenced**. Historical parent PID, exact Y7 creation FILETIME, process tree, all Steam children, and per-thread desktop membership were not retained. No re-exec or alternate-window-owner incident is proved.
- `_largest_visible_window()` calls `EnumWindows` in the helper's current desktop, then associates returned top-level HWNDs with its discovered game PIDs. Y7's zero count proves **B**: no top-level HWND attributable to PID 6936 was discoverable through that helper's current desktop during its scans. It does **not** prove **A**: CS2 never created any top-level HWND. The telemetry argues against a mere visibility/size/owner rejection on the enumerated desktop, because those target HWNDs would have increased `target_pid_hwnd_count` before filtering.
- The interactive launcher explicitly sets `STARTUPINFO.lpDesktop` to `winsta0\\default` for the brokered Steam request and presentation helper. A desktop mismatch is therefore less likely, but Y7 did not log the helper thread's actual desktop/window station, CS2 GUI-thread desktop, or any other desktop's HWNDs. `EnumWindows` is not a cross-desktop/process-tree scan. Windows distinguishes current-desktop and specified-desktop enumeration: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows and https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdesktopwindows .

### Earliest proven Y3-versus-Y7 divergence and renderer stages

- **Earliest retained divergence is before game materialization:** Y3 used an already-running Steam client in UI mode 7; its Steam client-version start was logged at `2026-09-10 13:32:06` KC-01 local and AppID 730 tracked PID 8616 at `14:11:38` local (approximately `21:11:38Z`). Y7's read-only preflight found no Steam process at `12:32:39Z`; the Y7 Steam log shows fresh client startup/UI `0->7` only around `12:44:10Z`, 26 seconds before PID 6936 tracking. This pre-launch difference is proven; causation of the later renderer stall is not. Y3's earlier `steam://close/bigpicture`/mode-7 context is retained in the Y5A handoff.
- **First proved post-process functional divergence:** Y3's launch task passed `WaitingGameWindow` immediately; overlay DXGI setup began about nine seconds after PID 8616 creation, D3D11 swap-chain creation was logged at `21:12:01Z`, and independent WinSta0/Default observer first saw SDL_app HWND **393378** for PID 8616 at `21:12:01.468156Z`. Its recorded creation FILETIME `134335482987865832` corresponds to `21:11:38.7865832Z`. Retained Y7 Steam evidence does **not** show a launch-task/`WaitingGameWindow` transition, so that stage cannot be compared directly. Y7 overlay DXGI setup first appears at `12:45:30Z`, approximately 53-54 seconds after Steam tracked PID 6936; no Y7 swap-chain/SDL milestone is recorded.
- Y7 stage ledger: exact CS2 creation time **not evidenced** (Steam first tracked at `12:44:36Z`); overlay injection **evidenced** at `12:44:37Z`; DXGI preparation **evidenced** `12:45:30Z`; factory hook attempts **evidenced** `12:45:31-36Z` and `12:45:52-53Z`; hooking-mutex failures **evidenced** `12:45:36-37Z`; D3D9/D3D9Ex preparation **evidenced** `12:45:43Z`, Direct3DCreate9 hook call `12:45:53Z`; swap-chain creation **not evidenced**; D3D11 initialization **not evidenced**; SDL_app or any other CS2 HWND **not evidenced**; renderer progress beyond these hooks **not evidenced**. `DXGIFactory*_CreateSwapChain already hooked` describes hook installation, not successful swap-chain creation. The mutex errors are correlated, not proven causal.

### Current timeout architecture, hypotheses, and next diagnostic gate

`change_session_state()` prepares the runtime and durable launch attempt, then calls `launch_prepared_game()`. The Steam adapter sends the brokered request, waits up to 120 seconds for a new verified process and settles for one second, then constructs ownership. `launch_prepared_game()` **after that** calls `ensure_game_on_vdd()`, which starts a new Session-1 helper. `_run_helper()` resolves the VDD and only then sets `deadline = time.monotonic() + 75`. These 75 seconds measure post-discovery current-desktop HWND/presentation opportunity. They do not measure control-plane START, Steam cold start, asynchronous launch request, PID discovery, or initial ownership construction. Stream readiness follows presentation. Y7 nearly exhausted the full 75 seconds with PID 6936 observable. Increasing the timeout merely because claim-to-PID latency was long has no evidentiary basis.

Ranked hypotheses; none established as final root cause:

1. **Delayed or stalled CS2 graphics/window materialization after PID 6936 appeared.** Supports: Y7 did not reach Y3's swap-chain/SDL milestone; DXGI preparation came 53-54 seconds after Steam tracking and hook failures followed. Against: a different-desktop/different-PID HWND remains unexcluded; overlay is not a complete game renderer trace. Missing: game-side startup/renderer events, swap-chain/SDL evidence, all-desktop HWND attribution.
2. **Wrong desktop or different process owns the game HWND.** Supports: helper negative is scoped to its current desktop and game-root/Session-1 PIDs. Against: request/helper explicitly target `winsta0\\default`, Y3 succeeded through this path, helper saw only PID 6936 under the root. Missing: helper/CS2 thread desktop names, full PID/PPID/creation identities, HWND PID/class inventory on relevant desktops.
3. **Steam cold-start/UI/AppID state delayed downstream initialization.** Supports: Y7 Steam was absent at preflight and started only 26 seconds before tracking; Y3 client was warm. Against: no request/auth/task timestamps establish what consumed the apparent earlier 52 seconds or link cold start to the HWND failure. Missing: monotonic launch-stage timing and Steam task/auth events.
4. **Overlay hooking contention or GPU/display initialization issue.** Supports: two mutex failures, late DXGI setup, absent swap-chain record; Y5 pattern was similar. Against: hook failure does not prove game-render failure; VDD discovery succeeded and no Y7 launch-time GPU/driver/device error is retained. Missing: game/Windows graphics events and renderer stage telemetry. No VDD/GPU mutation is justified.

**Proposed source patch scope only; no edits made:** add a single attempt-keyed UTC-plus-monotonic stage trace around preparation and `launch_prepared_game()` in `node-agent/khan_agent/gaming_runtime.py::change_session_state`; record request-issued/request-returned, first candidate and settled process identities including PID, PPID, creation FILETIME, executable/root/session in `node-agent/khan_agent/gaming_launchers.py::SteamLauncherAdapter.launch` and `node-agent/khan_agent/windows_verified_process.py::wait_for_new_game_processes`. In `node-agent/khan_agent/windows_presentation.py::_run_helper` and `_largest_visible_window`, log helper window-station/thread-desktop identity, input desktop, `EnumWindows` error status, all game-root PID identities per sample, and bounded class/PID/TID details for every current-desktop `SDL_app` HWND regardless of whether its PID is the first launcher PID. Capture target CS2 GUI-thread desktop identity where readable; if different, use a read-only explicit-desktop HWND diagnostic. Keep the acceptance filter and 75-second timeout unchanged. Avoid window titles, command-line secrets, or user data.

**Proposed tests, not run because source was not changed:** extend `node-agent/tests/test_steam_async_observation_q38ir.py` and `test_late_steam_launch_authority_q38it.py` for stage timestamps and a multi-PID/late-replacement snapshot; extend `node-agent/tests/test_windows_presentation_kg009e.py` and `test_presentation_startup_probe_q38iu.py` for zero-target-HWND versus alternate-PID SDL_app/desktop-mismatch telemetry, asserting unchanged acceptance and 75-second monotonic boundary. Run focused tests, affected runtime/ownership suite, then node-agent package regression; qualify a Windows package before later runtime use.

**Decision:** another canonical START is **not justified now**. First review, implement, test, and qualify the exact instrumentation under separate source-edit approval. A later single instrumented START requires a fresh commercial/runtime gate and explicit production authorization. No Y8 START, STOP, reboot, Steam/CS2/Sunshine/VDD/Hyper-V action, production-source edit, migration, commit, tag, or push occurred. No source tests or runtime-layer tests were run in Y8; verification comprised retained-log/source inspection, read-only KC-01 time-zone inspection, and read-only DB observation.


## Q38IU-Y9 DIAGNOSTIC INSTRUMENTATION — SOURCE QUALIFIED — 2026-09-14 UTC

**Scope.** Source edits and tests only. Branch `feature/kg009-gaming-runtime-orchestrator`, HEAD `70260fba00b800bef15916cafde229d9d5e3ceda`. The worktree was already substantially dirty; its unrelated changes were preserved. Y9 changed `node-agent/khan_agent/gaming_runtime.py`, `gaming_launchers.py`, `windows_verified_process.py`, `windows_presentation.py`, added `launch_diagnostics.py`, extended `node-agent/tests/test_steam_async_observation_q38ir.py`, `test_late_steam_launch_authority_q38it.py`, `test_windows_presentation_kg009e.py`, `test_presentation_startup_probe_q38iu.py`, and appended this handoff. No migration or schema change.

**Diagnostic records.** `LaunchTrace` writes best-effort `launch_stage` records with UTC, monotonic milliseconds, per-trace elapsed/delta, existing `attempt_id` when authority exists, and `runtime_id`. The create/start runtime path records preparation, managed-session validation, display prerequisites, Steam inventory/readiness, attempt-authority creation, and stream-readiness begin/end. `launch_prepared_game` records entry, adapter return, presentation-helper begin/return. The Steam adapter records baseline creation, adapter entry, broker request begin/return, verified discovery begin/end, and ownership construction. Verified-process observation records baseline, first candidate, additional/replacement candidate, timeout, and settled set. Process facts are bounded to PID, creation FILETIME, Session ID, root-relative executable, root verification, and PPID only when a live psutil process creation timestamp matches the verified FILETIME. No command line or environment is logged. Records before the durable attempt is created use the existing runtime ID; subsequent records use both IDs. Monotonic values provide within-host correlation without relying solely on wall-clock agreement.

The presentation helper receives the same attempt/runtime IDs, records UTC and monotonic absolute/elapsed/delta timing, startup PID/Session identity plus window-station, helper-thread desktop, input-desktop identity/errors, bounded verified PID identity changes/samples, EnumWindows status/error, target HWND and rejection counts/reasons, SDL_app HWND/PID/TID/class/session relationship independent of the original launcher PID, and accepted HWND. It probes target process threads' desktop identities and uses read-only EnumDesktopWindows on up to four different desktops, retaining only up to eight relevant HWND records per desktop. Per-window and scan records emit on change or at five-second intervals; detailed target-HWND records are capped at 16 per scan and 32 per helper, windows and process lists are capped, and telemetry state is capped. Final timeout records the last A–E classification: A no target GUI HWND on inspected desktops, B helper-desktop SDL_app under alternate PID, C related HWND on another safely inspected desktop, D target HWND rejected by existing rules, E accepted path. EnumWindows or relevant desktop-probe failures are explicitly indeterminate. Window titles, raw command lines, credentials, and full process/window dumps are absent.

**Preservation review.** Presentation default and CLI timeout remain 75 seconds and use the same monotonic deadline; Steam observation remains 120 seconds, generic process observation remains 45 seconds with the same settling loop. The target-PID, visibility, unowned-window, rectangle, and 64×64 acceptance gates and VDD placement call remain unchanged. Steam/CS2 arguments, process ownership/cleanup, Sunshine, billing, and control-plane behavior were not changed. Read-only desktop probes do not switch desktops, move foreign windows, alter security, or broaden acceptance. Telemetry failures are best-effort and do not gate the canonical path. A fake-clock regression found and corrected an extra pre-deadline monotonic read during development.

**Validation.** Python compileall passed for the five diagnostic source files and four focused test files. Final focused command from `node-agent`: `./.venv/bin/python -m pytest -q tests/test_steam_async_observation_q38ir.py tests/test_late_steam_launch_authority_q38it.py tests/test_windows_presentation_kg009e.py tests/test_presentation_startup_probe_q38iu.py` — **53 passed**. Affected presentation/Steam/runtime/ownership grouped command covered those four plus verified-process exit, brokered ownership, gaming runtime execution, fail-closed stream readiness, interactive runtime execution, Steam broker request, launch recovery, pending-launch sanitation, gaming launchers, runtime ownership, Windows session binding, gaming session broker, and VDD runtime policy — **204 passed**. Full `./.venv/bin/python -m pytest -q` from `node-agent` — **533 passed, 1 skipped**. `git diff --check` passed. Initial nonfinal runs exposed one static test assertion affected by SDL-only diagnostics, two working-directory-dependent test failures, one fake-clock stall, and one redundant session-ID source-contract failure; these were corrected or rerun from the required directory. No final test failures.

**Source SHA256.**
- `gaming_runtime.py`: `57560ae5dc366c2e2409e792a383656a5bb1619a5beead9c3cae50c1edfa91a5`
- `gaming_launchers.py`: `64b15b3550a3bbe194aa2924b731a6368d9f20db7ec4e83b7a3e72e5833b5d05`
- `windows_verified_process.py`: `0d0be0a205057753f30485546a14895041843161a5c52e72cc5105745dd3a0dd`
- `windows_presentation.py`: `55a8b985588b0fd4aa6836c44f7bb0a1cbca84ed63a9b33adc4eb06e45e40d76`
- `launch_diagnostics.py`: `5ceb1d8ad40fd378fe69ed8dbcd938187ca198a77b685425182f7573e385941f`

**Remaining limits and next candidate scope.** Source tests used Linux-hosted Win32 mocks. No standalone Windows package, KC-01 host, gaming VM, interactive KhanGaming, VDD, Sunshine, or Moonlight runtime validation was performed. Cross-process target window-station identity and inaccessible desktops cannot always be read safely; those outcomes remain diagnostic errors, not absence proof. No game-side or DXGI/ETW swap-chain event was added, so sustained verified-PID/no-HWND evidence narrows a graphics/overlay stall but cannot prove its exact internal stage; correlate later with separately retained Steam/overlay or Windows graphics evidence. The proposed Windows candidate would include only the five changed `khan_agent` Python modules in the existing node-agent runtime, retain the existing dependency/configuration set and launch arguments, and undergo standalone Windows syntax/import/unit qualification before any separately authorized production deployment or canonical START. Y9 performed no packaging, deployment, START, STOP, service control, reboot, Steam/CS2, Sunshine, VDD, Hyper-V, commit, tag, or push.

Y9 final validation detail: the focused command above passed 53 tests; the exact grouped command from `node-agent` was:
```sh
./.venv/bin/python -m pytest -q tests/test_windows_verified_process_exit_q38fp.py tests/test_windows_brokered_ownership_q38df.py tests/test_gaming_runtime_execution_v1.py tests/test_fail_closed_stream_readiness_kg009d3.py tests/test_interactive_runtime_execution_kg009d3.py tests/test_steam_broker_request_q38dt.py tests/test_steam_async_observation_q38ir.py tests/test_launch_recovery_lifecycle_q38iu.py tests/test_presentation_startup_probe_q38iu.py tests/test_pending_launch_sanitation_q38iu.py tests/test_gaming_launchers_kg002.py tests/test_runtime_ownership_kg009d1.py tests/test_windows_presentation_kg009e.py tests/test_late_steam_launch_authority_q38it.py tests/test_windows_session_binding_kg009d2.py tests/test_gaming_session_broker_kg009.py tests/test_vdd_runtime_policy_kg008k22.py
```
It passed 204 tests. Final full rerun `./.venv/bin/python -m pytest -q -rs` passed 533 and skipped one existing Windows installer parser test because PowerShell is unavailable on the Linux source host.

## Q38IU-Y10 WINDOWS DIAGNOSTIC CANDIDATE — QUALIFIED — 2026-09-14 UTC

**Scope and preservation.** Branch `feature/kg009-gaming-runtime-orchestrator`; HEAD `70260fba00b800bef15916cafde229d9d5e3ceda`. The substantial modified and untracked source worktree was present before Y10 and was preserved. Y10 created a local package and temporary qualification artifacts, staged the archive on KC-01, and appended this handoff; it did not edit product source, run a migration, or change schema. No commit, tag, or push occurred.

**Candidate authority.** Linux archive: `/tmp/khan-node-agent-q38iu-y10-windows-diagnostic-candidate-20260914T103840Z.tar.gz`; **182,621 bytes**, SHA256 `b82a90f217261051e03873ff932f231e2bd44fc4db7b50bfff63b172a54bb3b0`, **129 files**. Archive sanitation passed: no duplicate/unsafe members, private configuration or identity files, virtual environment, cache, compiled files, or transient files. Full source-to-archive/extraction parity passed, including these five Y9 diagnostic modules (source = package = extraction SHA256):

| Module | SHA256 |
| --- | --- |
| `gaming_runtime.py` | `57560ae5dc366c2e2409e792a383656a5bb1619a5beead9c3cae50c1edfa91a5` |
| `gaming_launchers.py` | `64b15b3550a3bbe194aa2924b731a6368d9f20db7ec4e83b7a3e72e5833b5d05` |
| `windows_verified_process.py` | `0d0be0a205057753f30485546a14895041843161a5c52e72cc5105745dd3a0dd` |
| `windows_presentation.py` | `55a8b985588b0fd4aa6836c44f7bb0a1cbca84ed63a9b33adc4eb06e45e40d76` |
| `launch_diagnostics.py` | `5ceb1d8ad40fd378fe69ed8dbcd938187ca198a77b685425182f7573e385941f` |

**Package-contained Linux qualification.** Compile passed for 108 Python files. Focused tests: **53 passed**. Affected grouped tests: **203 passed, 1 deselected**. Full package suite with `-m "not source_tree_only"`: **531 passed, 1 skipped, 2 deselected**; the skip was the Windows PowerShell parser unavailable on Linux. Post-test file-set and source/archive/extraction parity passed for all 129 files; archive bytes and SHA256 remained exact.

**KC-01 staged and standalone Windows qualification.** Archive staged at `C:\KhanCloudBuild\khan-node-agent-q38iu-y10-windows-diagnostic-candidate-20260914T103840Z.tar.gz`; staged bytes **182,621** and SHA256 `B82A90F217261051E03873FF932F231E2BD44FC4DB7B50BFFF63B172A54BB3B0`, matching Linux. The final read-only `Test-Path -LiteralPath ... -PathType Leaf` returned `True`. The five extracted modules matched the source hashes above. Standalone Windows compile and import authority passed for all five; Win32 symbol/ABI configuration, read-only desktop probe, and safe session fallback passed. The qualification script made no launch or presentation call. Windows focused tests: **54 passed**. Full package suite with the source-tree marker excluded: **530 passed, 2 skipped, 2 deselected**; the two skips were Linux-only bootstrap contracts. The real PowerShell parser test passed separately (**1 passed**). The affected Windows/VDD runtime set finished **30 passed, 1 deselected**. An earlier broad package-side attempt produced **1 failed, 150 passed** because a test marked `source_tree_only` read the separate `khan-virtual-display` repository tree, intentionally absent from the node-agent runtime archive. That was a test-environment scope error, not a product-source failure; the correctly scoped affected run passed. Final Windows post-test archive/extraction parity passed for all **129 files**, with **182,621 bytes** and the same SHA256.

**Final read-only KC-01 live-state parity.** Before snapshot `2026-09-14T10:45:56.5112271Z`; final probe `2026-09-14T11:24:51.1627477Z`. Both showed KhanCloudAgent `Running`, PID **8864**, start mode `Auto`; Sunshine count **1**, PID **10940**, Session **1**; Steam count **0**; CS2 count **0**. Installed live module results were identical before and after:

| Installed live module | Unchanged SHA256 / state |
| --- | --- |
| `gaming_runtime.py` | `0E008111A3D925CE8E18E9B26CFC147188679B5503FC00F0DEC027469864FE18` |
| `gaming_launchers.py` | `25DA16E356B2691AD30461F0BB594DB030F79136F468C267AD71BC53D9F7AB88` |
| `windows_verified_process.py` | `623DB2D703C8F3B68A563CE9792996B23354F4274EDF115F044E941186BAFB57` |
| `windows_presentation.py` | `4F5A0550E357AE655C36A22F644849CC20A2CE445CA637714F863ABD4A65EABA` |
| `launch_diagnostics.py` | absent before and after |

These installed hashes differ from the staged candidate hashes, and its new `launch_diagnostics.py` is absent from the live runtime: **the candidate is staged and NOT installed**. No unintended live Agent, Sunshine, Steam, CS2, or installed-module change was detected. Y10 performed **no START or STOP**, agent service control, Steam/CS2 launch or kill, Sunshine restart, VDD/Hyper-V action, reboot, database/session/job/wallet/reservation mutation, or production deployment.

**Decision and limit.** The candidate is qualified for a separately authorized, guarded transactional deployment; no deployment has occurred. Standalone Windows package qualification and a stable KC-01 host do not establish gaming-VM, interactive KhanGaming, VDD presentation, Sunshine stream readiness, or Moonlight end-to-end runtime success. Those remain for subsequent authorized runtime validation. No Y10 migration/schema work was required; no final test failures remain after the `source_tree_only` exclusion.

## Q38IU-Y24B WINDOWS-NATIVE 1:1 PRESENTATION CONTRACT — SOURCE QUALIFIED — 2026-09-18 UTC

**Y23C10 RCA conclusion.** The live Y23C10 result
`PASS_VDD_1TO1_CS2_1920X1080` established that VDD activation, primary
selection, or moving an already-created HWND is insufficient when the VDD
backing DEVMODE remains 3840x2160 while Session-1 presentation geometry and
the requested stream are 1920x1080. The resulting CS2 SDL HWND was
960x540 at DPI 192. After the actual VDD DEVMODE was changed to
1920x1080@60 before renderer/window initialization, while the VDD remained
presentation-primary, the new CS2 HWND was visible, non-iconic, uncloaked,
on the VDD, and had 1920x1080 window/client/DWM geometry at naturally
reported DPI 96. Q38IU-Y24B implements that pre-launch 1:1 contract; it does
not mutate global DPI or AppCompat DPI state.

**Implementation architecture.**

- The existing `windows_presentation.py` KHC0001/Khan VDD
  `EnumDisplayDevicesW` discovery remains the single dynamic display
  authority. No display number, monitor handle, coordinate, LUID, physical
  display identity, or monitor order is hardcoded.
- The managed-session helper now establishes exactly
  1920x1080@60 before first launch and stopped-runtime relaunch. It enumerates
  the resolved VDD modes, requires the exact mode, copies the current DEVMODE
  to preserve position/color depth, changes only width/height/refresh, runs
  `ChangeDisplaySettingsExW(..., CDS_TEST)`, applies with
  `CDS_UPDATEREGISTRY`, and verifies the final width/height/refresh.
- If the resolved VDD is not already primary, the helper stages a dynamic
  position-only transaction: the VDD becomes primary at (0,0), every other
  monitor retains its mode and relative placement, and the global transaction
  is applied. Physical display resolution is not changed. There is no
  topology rollback, VDD restart, Steam restart, or Sunshine restart.
- Final pre-launch proof requires one VDD topology entry, one primary monitor
  equal to that dynamically resolved VDD, and Session-1 VDD monitor geometry
  equal to 1920x1080. Exit codes 40-47 distinguish unresolved VDD, missing
  mode, CDS_TEST rejection, apply failure, post-apply mode mismatch,
  non-primary VDD, monitor-geometry mismatch, and helper/dependency failure.
  All propagate as `GamingRuntimeError` before `prepare_game_launch`.
- `gaming_runtime.py` executes the contract after authoritative managed
  session validation and any existing VDD policy activation, but before Steam
  inventory preparation, launch-attempt creation, Steam launch authorization,
  or game launch. Successful evidence is persisted as
  `presentation_contract`.
- Post-launch presentation remains bound to the D1-authoritative game PID,
  expected install root, and managed Session ID. It verifies the existing
  top-level HWND in place rather than moving it: visible, non-iconic,
  uncloaked, on the dynamically resolved VDD, exact 1920x1080 client
  geometry, and exact 1920x1080 presentation-monitor geometry. Window,
  client, DWM-frame, and DPI facts are emitted as bounded diagnostic evidence;
  DPI is not an acceptance mutation. A 960x540 client or physical-monitor
  HWND fails readiness and enters the existing ownership cleanup path.
- Existing D1 launch authority, failed-readiness cleanup, managed-session,
  Steam/Sunshine, STOP, sanitation, and reconciliation behavior is preserved.

**Exact files changed in Q38IU-Y24B.**

- `node-agent/khan_agent/windows_presentation.py`
- `node-agent/khan_agent/gaming_runtime.py`
- `node-agent/khan_agent/gaming_launchers.py`
- `node-agent/tests/test_windows_presentation_contract_q38iu_y24b.py`
  (new)
- `node-agent/tests/test_windows_presentation_kg009e.py`
- `node-agent/tests/test_runtime_ownership_kg009d1.py`
- `node-agent/tests/test_presentation_startup_probe_q38iu.py`
- `node-agent/tests/test_windows_session_binding_kg009d2.py`
- `node-agent/tests/test_graphics_init_diagnostics_q38iu.py`
- `.codex/KHAN_CLOUD_DEVELOPMENT_HANDOFF.md`

`gaming_launchers.py`, `gaming_runtime.py`, and
`test_runtime_ownership_kg009d1.py` already contained valuable modified
work before Y24B. `windows_presentation.py` and several updated focused
tests already existed as valuable untracked work. Their prior content was
preserved. The clean tracked
`test_windows_session_binding_kg009d2.py` became modified in this batch,
and the new Y24B test is the only new product/test path.

**Tests added/modified.** The new Y24B module covers dynamic VDD naming,
successful enumerate/CDS_TEST/apply/post-verify behavior, unresolved VDD,
missing mode, CDS_TEST rejection, apply failure, post-apply DEVMODE mismatch,
non-primary VDD, monitor-geometry mismatch, successful exact game
presentation, 960x540 client rejection, wrong-monitor rejection,
pre-launch failure before game preparation, and position-only primary
transaction behavior. Existing presentation tests now require verify-in-place
behavior and no `SetWindowPos`. The D1 stop/start test proves ordering
`display_contract -> prepare -> launch` and persistence without weakening
ownership assertions. Existing session binding, startup-probe, and graphics
diagnostic source contracts were updated for this deliberate policy change.

**Syntax validation.** Final command from `node-agent`:
`.venv/bin/python -m py_compile khan_agent/windows_presentation.py khan_agent/gaming_runtime.py khan_agent/gaming_launchers.py tests/test_windows_presentation_contract_q38iu_y24b.py tests/test_windows_presentation_kg009e.py tests/test_runtime_ownership_kg009d1.py tests/test_presentation_startup_probe_q38iu.py tests/test_windows_session_binding_kg009d2.py tests/test_graphics_init_diagnostics_q38iu.py`
— PASS. Focused `git diff --check` on all Y24B paths — PASS.

**Focused result.** Final command from `node-agent`:
`.venv/bin/python -m pytest -q tests/test_windows_presentation_contract_q38iu_y24b.py tests/test_windows_presentation_kg009e.py tests/test_vdd_runtime_policy_kg008k22.py tests/test_runtime_ownership_kg009d1.py tests/test_windows_session_broker_kg009d2.py tests/test_windows_session_integration_kg009d2.py tests/test_launch_recovery_lifecycle_q38iu.py tests/test_pending_launch_sanitation_q38iu.py`
— **137 passed**.

**Broader result.** The final 21-module Windows
presentation/gaming/runtime/ownership/session/cleanup/graphics command
including the Y24B module — **243 passed**.

**Full node-agent regression.** Final
`.venv/bin/python -m pytest -q -rs` from `node-agent` —
**552 passed, 1 skipped**. The single existing skip is the Windows installer
PowerShell-parser test because PowerShell is unavailable on the Linux source
host.

**Intermediate failures, all corrected and superseded.** The first existing
presentation/policy run had 50 passes and 3 stale source-contract failures
that still required `SetWindowPos`. The first new focused run had 62 passes
and 3 fake-DWM ABI failures in the test double. The first broader run had
233 passes and 3 further stale source-contract assertions. The first full run
had 550 passes, 1 skip, and 1 remaining stale `SetWindowPos` assertion.
The implementation was not weakened; test doubles were corrected and source
contracts were deliberately updated to require the new verify-in-place
behavior. The final focused, broader, and full results above supersede all
intermediate runs.

**Remaining gate.** Source tests used Linux-hosted Win32 mocks. No standalone
Windows package, candidate/source-package parity check, KC-01 deployment,
gaming VM, interactive KhanGaming, real VDD mode mutation, Steam/game launch,
Sunshine readiness, or Moonlight validation occurred. No migration or schema
change was required.

DEPLOYED=NO

COMMIT=NO

TAG=NO

PUSH=NO


## Q38IU-Y25 CANDIDATE FREEZE + STANDALONE WINDOWS QUALIFICATION - PASS - 2026-09-18 UTC

**Authority and preservation.** Branch `feature/kg009-gaming-runtime-orchestrator`;
HEAD `70260fba00b800bef15916cafde229d9d5e3ceda`. The authoritative dirty
worktree was preserved. Y25 changed no product/test source, database, billing,
wallet, reservation, schema, service, process, display, VDD, Sunshine, Steam,
game, Hyper-V, or live runtime state. Its only repository write was this
handoff append.

**Candidate.**
`/tmp/khan-node-agent-q38iu-y25-windows-candidate-20260918T141213Z.tar.gz`;
192,502 bytes; SHA256
`6ae7ee382d14e1da82bd8e222c8d2f526f8a393e7ecdcd0ffa2cc872282aaa0f`;
131 package-owned files. Sanitation passed with no duplicate/unsafe members,
private configuration/identity, venv, cache, compiled, log, backup, rejected,
or transient files. Linux extraction:
`/tmp/q38iu-y25-qual-20260918T141213Z`.

**Source/package/extraction parity.** Full 131-file name and SHA256 parity
passed before and after Linux tests. Archive member, Linux extraction, and
Windows extraction matched source for every file. Required hashes (source =
archive member = Linux extraction = Windows extraction):

| Module | SHA256 |
| --- | --- |
| `gaming_runtime.py` | `9f37d37db393b3608b6247ef40fe523b20c572a2af2edfbbcbcb5d46b157e596` |
| `gaming_launchers.py` | `3d2763eeb7e1a6e331de2938235d8337109faec87799ae5df605aaddccdff089` |
| `windows_presentation.py` | `70aaa5c1e8ef2acd2c5c49a2bb96767652766ee4d57ddbd5d415377d9aef9494` |
| `windows_verified_process.py` | `0d0be0a205057753f30485546a14895041843161a5c52e72cc5105745dd3a0dd` |
| `runtime_ownership.py` | `03a362559698ef45e89c1ecc2b4e21f744589f119591f8d6222f19fdf3ead28b` |
| `windows_interactive.py` | `dc622f9a7c5ce9235f887e67a563fd3e2148df57c77534c5c529985cb220a335` |
| `windows_session_broker.py` | `496915510e0c630d48e5477f6a1b793c5b26ebe3406081c4db4fc2444af472ab` |

Static inspection and focused/direct-mock tests proved the packaged Y24
contract: dynamic Khan VDD resolution; exact 1920x1080@60 initial request;
exact mode enumeration; `CDS_TEST`; actual DEVMODE application;
presentation-primary enforcement; post-apply DEVMODE and Session-1 geometry
verification; pre-launch ordering; post-launch authoritative-PID visible,
non-iconic, uncloaked, dynamic-VDD, exact-client verification in place; and
no production `SetWindowPos` correction.

**Linux qualification.** Source syntax PASS; focused 137 passed; reconstructed
affected 21-module run 240 passed; full source 552 passed, 1 skipped
(PowerShell parser unavailable). Extracted package compiled 110 Python files
and imported all seven required modules from candidate paths. Correct
package-scoped results: focused 135 passed, 2 deselected; affected 238 passed,
2 deselected; full 550 passed, 1 skipped, 2 deselected. An earlier unmarked
focused attempt had 136 passed and one source-tree-only failure because the
separate `khan-virtual-display` repository was correctly absent; this was
not a product failure.

**KC-01 staging and Windows standalone qualification.** Staged only at
`C:\KhanCloudBuild\khan-node-agent-q38iu-y25-windows-candidate-20260918T141213Z.tar.gz`;
standalone extraction:
`C:\KhanCloudBuild\Q38IU-Y25-qual-6ae7ee38\source`. Windows size/hash,
131-file integrity, seven required hashes, 110-file syntax, seven-module
import authority, Win32 ABI/symbols, read-only desktop probe, and safe session
fallback passed. The historical guard reported
`NO_LAUNCH_OR_PRESENTATION_CALLS=PASS`.

The first real-Windows focused run had 128 passed, 7 failed, 2 deselected:
seven older Linux-oriented integration tests did not mock the new Y24
pre-launch entrypoint on genuine Windows. Five blocked before helper launch;
two failed at session-token acquisition before child/helper creation or any
presentation mutation. No live mutation occurred. An external pytest-only
autouse fixture then replaced only
`gaming_runtime._establish_presentation_contract` for integration tests;
candidate files remained unchanged. Safe Windows focused: 135 passed,
2 deselected; affected: 238 passed, 2 deselected; full: 549 passed, 2 skipped,
2 deselected (two Linux-only contracts). The Y24 module separately passed
13/13 without the global fixture using its Win32 fakes. Real PowerShell parser:
1/1 passed. Final Windows archive/extraction parity passed for all 131 files.

**Live preservation.** Pre `2026-09-18T14:15:45.7526031Z`; final
`2026-09-18T14:22:34.8205503Z`. Both showed KhanCloudAgent Running/Auto PID
9020; Sunshine PID 13476 Session 1; Steam PID 10072 Session 1; CS2 count 0.
All seven installed hashes were identical before/after. Installed candidate-
changed hashes remained old: `gaming_runtime.py`
`57560AE5DC366C2E2409E792A383656A5BB1619A5BEEAD9C3CAE50C1EDFA91A5`,
`gaming_launchers.py`
`64B15B3550A3BBE194AA2924B731A6368D9F20DB7EC4E83B7A3E72E5833B5D05`,
and `windows_presentation.py`
`8F411B390BFF08DB0F8B65CB239D521A20016154F63E15253C628FADD6FFBBE2`.
They differ from Y25, directly proving the staged candidate is not installed.
No START or STOP was run.

**Decision and limit.** Candidate is qualified for the separately authorized
controlled transactional deployment gate. Standalone qualification does not
prove a real VDD transition, game presentation, Sunshine readiness, or
Moonlight streaming. Next gate: controlled transactional KC-01 deployment ->
installed/source/candidate parity -> agent health -> commercial/admission
cleanliness -> one fresh canonical RAW START -> launch timing -> Moonlight
visual validation -> canonical STOP -> cleanup/sanitation/repool verification.

DEPLOYED=NO

COMMIT=NO

TAG=NO

PUSH=NO

## Q38IU-Y26 CONTROLLED TRANSACTIONAL KC-01 DEPLOYMENT - FAIL / ROLLED BACK - 2026-09-18 UTC

**Authority and preflight.** Branch remained
`feature/kg009-gaming-runtime-orchestrator` at HEAD
`70260fba00b800bef15916cafde229d9d5e3ceda`; the authoritative dirty worktree
was preserved. Linux and staged KC-01 Y25 archives both matched 192,502 bytes
and SHA256
`6ae7ee382d14e1da82bd8e222c8d2f526f8a393e7ecdcd0ffa2cc872282aaa0f`.
Fresh extraction `C:\\KhanCloudBuild\\Q38IU-Y26-deploy-6ae7ee38` contained 131
files and all seven required module hashes matched Y25. Immediately before
mutation, DESKTOP-4ROCVUH had KhanCloudAgent Running/Auto PID 9020, its two
expected runtime Python processes, Sunshine PID 13476 Session 1, Steam PID
10072 Session 1, and zero CS2. There was no deployment process, rename canary,
or dependency probe. Three September 8-10 historical rollback trees were
structurally complete and no active transaction existed. VDD/monitor/display
PnP devices were OK with problem code 0. Focused source transaction tests:
87 passed.

**Supported transaction and failure.** Y26 invoked the packaged
`deploy\\universal-bootstrap.ps1` exactly once with the fresh extracted source
and installed `C:\\ProgramData\\KhanCloud\\Agent\\config.yaml`; direct
`install-runtime.ps1`, the old updater, and prior one-shot deployments were not
used. The supported engine stopped only KhanCloudAgent, proved runtime-process
quiescence and rename readiness, and created fresh rollback authority
`C:\\ProgramData\\KhanCloud\\Agent\\runtime.rollback.9736ecb9aee4466891107c19a48a1e4b`.
Dependency installation/import acceptance and compile passed. The packaged
Windows pytest gate then failed: 535 passed, 14 failed, 2 skipped, 2 deselected.
The failures were older integration tests exercising the Y24 presentation
entrypoint without the external qualification-only safe fixture. The engine
reported `Khan Cloud node-agent tests failed`, never reached heartbeat or
commit, entered `ROLLBACK WINDOWS RUNTIME`, restored the prior runtime, and
restarted the previously running Agent. No retry occurred.

**Rollback proof and preservation.** Post-rollback KhanCloudAgent was
Running/Auto at PID 17880 with the expected two-process service chain. The
fresh GUID rollback directory was absent because it had been moved back to
the authoritative `runtime`; only the same three historical rollback trees
remained. Installed imports for all seven required modules passed from the
live restored runtime. Config remained exactly 888 bytes with SHA256
`960B7C8B66D15FBE49597B22A7063A288391AE7D1ED3F20299A7AED728CC1189`.
All seven installed hashes returned to their pre-deploy values. Four already
matched Y25, but `gaming_runtime.py`
`57560AE5DC366C2E2409E792A383656A5BB1619A5BEEAD9C3CAE50C1EDFA91A5`,
`gaming_launchers.py`
`64B15B3550A3BBE194AA2924B731A6368D9F20DB7EC4E83B7A3E72E5833B5D05`,
and `windows_presentation.py`
`8F411B390BFF08DB0F8B65CB239D521A20016154F63E15253C628FADD6FFBBE2`
remain the prior installed generation and do not equal Y25. Therefore Y25 is
not installed and full installed-candidate parity is inapplicable/failed.

The packaged test phase unexpectedly launched CS2 PID 14004 in Session 1 at
`2026-09-18T14:44:18.6009225Z`, so the absolute Y26 preservation condition was
violated and the gate is FAIL. No manual kill, canonical START/STOP, or Steam
action was issued. CS2 exited naturally before the final snapshot; final count
was zero. Sunshine PID 13476 and Steam PID 10072 retained their original start
times and Session 1 throughout. Final VDD/monitor/display PnP identity/status
matched preflight (all OK/problem code 0). No intentional VDD action was
issued, but exact Session-1 mode/topology was not re-probed, so PnP parity
does not exclude a transient test-side display mutation. No Sunshine, Steam,
Hyper-V, reboot, credential, billing, wallet, reservation, or database mutation
was performed by Y26. Transaction logs are under
`/tmp/q38iu-y26-transaction-20260918T144357Z`.

**Decision and next gate.** `DEPLOYMENT_STATUS=FAIL`; `DEPLOYED=NO`;
`ROLLED_BACK=YES`. The Y25 candidate must not be retried unchanged through
this installer because its packaged Windows test phase is not live-safe. The
fresh canonical RAW START/Moonlight/STOP E2E gate remains blocked until a
separate development and qualification gate produces an immutable candidate
whose supported transactional install cannot launch game/display behavior.

COMMIT=NO

TAG=NO

PUSH=NO

## Q38IU-Y27C WINDOWS DEPLOYMENT TEST-SAFETY BOUNDARY + CANDIDATE QUALIFICATION

**Root cause.** Y26's transactional deployment invoked
`pytest -q -m "not source_tree_only"` from both Windows deployment paths.
That negative selection admitted every packaged test except the two explicitly
source-tree-only tests, including lifecycle tests capable of calling real
Steam/game launch and VDD presentation code. The Y24 pre-launch presentation
contract also made 14 older lifecycle/control-plane/VDD-policy/ownership tests
stale on real Windows: their synthetic launch/readiness boundaries did not
provide synthetic presentation evidence, so they blocked at the earlier Y24
gate. Y25's external autouse fixture concealed that test defect and was not
part of the candidate.

**Exact 14-test repair.** Production presentation enforcement and ordering
were not changed. The control-plane bridge test now supplies one local
successful presentation proof. The shared `_good_environment` in
`test_gaming_runtime_execution_v1.py` supplies the same proof for its six
affected create/lifecycle/adapter tests. The two downstream launch/readiness
failure tests in `test_runtime_ownership_kg009d1.py` locally mock only the
presentation contract so they still reach their intended synthetic failures.
The shared session fixture in `test_vdd_runtime_policy_kg008k22.py` supplies
synthetic evidence for its five affected policy/session tests; its ordering
assertion now explicitly proves
`policy -> presentation_contract -> prepare_game`. The dedicated Y24
contract-failure test remains unweakened and still proves presentation failure
blocks before preparation. The exact 14 node IDs finished **14 passed**.

**Deployment-safe marker design and exact selection.** `pyproject.toml`
registers `deployment_safe` as an explicitly audited side-effect-free
installed-Windows marker. Both `deploy/install-runtime.ps1` and
`deploy/apply-runtime-update.ps1` now contain exactly
`& $Python -m pytest -q -m "deployment_safe"`; neither contains the old
negative expression. The selected subset is exactly **80 tests**:

- 7 tests in `test_deployment_test_safety_q38iu_y27c.py`;
- 7 individually marked pure/synthetic D1 ownership tests in
  `test_runtime_ownership_kg009d1.py`;
- all 21 static installer-transaction tests in
  `test_windows_installer_transaction_kg009d3.py`;
- all 13 fully faked Y24 Win32 presentation-contract tests in
  `test_windows_presentation_contract_q38iu_y24b.py`;
- all 9 static runtime-dependency contract tests in
  `test_windows_runtime_dependencies_q38fc.py`;
- all 23 static universal-bootstrap/service-host contract tests in
  `test_windows_universal_bootstrap.py`.

No lifecycle/control-plane/VDD-policy module was marked wholesale. The marker
selection collects **80/560**, deselecting 480 ordinary tests, so a future
unmarked test is not admitted automatically.

**Regression guards.** New `tests/conftest.py` activates only for marked
tests and replaces 16 live mutation entrypoints with fail-closed tripwires:
runtime presentation/policy/prepare/launch/cleanup, launcher preparation and
launch, interactive process creation, VDD restart/activation/policy
apply/restore, post-launch presentation, and ownership termination. The
dedicated safety tests require the exact positive command in both deployment
scripts, reject the former negative expressions, verify marker registration,
candidate-local imports, dependency imports, JSON-safe pure ownership state,
and the complete tripwire set. This fixture does not alter ordinary pytest
runs and was not used to repair the 14 stale tests.

**Linux qualification.** Python `py_compile` for all changed Python/test
files passed; focused `git diff --check` passed. Final results from
`node-agent`:

- exact formerly failing tests: **14 passed**;
- Y24 presentation contract: **13 passed**;
- installer/deployment transaction matrix: **90 passed, 1 skipped** (the
  existing PowerShell-parser skip on Linux);
- affected 22-module gaming/runtime/ownership/session/VDD matrix:
  **245 passed**;
- full source suite: **559 passed, 1 skipped**;
- positive deployment-safe subset: **80 passed, 480 deselected**;
- extracted-candidate compile: **112 Python files**; critical imports PASS;
  extracted safe subset: **80 passed, 480 deselected**.

An initial exact-14 run exposed only a synthetic fixture shape mistake
(dictionary versus broker object); after correcting the fixture interface the
same 14 node IDs passed. One initial new pure-state assertion was corrected to
account for derived inspection fields. These intermediate test-only failures
are superseded by the final results above.

**New sanitized candidate.** Linux archive:
`/tmp/khan-node-agent-q38iu-y27c-windows-candidate-20260923T103953Z.tar.gz`;
**193,483 bytes**; SHA256
`55425b3da2bf3c0bf85962812c1a77975c679c0cd6fef0dafdf3609a57b9b313`;
**133 files**. Inventory was sorted and unique; the archive used normalized
mtime/owner/group and deterministic gzip metadata. Sanitation found no
`.git`, venv, pytest/cache directories, bytecode, logs, backup/reject files,
private config, identity, credentials, secrets, or runtime state. Complete
source/archive/Linux-extraction parity passed before and after testing.

**Windows standalone qualification.** The archive was staged but not
installed at
`C:\KhanCloudBuild\khan-node-agent-q38iu-y27c-windows-candidate-20260923T103953Z.tar.gz`
and extracted only to
`C:\KhanCloudBuild\Q38IU-Y27C-qual-55425b3d\source`. Staged size/hash,
133-file inventory, every manifest hash, archive/extraction parity, 112-file
in-memory Python compile, and all seven critical candidate-local imports
passed. Real Windows collection listed exactly **80/560** tests. The final
positive subset passed **80 passed, 480 deselected**. Eight live-state samples
during pytest and the immediate post-test comparison were identical; final
candidate file/hash parity also passed. The first harness attempt stopped
before pytest and before monitoring because Windows PowerShell corrupted a
multiline `python -c` argument; a staged file-based checker fixed that
qualification transport defect without changing or rebuilding the candidate.

**Pre/post live preservation evidence.** Independent snapshots were
`2026-09-23T10:47:08.9306285Z` and
`2026-09-23T10:55:01.8646481Z`; comparison excluding only collection time
was byte-equivalent. KhanCloudAgent was already `Stopped`, start mode
`Auto`, PID 0 before qualification and remained exactly so; no service
control was issued. Sunshine remained PID **18052**, Session **1**, start time
`2026-09-23T10:22:22.1038270Z`. Steam remained absent and CS2 count remained
zero. Screen topology remained one `WinDisc` primary at 1024x768; all
display/monitor PnP entries remained OK/problem code 0; Khan VDD remained
1920x1080@60. All seven installed live hashes were identical before, during,
and after. Installed `gaming_runtime.py`, `gaming_launchers.py`, and
`windows_presentation.py` retain the old/Y26 rollback-generation hashes
`57560AE5...FA91A5`, `64B15B35...B5D05`, and
`8F411B39...FBBE2`, rather than candidate hashes
`9f37d37d...e596`, `3d2763ee...f089`, and
`70aaa5c1...9494`. The live installed runtime therefore remains the old/Y26
rollback generation.

**Status and exact next gate.** No migration/schema work was required.
`DEPLOYED=NO`; `RAW START=NO`; `RAW STOP=NO`; `REBOOT=NO`;
`COMMIT=NO TAG=NO PUSH=NO`. The exact next gate is separate explicit
authorization for a guarded transactional deployment of this exact SHA256
through the supported universal-bootstrap/install-runtime path, preceded by a
fresh live preflight that accounts for the already-stopped Agent. After
deployment, prove installed/candidate parity and service/control-plane health;
do not proceed to a commercial RAW START/STOP without a later distinct
authorization.
