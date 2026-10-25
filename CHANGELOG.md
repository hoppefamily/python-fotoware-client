# Changelog

All notable changes to python-fotoware-client. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/), where before 1.0 a minor version
may break the API.

## [Unreleased]

## [0.3.2] - 2026-10-25

### Changed

- A 410 Gone counts as `gone` in `cost_snapshot()`, no longer as an error.
  FotoWare answers 410 for a rendition task it has cleaned up, and
  `Rendition` requests such a rendition anew; counted under `errors`, a
  renewed rendition read like a failure. The `APIError` with
  `status_code=410` is raised as before.

## [0.3.1] - 2026-10-24

### Added

- `Rendition(client, asset_href, name=None, *, timeout=None)`: a rendition
  may have its own time limit, in seconds, instead of
  `ServerSettings.download_timeout`. A timeout of zero or less is refused.

## [0.3.0] - 2026-10-24

One method per FotoWare call; what takes several, in
`fotoware_client.extensions`. This release breaks the API.

### Added

- `FotoWareClient`, one method per API call, one request each:
  `get_api_descriptor`, `get_archives`, `get_archive`, `get_metadata_editor`,
  `search` (one page), `get_page`, `get_asset`, `request_rendition`,
  `get_rendition_task`.
- `fotoware_client.extensions`, built from those methods alone:
  `list_archives`, `field_labels`, `iter_search`, and
  `Rendition(client, href, name=None)` with `save()`, `read()`, `write_to()`
  and `url()`. The poll that finds the file ready delivers it; a task gone
  (410) is requested anew, once.
- Retry waits carry jitter (`RetryConfig.jitter`, default 0.5); a
  `Retry-After` is kept as sent.

### Removed

- `get_download_url` and `download_bytes`.
- The multi-call methods, now in the extensions:

  | 0.2 | 0.3 |
  | --- | --- |
  | `list_archives()` | `extensions.list_archives(client)` |
  | `get_field_labels(href)` | `extensions.field_labels(client, href)` |
  | `search_assets(...)` | `search(...)` |
  | `next_page(result)` | `get_page(result.next_href)` |
  | `iter_search(...)` | `extensions.iter_search(client, ...)` |
  | `get_rendition_url(href, rendition=...)` | `Rendition(client, href, name).url()` |
  | `download_original(href)` | `Rendition(client, href).read()` |
  | `download_original_to_file(href, f)` | `Rendition(client, href).write_to(f)` |
  | `download_rendition_to_file(href, f, rendition=n)` | `Rendition(client, href, n).write_to(f)` |
  | `validate_connection()` | `get_api_descriptor()` |

## [0.2.3] - 2026-10-24

### Fixed

- A rendition whose background task FotoWare has already cleaned up (410
  Gone) is requested anew, once, instead of failing its download.

## [0.2.2] - 2026-10-24

### Fixed

- Every response is closed, also when its body cannot be read: an answer that
  was no JSON, and a rendition request answered with a `Location` header,
  kept their connection out of the pool.

## [0.2.1] - 2026-10-24

### Fixed

- The licence link in the project description works on PyPI.

## [0.2.0] - 2026-10-24

First public release, on PyPI: a thin, read-only client for the FotoWare API
(FotoWeb). Not affiliated with or endorsed by FotoWare AS.

### Added

- One call, one request: `search_assets` returns one page; `next_page` and
  `iter_search` follow `paging.next`.
- A search FotoWare would answer wrongly is refused: over its size limit
  FotoWare answers a 500, or an empty list that looks like "no hits".
  `search_assets` raises `QueryTooLargeError` instead of sending it;
  `estimate_query_size` is public.
- Retries of 429 (honouring `Retry-After`) and 502/503/504 through urllib3,
  never of a 500.
- `cost_snapshot()`: requests, retries, errors and search pages.
- `ServerSettings`: what an installation can configure -- API paths, the
  original rendition's name, timeouts, rendition polling, the search size
  budget.
- Credentials from `FOTOWARE_TENANT_URL`, `FOTOWARE_CLIENT_ID` and
  `FOTOWARE_CLIENT_SECRET` or `~/.config/fotoware/credentials`
  (`FotoWareClient.from_env()`).
- `py.typed`.

## [0.1.0] - 2026-10-24

The first version under this name, tagged in the repository only and not
published.

[Unreleased]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/hoppefamily/python-fotoware-client/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/hoppefamily/python-fotoware-client/releases/tag/v0.1.0
