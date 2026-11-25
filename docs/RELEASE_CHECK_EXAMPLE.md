# How a failed release check changes a project Skill

In this fictional project, two Codex chats work on different parts of a release.
One maintains the checklist. The other checks the packaged app. Follow one
finding from the original conversation into a change a fresh chat can use.

[Offline interactive copy](release-check-example.html) · [Install Dialogue Bridge](../README.md#install-in-codex)

On GitHub, use **Download raw file** on the HTML source page, then open the saved
file in a browser. The walkthrough below also works directly on GitHub.

## 1. Open the original finding

The planning chat records the starting rule:

> Run the smoke check from the source checkout.

The packaging chat later records a different result:

> The source check passed, but the release archive failed with ModuleNotFoundError: No module named 'release_helper'.

The replay runs both checks. The source command exits with `0`. The original
archive exits with `1` from a clean working directory.

## 2. Review a focused revision

The packaging chat proposes a revision citing both source messages. The existing
rule stays in effect while the proposal is pending. Once approved in the
scripted replay, the planning chat's dependent view is marked for review. The
packaging chat's separate view has no dependency on this rule and stays current.

The proposed project edit applies to `docs/release-checks.md` and the project's
`.agents/skills/release-check/SKILL.md`:

```diff
 Run the smoke check from the source checkout.
+Then run the packaged app from a clean directory.
```

## 3. Check what a fresh chat can pick up

The replay opens the shared space as a fresh reader and retrieves the revised
rule and its original evidence. The reader uses the Bridge project edit actions
to preview and, after scripted approval, apply one diff per file. The project
proposal can also be made directly from selected evidence. A separate reader
checks the approved Skill diff and its original finding, then the replay rebuilds
the archive with the missing helper and runs the packaged check again:

```text
Fixed archive: exit 0. Release smoke check passed.
```

The replay uses the Bridge runtime with fictional transcripts and scripted
decisions. The smoke commands run against real temporary archives. In a live
Codex chat, the user reviews the diff before approval.

## Replay the example

From the repository root, use the Python interpreter from an environment
[prepared by this checkout's `setup.py`](../README.md#install-in-codex):

```text
python -B tools/release_check_demo.py
```

The replay uses a temporary project and registry. It removes both on exit.
All source messages are fixtures and model calls are disabled.

Could you find why the new check was added and tell which chat needed to review
its plan? [Share what you found](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose).
