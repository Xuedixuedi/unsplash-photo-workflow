"""`upw` command line. Writes happen only with `--yes`."""

from __future__ import annotations

import json
import os
import secrets
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path

import typer

from upw.adapters.oauth import wait_for_code
from upw.adapters.unsplash import UnsplashClient, authorize_url
from upw.core.applier import apply_plan
from upw.core.pipeline import suggest as build_suggestions
from upw.core.pipeline import summary_for
from upw.core.planner import overlay_csv, render_table
from upw.core.sync import sync_account
from upw.errors import RateLimitError, UpwError
from upw.redact import redact
from upw.runlog import RunLog
from upw.settings import Settings, upsert_env
from upw.state.store import StateStore

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Review-first Unsplash photo workflow.")


def main() -> None:
    app()


def _settings(root: Path) -> Settings:
    return Settings.load(root)


def _guard(settings: Settings, command: str, body: Callable[[RunLog], None]) -> None:
    log = RunLog(settings.state_dir, command)
    try:
        body(log)
    except UpwError as exc:
        message = redact(str(exc))
        if isinstance(exc, RateLimitError) and exc.retry_at is not None:
            StateStore(settings.state_dir).save_rate_limit({"retry_at": exc.retry_at, "message": message})
        log.fail("run", message)
        log.finish(message)
        raise typer.Exit(code=2) from exc


def _client(settings: Settings) -> UnsplashClient:
    settings.require_token()
    return UnsplashClient(
        access_key=settings.access_key,
        user_token=settings.user_token,
        api_base=settings.api_base,
        oauth_base=settings.oauth_base,
        max_sleep=settings.max_rate_sleep,
    )


def _maybe_open(path: Path) -> None:
    flag = os.environ.get("UPW_OPEN_REVIEW", "auto")
    if flag == "0":
        return
    if flag == "auto" and not sys.stdout.isatty():
        return
    webbrowser.open(path.resolve().as_uri())


@app.command()
def auth(root: Path = typer.Option(Path("."), "--root", help="Project directory.")) -> None:
    """Run a local OAuth flow and store the user token in .env."""
    settings = _settings(root)

    def body(log: RunLog) -> None:
        settings.require_app_keys()
        state = secrets.token_urlsafe(16)
        url = authorize_url(
            access_key=settings.access_key,
            redirect_uri=settings.redirect_uri,
            oauth_base=settings.oauth_base,
            state=state,
        )
        log.event("info", "Starting Unsplash OAuth")
        print("Open this URL if the browser does not:")
        print(url)
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            log.event("warning", "Could not open a browser")
        code = wait_for_code(settings.redirect_uri, state)
        with UnsplashClient(
            access_key=settings.access_key,
            user_token="",
            api_base=settings.api_base,
            oauth_base=settings.oauth_base,
            max_sleep=settings.max_rate_sleep,
        ) as client:
            token = client.exchange_code(
                client_secret=settings.secret_key,
                redirect_uri=settings.redirect_uri,
                code=code,
            )
        upsert_env(settings.root / ".env", {"UNSPLASH_USER_TOKEN": token})
        log.event("info", "Saved UNSPLASH_USER_TOKEN to .env")
        log.finish("Saved the Unsplash user token to .env. It was not printed.")

    _guard(settings, "auth", body)


@app.command()
def sync(root: Path = typer.Option(Path("."), "--root")) -> None:
    """Fetch your photos and record which ids are new."""
    settings = _settings(root)

    def body(log: RunLog) -> None:
        with _client(settings) as client:
            result = sync_account(client, StateStore(settings.state_dir), settings.username)
        log.event(
            "info",
            "Synced photos",
            username=result.username,
            photos=len(result.photos),
            new=len(result.new_ids),
        )
        log.finish(f"Synced {len(result.photos)} photos for @{result.username}. {len(result.new_ids)} are not processed yet.")

    _guard(settings, "sync", body)


