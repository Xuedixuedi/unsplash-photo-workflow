# unsplash-photo-workflow

Review-first pipeline for [Xuedi's Unsplash](https://unsplash.com/@liuxuedi) photos.

The camera is a Canon EOS 77D, which does not write GPS, and the Unsplash API does not return GPS from EXIF. After each upload batch, `upw` fills location, tags (up to 20), a description, a trip collection, and a show-on-profile suggestion. Deterministic code does the work. An LLM is called only for the slots that code cannot fill, and nothing is written until a human approves the plan.

```bash
python -m pip install -e ".[dev]"
cp .env.example .env
upw auth
upw run          # sync, suggest, print the review, stop
# edit state/review.csv
upw apply --yes  # write the rows whose approve column is yes
```

## What a run does

1. **sync** downloads your public photos and remembers which ids are not processed yet.
2. **suggest** builds `state/review.csv` and `state/review.json`.
3. **review** prints the plan. On a local terminal it also opens the CSV.
4. **apply** writes only rows marked `yes`. The default is a dry run. `--yes` performs the writes. The write is idempotent: a second apply skips fields that already match.
5. **run** does sync, suggest, and review, and stops before apply unless you pass `--yes`.

`approve` values:

| value | meaning |
| --- | --- |
| `yes` | apply the proposed location, tags, description, visibility, and collection |
| `no` | leave the photo alone this time; it stays in the next plan |
| `skip` | ignore the photo on later runs |

Rows the pipeline is confident about start as `yes`. A neighbour guess, an LLM suggestion, a burst hide, or an empty location starts as `no`. Low-confidence fields are flagged in their own columns (`location_flag`, `tags_flag`, and so on).

## Location chain

The first hit wins:

1. GPS in the local original file (`originals/{photo_id}.jpg`, or a row in `originals/manifest.csv`).
2. A phone photo, GPX track, or Google Timeline JSON (`UPW_PHONE_SOURCE`), matched by time. `camera_clock_offset_seconds` in `config/rules.yaml` is added to the camera clock first. The camera timestamp is read as `timezone` (default `Asia/Shanghai`).
3. The trip itinerary, when that calendar day lists exactly one place.
4. A neighbouring photo in the same batch, within `neighbour_max_seconds`, when both have a real clock time.
5. The optional LLM, which may choose only among the itinerary places for that day.
6. Otherwise the location stays empty and the row is flagged for review.

A location already stored on the photo is kept when local GPS does not contradict it, so a re-run does not churn a place you already set. Without a local original, the itinerary is matched on the Unsplash upload date, because the API does not provide the shutter time.

## Tags, description, collections, visibility

Tags keep the ones already on the photo (lowercased, case-insensitive dedupe). Then the pipeline adds the place, city, region, and country, the trip's tags, and the tags from the trip's template in `config/tag_templates.yaml`. New tags are lowercase, 1–3 words, and never a camera brand or a hashtag. Existing owner tags may be up to 5 words so phrases such as "unesco world heritage site" survive. Only the slots left under 20 are offered to the LLM, and only when a small image of the original is available.

The description is kept when one already exists. Otherwise it is a sentence built from the place. The LLM writes one only when that template has nothing to say.

Photos are grouped by the trip whose dates cover the capture day. Unmatched photos are clustered when consecutive dates are more than `cluster_gap_days` apart. The collection is created on apply if the title does not exist yet. Adding a photo that is already in the collection is a no-op on Unsplash.

`show_on_profile` is proposed `false` for extra frames in a burst shorter than `burst_seconds`. A photo with more downloads than `never_hide_above_downloads` (100) is never hidden. Hiding is always flagged for review, so it is not auto-approved.

## Project layout

```
src/upw/adapters/   Unsplash, Nominatim, EXIF/GPX, optional LLM
src/upw/core/       sync, locate, tag, group, rules, plan, apply
config/             rules.yaml and tag_templates.yaml
trips/*.yaml        one itinerary per trip
fixtures/           trimmed public metadata for tests
state/              gitignored caches, processed ids, logs, review files
```

`trips/example-jiuzhaigou.yaml` is a real-shaped example: trip name, collection name, a day, and two places. Copy it and edit the dates. A day with one place is filled in directly. Several places are left blank unless a neighbour or the LLM can choose.

## Create the Unsplash app

1. Open [unsplash.com/oauth/applications](https://unsplash.com/oauth/applications) and create an application.
2. Set the redirect URI to `http://127.0.0.1:8787/callback`.
3. Request scopes `public`, `read_user`, `write_photos`, and `write_collections`.
4. Copy the access key and secret key into `.env` (see `.env.example`). Never commit `.env`.

Demo apps are limited to 50 requests per hour. Production apps are limited to 1000. The client reads `X-Ratelimit-Limit` and `X-Ratelimit-Remaining`. It sleeps for `Retry-After` or until `X-Ratelimit-Reset` when that wait is short, and otherwise stops with a resume time so you can run the command again. There is no upload endpoint and no photo-delete endpoint. Those are out of scope.

```bash
upw auth
```

This opens the Unsplash consent page, catches the redirect on localhost, and writes `UNSPLASH_USER_TOKEN` into `.env`. The token is not printed. JSON logs redact bearer tokens and known secret values.

## Optional LLM

Leave `LLM_API_KEY` empty, or pass `--no-ai`, and the pipeline stays deterministic. When a key is set, calls go to an OpenAI-compatible `LLM_BASE_URL` (`/chat/completions`, JSON object responses) with a JPEG no larger than 512px. Responses are cached by photo id plus a hash of the prompt and image. Another provider can implement `JsonCompleter` in `src/upw/adapters/llm.py`.

Nominatim is limited to one request per second, sends `NOMINATIM_USER_AGENT`, and caches results in `state/cache/geocode.json`.

## Commands

```text
upw auth
upw sync
upw suggest [--no-ai] [--all]
upw review
upw apply [--yes] [--only-failed]
upw run [--no-ai] [--all] [--yes]
upw status [--format json]
```

`--all` plans photos that were already processed. `--only-failed` retries photos that failed in the last apply. Each command writes `state/logs/{run_id}.json` with a run id, the events, and the failed items, and prints a short summary at the end.

Originals and phone tracks:

```text
originals/2RxlZqY3nz8.jpg
originals/manifest.csv          # photo_id,file
UPW_PHONE_SOURCE=phone/track.gpx
UPW_PHONE_SOURCE=phone/timeline.json
UPW_PHONE_SOURCE=phone/iphone-exports/
```

Google Timeline JSON accepts `locations[].latitudeE7` / `longitudeE7` with `timestamp` or `timestampMs`, or a list of `{time, lat, lon}`.

## Tests

HTTP is mocked. No live Unsplash or LLM credentials are required.

```bash
ruff check . && ruff format --check .
mypy src
pytest --cov=upw --cov-report=term-missing --cov-fail-under=80
```

CI on every pull request and on `master` runs those checks plus gitleaks. This repository is public. Do not commit tokens, `.env`, or `state/`.

`fixtures/photos.json` and `fixtures/tags_current.json` are trimmed from the owner's public photo metadata and current tags. They are safe to commit.

## Later stages

A GitHub Actions workflow (manual, plus an optional daily schedule) and a Next.js review UI are added in follow-up pull requests. Branch protection on `master`, when this token can set it, should require the CI checks before merge. If the API refuses, the settings are:

GitHub → Settings → Branches → Add rule for `master` → Require a pull request and require the status checks named `python` and `gitleaks`.

## Limitations

- Unsplash does not return GPS, and it does not return the shutter time. Capture time comes from your local originals.
- The public API lists public photos only. There is no upload and no delete.
- Demo apps share a 50 request hourly budget. `upw run` on a large library can spend that on sync alone. Apply compares against the last sync snapshot and updates the snapshot after a successful write.
- Hiding "weaker" shots without an aesthetic model means burst extras, plus any ids you list in `force_hide_ids`. Downloads above 100 are never hidden.
- Nominatim is a public service. Keep the User-Agent honest and the cache on.
