"""The Actions run stays review-first and skips when it cannot do useful work."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/unsplash-run.yml")


def _plan_script(text: str) -> str:
    plan = text.split("- name: Plan photos", 1)[1]
    return plan.split("- name: Upload review and logs", 1)[0]


def test_unsplash_run_skips_without_secrets_and_never_writes_on_a_schedule() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert 'cron: "0 16 * * *"' in text
    assert "ENABLE_UNSPLASH_SCHEDULE" in text
    assert "Unsplash daily run skipped:" in text
    assert "The schedule never applies changes." in text
    assert "Unsplash run skipped: missing" in text
    assert "Add UNSPLASH_ACCESS_KEY, UNSPLASH_SECRET_KEY, and UNSPLASH_USER_TOKEN" in text
    assert "Settings → Secrets and variables → Actions." in text
    assert "Unsplash daily run skipped: sync found no new photos." in text
    assert "actions/upload-artifact@v4" in text
    assert "state/review.csv" in text
    assert "state/review.json" in text
    assert "state/logs/" in text
    assert "if-no-files-found: warn" in text
    assert "actions/cache@v4" in text
    assert "path: state" in text
    assert "key: upw-state-${{ github.run_id }}" in text
    assert "upw-state-" in text
    assert "contents: read" in text
    assert "group: unsplash-run" in text
    assert "set -x" not in text
    assert ".env" not in text.split("path: |", 1)[1]

    plan = _plan_script(text)
    assert "args+=(suggest)" in plan
    assert '[ "$EVENT_NAME" = "schedule" ]' in plan
    assert '[ "$EVENT_NAME" = "workflow_dispatch" ]' in plan
    yes_line = next(line for line in plan.splitlines() if "--yes" in line)
    assert "args+=(--yes)" in yes_line
    assert yes_line.strip().startswith("args+=(--yes)")
    dispatch = plan.split('[ "$EVENT_NAME" = "workflow_dispatch" ]', 1)[1]
    assert "args+=(--yes)" in dispatch.split("else", 1)[0]
    schedule = plan.split('[ "$EVENT_NAME" = "schedule" ]', 1)[1].split("elif", 1)[0]
    assert "--yes" not in schedule
    assert "suggest" in schedule
