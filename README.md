# unsplash-photo-workflow

Review-first pipeline for [Xuedi's Unsplash](https://unsplash.com/@liuxuedi) photos.
A Canon EOS 77D does not write GPS, and Unsplash does not return GPS from EXIF, so
location, tags, descriptions, trip collections, and profile visibility are filled by
deterministic code. An LLM is called only for the slots that code cannot fill, and
nothing is written until a human approves the plan.

The command-line entry point is `upw`. Library code lives in `src/upw` and is shared
by the CLI. A later stage adds a Next.js review UI under `web/`.

## Layout

```
src/upw/adapters/   Unsplash, Nominatim, EXIF/GPX, optional LLM
src/upw/core/       sync, locate, tag, group, rules, plan, apply
config/             rules and tag templates
trips/*.yaml        one itinerary per trip
state/              gitignored caches, processed ids, logs, review files
```

## Development

```bash
python -m pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy src
pytest --cov=upw --cov-report=term-missing --cov-fail-under=80
```

CI on every pull request and on `master` runs Ruff, mypy, pytest with coverage, and gitleaks.
This repository is public. Never commit `.env` or any token. `.env.example` lists the variable names only.

The stages after this bootstrap (CLI, scheduled GitHub Action, web review UI) land as pull requests.
Live Unsplash and LLM credentials are not required to run the tests: HTTP is mocked.
