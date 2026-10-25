# python-fotoware-client

[![tests](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/tests.yml)
[![pre-commit](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/pre-commit.yml/badge.svg?branch=main)](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/pre-commit.yml)

A thin, read-only Python client for the [FotoWare](https://www.fotoware.com/)
API (FotoWeb). It does what the API does and shows what that costs; it knows
nothing about any particular archive's fields.

Not affiliated with or endorsed by FotoWare AS. "FotoWare" and "FotoWeb" are
their trademarks.

## What it does

- **One method per API call, one request each.** `FotoWareClient` mirrors
  FotoWare's REST API: `get_api_descriptor`, `get_archives`, `get_archive`,
  `get_metadata_editor`, `search` (one page), `get_page`, `get_asset`,
  `request_rendition`, `get_rendition_task`. Nothing is batched or asked again
  behind the caller's back.
- **Extensions for what takes several calls.** `fotoware_client.extensions`
  builds on those methods alone: `list_archives`, `field_labels`, `iter_search`
  over every page, and `Rendition` for a file from request to download.
- **Refuses a query FotoWare would answer wrongly.** Over FotoWare's size limit
  a search comes back as a 500 or, worse, as an empty list that looks exactly
  like "no hits". `search` estimates the query first and raises
  `QueryTooLargeError` over the budget, without sending it.
  `estimate_query_size` is public, so callers can batch to stay under it.
- **Retries what is transient.** urllib3's `Retry` on the session retries 429
  (honouring `Retry-After`) and 502/503/504, twice by default. A 500 is not
  retried: it was always caused by the query.
  The waits double from 1 s and carry jitter, so parallel callers do not
  all ask again at the same moment; a `Retry-After` is kept as sent.
- **Counts the cost.** `cost_snapshot()` reports requests, retries, errors,
  search pages and empty search pages. A 410 Gone counts as `gone`, not as an
  error: it is how a rendition task FotoWare cleaned up answers, and
  `Rendition` requests such a rendition anew.
- OAuth client credentials with automatic token refresh; context manager.
- **Takes hrefs as FotoWare gives them.** Answers carry paths on the tenant;
  every call that takes an href accepts a path or a full URL.

## FotoWare's limits

Measured on 2026-10-23 against FotoWeb 8.1.1223.0; details and edges in
`fotoware_client/limits.py`.

| Limit | Value |
| --- | --- |
| Assets per search answer | 25, with `pageSize` ignored. FotoWare guarantees no page size, so the client follows `paging.next` and counts nothing |
| Cost of an answer | ~0.4 s with hits whether 1 or 25 assets; 130–220 ms empty |
| Search size | about 2,000 by `estimate_query_size`; budget 1,500 |

So the cheapest search asks for as many terms as fit the budget and fills
whole pages.

Two search settings of an installation (Site Configuration › Searching) are out
of the client's sight:

- **Maximum number of hits** caps a result set. A search with more hits ends
  early, without saying so.
- **Search string modification** decides how plain words without an operator
  are combined (AND, OR or as a phrase). Write `AND`/`OR` explicitly, and the
  setting does not matter.

## Settings of an installation

What a FotoWare installation may set differently, the client takes as
`ServerSettings`; the defaults are FotoWeb's:

```python
from fotoware_client import FotoWareClient, ServerSettings

settings = ServerSettings(
    original_rendition_name="Originaldatei",  # display names are configurable
    download_timeout=300,  # seconds per download or rendition
    rendition_poll_interval=0.5,  # first wait while a rendition is made
    query_size_budget=1200,  # if the installation's limit is lower
)
client = FotoWareClient.from_env(settings=settings)
```

Also: `oauth_token_path`, `api_descriptor_path`, `rendition_poll_interval_max`
and `term_overhead`. See `fotoware_client/settings.py`.

## Credentials

Pass them to the constructor, or let `FotoWareClient.from_env()` find them:

1. the environment: `FOTOWARE_TENANT_URL`, `FOTOWARE_CLIENT_ID`,
   `FOTOWARE_CLIENT_SECRET`;
2. else the credentials file `~/.config/fotoware/credentials`
   (`$XDG_CONFIG_HOME/fotoware/credentials`), one `NAME=value` per line,
   refused unless only its owner may read it (`chmod 600`).

Never on a command line, where a secret lands in the process list and the
shell history.

## Usage

```python
from fotoware_client import FotoWareClient
from fotoware_client.extensions import Rendition, iter_search, list_archives

with FotoWareClient.from_env() as client:
    archive = next(a for a in list_archives(client) if a.href.startswith("/fotoweb/archives/5000-"))
    query = "(631:4000000000001 OR 631:4000000000002) AND (dt:image OR dt:graphic)"
    for page in iter_search(client, archive.href, query):
        for asset in page.assets:
            print(asset.filename)

    Rendition(client, asset.href).save("original.jpg")
    data = Rendition(client, asset.href, "Medium (JPG, 3000px)").read()
    print(client.cost_snapshot())
```

`Rendition(client, href, name=None)` asks FotoWare to prepare the original, or
the rendition with that display name, polls the task, and downloads the file
in the poll that finds it ready: `.save(path)`, `.read()`, `.write_to(file)`,
or `.url()` for the prepared address alone. A task FotoWare has already
cleaned up (410 Gone) is requested anew, once.

## Errors

All derive from `FotoWareError`:

| Error | When |
| --- | --- |
| `QueryTooLargeError` | the query is over the size budget; nothing sent |
| `RateLimitError` | a 429 outlasted the retries |
| `RetryExhaustedError` | a 502/503/504, connection error or timeout outlasted the retries |
| `NotFoundError` | a 404 |
| `APIError` | any other error status, a 500 among them |
| `AuthenticationError` | the token could not be fetched |
| `ConfigurationError` | the client was set up wrongly |

## Install

```bash
pip install python-fotoware-client
```

## Development

```bash
make venv
make lint type test
```

Pre-commit hooks: `pip install pre-commit && pre-commit install`.

## License

MIT, see [LICENSE](https://github.com/hoppefamily/python-fotoware-client/blob/main/LICENSE).
