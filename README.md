# python-fotoware-client

[![tests](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/tests.yml)
[![pre-commit](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/pre-commit.yml/badge.svg?branch=main)](https://github.com/hoppefamily/python-fotoware-client/actions/workflows/pre-commit.yml)

A thin, read-only Python client for the [FotoWare](https://www.fotoware.com/)
API (FotoWeb). It does what the API does and shows what that costs; it knows
nothing about any particular archive's fields.

Not affiliated with or endorsed by FotoWare AS. "FotoWare" and "FotoWeb" are
their trademarks.

## What it does

- **One call is one request.** `search_assets` returns one page; `next_page`
  and `iter_search` follow `paging.next`. Nothing is batched or asked again
  behind the caller's back. The only exception are the rendition downloads,
  which poll until FotoWare has prepared the file.
- **Refuses a query FotoWare would answer wrongly.** Over FotoWare's size limit
  a search comes back as a 500 or, worse, as an empty list that looks exactly
  like "no hits". `search_assets` estimates the query first and raises
  `QueryTooLargeError` over the budget, without sending it.
  `estimate_query_size` is public, so callers can batch to stay under it.
- **Retries what is transient.** urllib3's `Retry` on the session retries 429
  (honouring `Retry-After`) and 502/503/504, twice by default. A 500 is not
  retried: it was always caused by the query.
- **Counts the cost.** `cost_snapshot()` reports requests, retries, errors,
  search pages and empty search pages.
- OAuth client credentials with automatic token refresh; context manager.
- **Takes hrefs as FotoWare gives them.** Answers carry paths on the tenant;
  every call that takes an href accepts a path or a full URL.

## FotoWare's limits

Measured on 2026-10-23 against FotoWeb 8.1.1223.0; details and edges in
`fotoware_client/limits.py`.

| Limit | Value |
| --- | --- |
| Assets per search answer | 25, fixed (`pageSize` is ignored) |
| Cost of an answer | ~0.4 s with hits whether 1 or 25 assets; 130–220 ms empty |
| Search size | about 2,000 by `estimate_query_size`; budget 1,500 |

So the cheapest search asks for as many terms as fit the budget and fills
whole pages.

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

with FotoWareClient.from_env() as client:
    archive = next(
        a for a in client.list_archives() if a.href.startswith("/fotoweb/archives/5000-")
    )
    query = "(631:4000000000001 OR 631:4000000000002) AND (dt:image OR dt:graphic)"
    for page in client.iter_search(archive.href, query):
        for asset in page.assets:
            print(asset.filename)
    print(client.cost_snapshot())
```

Other calls: `get_asset`, `get_field_labels`, `get_rendition_url`, `download_original`,
`download_original_to_file`, `download_rendition_to_file`, `download_bytes`.

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
pip install "python-fotoware-client @ git+https://github.com/hoppefamily/python-fotoware-client.git@v0.1.0"
```

## Development

```bash
make venv
make lint type test
```

Pre-commit hooks: `pip install pre-commit && pre-commit install`.

## License

MIT, see [LICENSE](LICENSE).