@app.command()
def suggest(
    root: Path = typer.Option(Path("."), "--root"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Do not call an LLM."),
    all_photos: bool = typer.Option(False, "--all", help="Plan processed photos too."),
) -> None:
    """Build review.csv from the local sync snapshot."""
    settings = _settings(root)

    def body(log: RunLog) -> None:
        plan = build_suggestions(settings, log, no_ai=no_ai, include_processed=all_photos)
        log.finish(summary_for(plan, applied=False, stopped=False))

    _guard(settings, "suggest", body)


@app.command()
def review(root: Path = typer.Option(Path("."), "--root")) -> None:
    """Print the review plan and open review.csv on a local terminal."""
    settings = _settings(root)

    def body(log: RunLog) -> None:
        store = StateStore(settings.state_dir)
        plan = overlay_csv(store.load_plan(), store.review_csv_path())
        print(render_table(plan))
        print(store.review_csv_path())
        _maybe_open(store.review_csv_path())
        log.event("info", "Showed the review plan", rows=len(plan.photos))
        log.finish(f"Review file: {store.review_csv_path()}")

    _guard(settings, "review", body)


@app.command()
def apply(
    root: Path = typer.Option(Path("."), "--root"),
    yes: bool = typer.Option(False, "--yes", help="Write approved rows. Default is a dry run."),
    only_failed: bool = typer.Option(False, "--only-failed", help="Retry photos that failed last time."),
) -> None:
    """Apply the reviewed plan. Dry-run unless --yes."""
    settings = _settings(root)

    def body(log: RunLog) -> None:
        code = _apply(settings, log, yes=yes, only_failed=only_failed)
        if code:
            raise typer.Exit(code=code)

    _guard(settings, "apply", body)


def _apply(settings: Settings, log: RunLog, *, yes: bool, only_failed: bool) -> int:
    store = StateStore(settings.state_dir)
    plan = overlay_csv(store.load_plan(), store.review_csv_path())
    only_ids = store.failed_photo_ids() if only_failed else None
    if only_failed and not only_ids:
        log.finish("No failed photos in the last apply.")
        return 0
    photos = store.load_photos()
    username = settings.username or store.load_username()
    client: UnsplashClient | None = None
    if yes or settings.user_token:
        client = _client(settings)
    try:
        report = apply_plan(
            plan,
            photos,
            store,
            write=yes,
            client=client,
            username=username,
            run_id=log.run_id,
            only_ids=only_ids,
        )
    finally:
        if client is not None:
            client.close()
    counts: dict[str, int] = {}
    for item in report["results"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
        if item["status"] == "failed":
            log.fail(str(item["photo_id"]), str(item.get("error") or "failed"))
    mode = "wrote" if yes else "dry-run"
    summary = f"Apply {mode} ({log.run_id}): " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    log.event("info", summary, dry_run=not yes)
    log.finish(summary or "Nothing to apply.")
    return 1 if counts.get("failed") else 0


@app.command()
def run(
    root: Path = typer.Option(Path("."), "--root"),
    yes: bool = typer.Option(False, "--yes", help="Apply rows already marked yes."),
    no_ai: bool = typer.Option(False, "--no-ai"),
    all_photos: bool = typer.Option(False, "--all"),
) -> None:
    """Sync, suggest, and show the review. Apply only with --yes."""
    settings = _settings(root)

    def body(log: RunLog) -> None:
        with _client(settings) as client:
            result = sync_account(client, StateStore(settings.state_dir), settings.username)
        log.event("info", "Synced photos", photos=len(result.photos), new=len(result.new_ids))
        plan = build_suggestions(settings, log, no_ai=no_ai, include_processed=all_photos)
        print(render_table(plan))
        print(StateStore(settings.state_dir).review_csv_path())
        if not yes:
            log.finish(summary_for(plan, applied=False, stopped=True))
            return
        code = _apply(settings, log, yes=True, only_failed=False)
        if code:
            raise typer.Exit(code=code)

    _guard(settings, "run", body)


@app.command()
def status(
    root: Path = typer.Option(Path("."), "--root"),
    output: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Show how many photos are synced, new, and failed."""
    settings = _settings(root)
    store = StateStore(settings.state_dir)
    photos = store.load_photos()
    processed = store.processed_ids()
    new_ids = [photo.id for photo in photos if photo.id not in processed]
    failed = sorted(store.failed_photo_ids())
    try:
        review_rows = len(store.load_plan().photos)
    except UpwError:
        review_rows = 0
    last = store.last_apply_report()
    payload = {
        "photos": len(photos),
        "new": len(new_ids),
        "processed": len(processed & {photo.id for photo in photos}),
        "review_rows": review_rows,
        "failed": len(failed),
        "failed_ids": failed,
        "last_apply_run": None if last is None else last.get("run_id"),
    }
    if output == "json":
        print(json.dumps(payload))
        return
    print(
        f"Photos: {payload['photos']}  New: {payload['new']}  "
        f"Processed: {payload['processed']}  Review rows: {payload['review_rows']}  "
        f"Failed: {payload['failed']}"
    )
    if failed:
        print("Failed ids: " + ", ".join(failed))


if __name__ == "__main__":
    main()
