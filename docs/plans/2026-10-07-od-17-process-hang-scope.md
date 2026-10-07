# OD-17 Process Hang Scope Fix

## Goal

Restrict `ProcessHangPlaybook` recovery actions to descendant processes of the
running VECTOR process so unrelated system processes can never be killed.

## Plan

1. Add a regression test that fails if `psutil.process_iter()` is called,
   exposes one high-CPU descendant through `Process().children(recursive=True)`,
   and keeps a separate high-CPU non-descendant outside that list.
2. Confirm the regression test fails against the current system-wide scan.
3. Replace the system-wide iterator with recursive child discovery and retain
   the existing CPU threshold, kill behavior, exception handling, and result
   contract.
4. Update the existing process-hang test to mock the new discovery boundary.
5. Compile every touched Python file and run the resilience playbook tests.

## Risk

Low: the playbook is dormant, and the change only narrows eligible processes.
The main compatibility detail is that child processes expose CPU/name/PID via
methods/properties rather than the `info` dictionary populated by
`process_iter(attrs=...)`.
