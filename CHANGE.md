# CHANGE.md

## v0.1.11 - 2026-02-20

### Added
- Added a new React + TypeScript + Vite frontend workspace under `frontend/`, including:
  - auth/login flow
  - dashboard/content/sources pages
  - reusable publish and layout components
  - API client wiring and platform constraint helpers
- Added frontend end-to-end test specs for integration and publish flow:
  - `frontend/e2e/integration.spec.ts`
  - `frontend/e2e/publish-flow.spec.ts`
- Added frontend project tooling and configs:
  - Vite + React + Tailwind
  - ESLint + TypeScript config
  - Playwright config

### Changed
- Enabled CORS middleware in API for local frontend dev origins:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`
- Updated frontend ignore rules to exclude Playwright runtime artifacts:
  - `test-results`
  - `playwright-report`

## v0.1.10 - 2026-02-19

### Added
- Added template-driven pre-generation constraints to reduce random failures:
  - platform-specific length/style/rule templates
  - configurable banned words injection into generation prompts
- Added generation stage timeout budget + explicit fallback degrade:
  - primary model timeout/failure now degrades to fallback model in-stage
  - per-call generation metadata includes backend/model/latency and fallback usage
- Added post-generation auto quality check + bounded self-repair:
  - generated drafts are scored on quality/compliance/repetition
  - automatic repair loop is capped by `GEN_SELF_REPAIR_MAX_ATTEMPTS`
  - prevents unbounded retry/repair loops
- Added generation output versioning and rollback support:
  - `draft_versions` table stores content snapshots + prompt/model/params/hash metadata
  - API support for version listing and rollback
- Added publish-stage stability gate:
  - blocks publication when quality/compliance/repetition thresholds are not met
  - includes near-duplicate blocking across same publish batch

### Changed
- `SummarizerAgent` now uses:
  - constraint templates
  - timed generation budget
  - fallback-first degrade on primary failure
  - self-repair bounded loop
  - generation metadata attachment (`generation_meta`)
- `QualityAgent` now computes and persists:
  - `compliance_score`
  - `repetition_ratio`
- `PublisherAgent` now enforces pre-publish gate thresholds.
- `TrendOrchestrator` now persists generation versions for each saved draft.

### API
- Added:
  - `GET /api/v1/content/{draft_id}/versions`
  - `POST /api/v1/content/{draft_id}/versions/{version_no}/rollback`

### Tests
- Added/extended regression coverage for:
  - generation metadata output
  - draft versioning + rollback
  - content rollback API 404 behavior

## v0.1.9 - 2026-02-19

### Added
- Added parse-stage contract + schema versioning:
  - strict parse contract `ParseContractV1` (`schema_version=v1`)
  - strong validation on required fields and types before accepting parse output
- Added parse confidence scoring and routing:
  - low-confidence auto retry within run
  - low-confidence routing to `delayed` queue or `manual_review` queue
- Added parse DLQ (dead-letter queue):
  - persisted parse dead letters (`parse_dead_letters` table)
  - replay support for failed parse items
- Added parse cache by `content_hash + schema_version`:
  - avoids duplicate parse/model calls on repeated content
- Added recoverable/unrecoverable parse error split:
  - recoverable errors go delayed retry with exponential backoff
  - unrecoverable errors go directly to DLQ to prevent retry storms
- Added parse management APIs:
  - `POST /api/v1/parse/run`
  - `GET /api/v1/parse/dlq`
  - `POST /api/v1/parse/dlq/{dlq_id}/replay`

### Changed
- `trend_sources` now stores parse execution metadata:
  - `parse_schema_version`
  - `parse_confidence`
  - `parse_attempts`
  - `parse_error_kind`
  - `parse_last_error`
  - `parse_retry_at`
- `TrendOrchestrator` now triggers parse-stage processing for freshly ingested source rows.
- Capabilities endpoint now exposes parse runtime settings.

### Tests
- Added parse service regression tests covering:
  - contract validation success path
  - low-confidence delayed/manual routing
  - recoverable retry behavior
  - unrecoverable to DLQ behavior
  - content-hash parse cache hit behavior
  - DLQ replay success
- Added API regression tests for parse run endpoint and DLQ replay 404 behavior.

## v0.1.8 - 2026-02-19

### Added
- Added Redis-backed scraper coordination backend for multi-instance runtime:
  - shared priority queue for scrape jobs
  - shared queue backpressure limit
  - cross-instance result handoff via Redis pub/sub
- Added Redis-backed source-level circuit breaker state sharing:
  - shared open/half-open/closed transition state
  - shared failure counters and open window across instances
- Added runtime config for scraper coordination:
  - `SCRAPER_COORDINATION_BACKEND`
  - `SCRAPER_REDIS_URL`
  - `SCRAPER_REDIS_KEY_PREFIX`
  - `SCRAPER_REDIS_POP_TIMEOUT_SECONDS`

### Changed
- `ScraperAgent` now supports dual coordination backends:
  - `memory` (default, previous behavior)
  - `redis` (distributed queue + circuit state)
- `ScraperAgent` falls back to `memory` backend automatically when Redis package/service is unavailable.
- `/api/v1/capabilities` now exposes scraper coordination backend and Redis key prefix.

### Tests
- Extended scraper regression tests with Redis coordination coverage:
  - shared queue backpressure across two agent instances
  - shared circuit-open visibility across two agent instances

## v0.1.7 - 2026-02-19

### Added
- Added source-level resilience controls in scraping:
  - circuit breaker with half-open probing
  - exponential backoff retry
- Added scrape queue + backpressure controls:
  - bounded priority queue
  - configurable enqueue timeout
  - per-source RPS rate limiting
- Added scraper state persistence:
  - `scraper_states` table
  - `BaseScraper.load_state/dump_state`
  - persisted `GitHubScraper` cursor + ETag across restarts
- Added source ingest idempotency by triple key:
  - `source_platform + source_id + source_updated_at`
  - backed by `source_ingest_records` table
- Added platform SLO metrics for scraping:
  - request outcomes
  - HTTP status class counters (`429`, `5xx`, etc.)
  - item throughput
  - cost units

### Changed
- `ScraperAgent` now dispatches via queue workers in runtime mode and enforces:
  - backpressure
  - per-source rate limiting
  - source isolation via circuit breaker
- `TrendSource` now stores `source_updated_at`.
- Runtime capabilities endpoint now exposes scraper resilience/rate settings.

### Tests
- Added scraper regression:
  - source-level circuit breaker short-circuit behavior
- Added content store regression:
  - idempotent ingest by `source_updated_at`
  - scraper state persistence roundtrip
- Existing GitHub incremental tests continue to pass with state persistence flow.

## v0.1.6 - 2026-02-19

### Added
- Expanded `GitHubScraper` channels with:
  - `github_issue`
  - `github_pull_request`
  - `github_discussion`
  - `github_security_advisory`
- Added incremental scraping support for GitHub:
  - in-memory per-channel `updated_at` cursor filtering
  - per-endpoint `ETag` cache and conditional `If-None-Match` requests
- Added GitHub-specific heat-score controls:
  - `HEAT_GITHUB_WEIGHT_STAR_VELOCITY`
  - `HEAT_GITHUB_WEIGHT_CONTRIBUTOR_ACTIVITY`
  - `HEAT_GITHUB_WEIGHT_RELEASE_ADOPTION`
  - `HEAT_GITHUB_STAR_VELOCITY_NORM_CAP`
  - `HEAT_GITHUB_CONTRIBUTOR_ACTIVITY_NORM_CAP`
  - `HEAT_GITHUB_RELEASE_ADOPTION_NORM_CAP`
  - `HEAT_GITHUB_BOOST_BASE`
  - `HEAT_GITHUB_BOOST_RANGE`

### Changed
- `HeatScoreService` now includes GitHub platform-specific feature composition:
  - star velocity
  - contributor activity
  - release adoption
- Runtime capability output now exposes GitHub heat-weight settings.

### Tests
- Extended third-party scraper regression tests with:
  - new GitHub channels coverage
  - ETag + cursor incremental behavior coverage
- Extended heat-score regression tests with GitHub-specific ranking behavior.

## v0.1.5 - 2026-02-19

### Added
- Added `GitHubScraper` with two channels:
  - `github_trending` (repository search)
  - `github_release` (latest release per repository)
- Added GitHub scraper runtime config:
  - `GITHUB_TOKEN`
  - `GITHUB_API_BASE_URL`
- Added structured scrape-stage persistence model on `trend_sources`, including:
  - source metadata: `source_channel`, `source_type`, `pipeline_run_id`
  - strategy context: `capture_mode`, `sort_strategy`
  - normalized fields: `published_at`, `normalized_text`, `hashtags`, `mentions`
  - media/link fields: `external_urls`, `media_urls`, `media_assets`, `multimodal`
  - ranking fields: `normalized_heat_score`, `heat_breakdown`, `platform_metrics`
  - parse workflow fields: `parse_status`, `parse_payload`, `parsed_at`, `last_seen_at`
- Added repository helpers for downstream parsing:
  - `list_sources_for_parsing(...)`
  - `mark_source_parsed(...)`

### Changed
- Integrated `github` into `ScraperAgent` registry and default scraper source set.
- Unified scraper outputs with explicit `source_channel`/`source_type` tags across platforms.
- Updated scraping node persistence to write structured capture/heat fields directly to DB.
- Added lightweight migration for existing `trend_sources` schema.

### Tests
- Expanded third-party scraper regression tests:
  - Added GitHub channel tests in `tests/test_scrapers_third_party.py`
- Expanded content store regression tests:
  - Added structured trend source persistence + parse-state tests
  - Added legacy `trend_sources` schema migration test
- Added API negative regression:
  - `tests/test_api.py::test_patch_schedule_enable_not_found_returns_404`

## v0.1.4 - 2026-02-19

### Added
- Added third-party scraper regression test suite:
  - `tests/test_scrapers_third_party.py`
  - Covers `TwitterScraper`, `YouTubeScraper`, `WeiboScraper`, `BilibiliScraper`, `ZhihuScraper`

### Tests
- Added 5 offline parser/field-mapping tests for third-party scrape responses.


## v0.1.3 - 2026-02-19

### Added
- Added `PATCH /api/v1/schedules/{schedule_id}/enable` endpoint to toggle schedule enable/disable state.

### Changed
- Schedule toggle now updates both persisted state and in-memory scheduler job registration.

### Tests
- Added API tests:
  - `tests/test_api.py::test_update_schedule_not_found_returns_404`
  - `tests/test_api.py::test_update_schedule_no_updates_returns_400`
  - `tests/test_api.py::test_patch_schedule_enable_toggle`


## v0.1.2 - 2026-02-19

### Added
- Added `PUT /api/v1/schedules/{schedule_id}` to update schedule config fields, including:
  - `query`
  - `capture_mode` (`by_time` / `by_hot` / `hybrid`)
  - `sort_strategy` (`engagement` / `recency` / `hybrid`)
  - `start_time` / `end_time`
  - `enabled`
- Added schedule query API support in repository:
  - `ContentRepository.get_schedule(schedule_id)`

### Changed
- Updated schedule update workflow to:
  - validate schedule existence before update
  - persist partial updates
  - refresh in-memory scheduler jobs (`remove` then conditional `add` when enabled)
- Improved schedule update normalization in repository for optional strategy fields.

### Tests
- Added API regression test:
  - `tests/test_api.py::test_update_schedule_with_strategy_fields`
- Added repository regression test:
  - `tests/test_content_store.py::test_schedule_update_strategy_fields`


## v0.1.1 - 2026-02-19

### Added
- Added scrape strategy fields to pipeline:
  - `capture_mode`, `sort_strategy`, `start_time`, `end_time`, `query`
- Added source normalization service:
  - text normalization, hashtag/mention/url extraction, media asset structuring
- Added unified cross-platform heat score service.
- Added selective multimodal enrichment service for high-value image items.
- Added multimodal analysis method in LLM client (`analyze_media`).
- Added schedule model persistence fields:
  - `query`, `capture_mode`, `sort_strategy`, `start_time`, `end_time`
- Added lightweight DB migration for existing `schedule_configs` tables.
- Added heat score config options:
  - component weights
  - freshness decay parameters
  - per-platform weighting

### Changed
- Updated scraper pipeline to:
  - apply normalization
  - deduplicate by text + media hash
  - score and sort using strategy-aware heat ranking
  - optionally apply multimodal enrichment
- Updated API schedule creation to accept strategy fields.
- Updated scheduler execution path to pass strategy fields into orchestrator.
- Updated capability endpoint to expose multimodal and heat-score runtime config.

### Tests
- Added heat score regression tests:
  - stable ordering
  - strategy sorting
  - platform weight override effect
  - freshness decay effect
- Added scraper strategy regression tests:
  - by-time filtering and recency behavior
  - by-hot engagement sorting behavior
- Added schedule migration and persistence tests.
- Added API schedule creation test with strategy fields.
