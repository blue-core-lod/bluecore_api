# Federated search spike

Search Blue Core and external BIBFRAME sources side by side, and load an
external record for editing without storing it. Built to answer one question:

> Do we have to bulk-load all of the Library of Congress into Blue Core so that
> catalogers can find a record to copy?

Short answer: no, not for that reason. What follows is what was built and what
was measured.

## Endpoints

### `GET /search/federated`

Same parameters as `GET /search/` (`q`, `type`, `scope`, `limit`, `offset`) plus
`sources`. Public, like the rest of the read API.

```
curl -s 'localhost:3000/search/federated?q=melville+moby&type=works' \
  | jq '.sources[] | {id, status, total, elapsed_ms}'
```

Results are **grouped by source, never merged**. Two reasons:

- The scores are not comparable. `ts_rank` is a normalized cover-density score
  in `(0,1]` computed against Blue Core's corpus; LC's `rank` is an
  unnormalized static weight — six *different* works for `melville moby` all
  score exactly `23803`. Any merged order would be a number that looks
  authoritative, reorders when you page, and nobody can debug.
- A merged list would bury Blue Core's own records under a pool hundreds of
  times larger — exactly the records a cataloger needs to see in order *not* to
  duplicate them.

Each group carries `status` (`ok` / `timeout` / `error` / `unsupported`),
`elapsed_ms`, its own `total`, and `total_is_exact` so a counted total is
distinguishable from an upstream estimate.

**A source that fails is never reported as a source with no results.** That
distinction is the whole reliability story: a cataloger who reads a timeout as
"no such record exists" goes and catalogs a duplicate. The endpoint returns 200
with `partial: true` whenever at least one source answered.

Add `Accept: text/html` for a browsable version, which is how to demo this
without any sinopia_editor changes.

### `GET /external/resources?uri=…`

Fetches a record from an allow-listed source and returns it framed the way Blue
Core frames its own, so an editor can load it. **Nothing is persisted** — the
record becomes a Blue Core row only if a cataloger saves it. That is the
property the whole approach rests on.

`bluecore_uri` says whether Blue Core already holds a copy derived from this
record, so a client can offer to open that instead of making a second one.

### `GET /search/federated/metrics`

Live counters for the experiment. Aggregate only -- no query text, nothing
about who searched.

```
curl -s localhost:3000/search/federated/metrics | jq
```

The number to watch is `distinct_external_records_fetched`: records catalogers
actually opened, set against the ~47M a bulk load would bring in. If that stays
in the thousands over a few months, the ratio is the argument.

Per-process and reset on restart, like the cache. The durable record is the
`federated.search` and `federated.fetch` log lines.

Note what cannot be counted yet: whether an opened record was ultimately
**saved**. The editor posts a blank-node subject, so nothing on the write path
knows which external record a new resource came from -- see the provenance
decision below. `distinct_external_records_fetched` is therefore an upper bound
on records kept, and a fair measure of records touched.

## Configuration

| Variable | Default | |
|---|---|---|
| `FEDERATED_SEARCH_SOURCES` | `bluecore,loc` | Enabled sources, in response order. The `sources=` parameter may only narrow this. |
| `LOC_BASE_URL` | `https://id.loc.gov` | |
| `LOC_SEARCH_DIRECTORIES` | `works` | Which suggest2 directories a `type=all` search covers. |
| `FEDERATED_SEARCH_TIMEOUT` | `5.0` | Per-source wall-clock budget. |
| `FEDERATED_SEARCH_CACHE_TTL` | `600` | |
| `FEDERATED_SEARCH_MAX_EXTERNAL_OFFSET` | `200` | |
| `FEDERATED_ALLOWED_HOSTS` | `id.loc.gov` | Hosts `/external/resources` may fetch. |

## What id.loc.gov actually does

Verified live on 2026-09-22 and pinned by the recorded fixtures in
`tests/loc-suggest2-*.json`. Three of these will silently break an adapter
written from a reasonable reading of the docs:

1. **Paging uses `offset`, not `start`.** `start=21` is accepted and ignored —
   the response still echoes `"start": 1` and returns page one.
2. **`rank` is not a relevance score.** It is a static per-access-point weight.
3. **The query is echoed back with a trailing `*`, but do not rely on it.**
   `melville moby` comes back as `melville moby*`, yet `moby dic*` finds
   nothing while `moby dick*` finds 390 and `moby di*` finds 2 — so it is not
   a plain prefix match over the term index. Either way the query must not go
   through `format_query`, whose tsquery operators would be sent literally.

Neither pool tolerates a typo. `searchtype=keyword` matches tokens exactly, with
no fuzzy fallback and no did-you-mean, so `nmoby dick` returns zero; Blue Core's
own `to_tsquery` ANDs the terms and misses too. Worth knowing before a cataloger
reads an empty page as "no such record exists".

Also: `.cbd.jsonld` exists for **instances only** — a work returns 403 for it,
so the copy path uses the plain `.jsonld`.

## Measurements

Corpus: 23,810,395 Works / 23,017,769 Instances / 2,964,985 Hubs.
There is **no bulk export of Works or Instances** — only authorities,
vocabularies and BIBFRAME Hubs.

Latency, `type=works`, cold: p50 1.7s, max 2.2s over 12 known-item queries.
Warm through LC's own Varnish: ~0.1s. Blue Core local search: 0.26–1.4s. The
fan-out is `max()`, not `sum()`.

### Relevance, and the local re-ranking that fixes it

suggest2's own order is poor for known-item lookup: it ranks works *about* a
title above the title itself. Searching "achebe things fall apart" returns
criticism for the entire first page and not the novel. Both genuinely match the
query -- what separates them is that the novel is titled "Things fall apart"
while the criticism is "The rhetorical implications of Chinua Achebe's Things
fall apart".

So the adapter pulls a window of 25 hits and reorders them locally, scoring
each on the query alone: does a contributor match, does the title carry every
non-author query token, in order, and is it concise. `benchmarks/loc_relevance.py`
measures it over 24 known-item queries -- 12 the heuristic was written against
and 12 held back:

| | top-1 | top-3 | top-10 | MRR |
|---|---|---|---|---|
| suggest2 order, design set | 4/12 | 7/12 | 9/12 | 0.49 |
| **re-ranked, design set** | **11/12** | **11/12** | **11/12** | **0.92** |
| suggest2 order, held-out set | 2/12 | 3/12 | 7/12 | 0.24 |
| **re-ranked, held-out set** | **10/12** | **10/12** | **10/12** | **0.83** |

The held-out numbers are the ones to believe, and they are the stronger pair,
which is the opposite of what overfitting looks like. Scoring is deliberately
strict -- a hit counts only if its title, minus any name/title access point
prefix, *starts with* the expected title and its contributors name the expected
author. A looser substring match scores the unranked results 12/12 and is
useless, because a book about *The Crying of Lot 49* has that string in its
title.

Costs one extra parameter on a request we were making anyway: `count=25`
instead of `count=limit`. Re-ranking applies within the window fetched for the
current offset, so a deeper page reorders its own window rather than the whole
result set.

What did **not** help, all measured:

- **`searchtype=left-anchored`** scores 0/12. It only matches a prefix of an
  access point, so it needs "Melville, Herman, 1819-1891. Moby-Dick" rather
  than what a cataloger types. Earlier notes here suggested trying it for
  known-item lookup; that was wrong. It remains more forgiving of partial input.
- **Quoting the query** scores 0/12 -- suggest2 treats the quotes literally.
- **Searching the instances directory** scores 2/12.
- **`/search/` with `rdftype:` qualifiers** (the only field qualifiers that
  endpoint accepts -- `title:`, `contributor:`, `lccn:` all return nothing)
  is a wash with plain suggest2, and loses the `more` block that supplies
  contributors, the linked instance and last-modified dates.
- **suggest2's own `rdftype` parameter** validates its value and rejects every
  form tried, including full class URIs. It appears non-functional.
- **Dropping the author from the query** is much worse (2/12 top-1), which is
  reassuring: catalogers naturally type author and title together.

Two queries miss under every strategy: "darwin on the origin of species" and
"bronte jane eyre". The second is at least partly a scoring artifact -- the
contributor is "Brontë" and the benchmark's normalization keeps the diaeresis.

## Politeness

`id.loc.gov/robots.txt` says `Crawl-delay: 3` and warns that access may be
blocked for irresponsible use — and a block would land on every id.loc.gov user
at the institution, not just Blue Core. So:

- One identifiable `User-Agent` with a contact URL, and one client for the
  process rather than one per cataloger's browser.
- Responses cached for ten minutes, with single-flight coalescing so
  simultaneous identical searches share one request rather than all missing a
  cache nothing has filled yet.
- Egress capped at 4 concurrent requests; `429` reported, never retried.
- `type=all` queries one directory, not three.
- Deep paging refused past offset 200 without a request.
- No prefetching, no cache pre-warming, no crawling.

A literal 3-second delay is deliberately *not* implemented: crawl-delay governs
crawlers enumerating a site, and these are user-initiated, cacheable point
queries against a documented JSON API that LC serves with
`access-control-allow-origin: *`. Worth writing to LC before this goes live, to
say what we are doing and ask what rate they are comfortable with.

## Known gaps

- **Provenance on save is not wired up.** `local_uri` and `bluecore_uri` tell a
  client we already hold a copy, but the editor's copy path posts a blank-node
  subject, so `save_graph` writes no `bf:derivedFrom` and the dedup never fires.
  Adding it inverts the failure rather than removing it — see the note below.
  This needs a decision before real cataloging is enabled.
- No circuit breaker. A source that is down costs its 5s budget on every search
  rather than failing fast.
- Share-VDE is not implemented. The adapter Protocol is the whole answer, but
  there is no usable public API today: `lookup.ld4l.org`'s linked-data
  authorities — including the three ShareVDE entries already in sinopia_editor's
  `searchConfig.json` — return `Unable to initialize linked data authority`, and
  `svde.org` returns 429 to an unauthenticated request. That needs a
  conversation with Casalini, not code.
- `contribution[].@type` in framed LC data is an array and the agent label is
  `rdfs:label`, while the editor's `hitsToResult` tests for a string and reads
  `agent.label`. Titles and types render; the contributor line comes out blank.

### The duplication decision

Worth raising as a policy question rather than settling in code:

- **Today**, a copy records no provenance, so two catalogers copying the same LC
  work produce two unrelated Blue Core resources with no way to tell after the
  fact. Silent duplication.
- **If `derivedFrom` is added**, `_keep_existing` returns `False` for
  `POST /works/` (it only holds on the ingest path), so the second cataloger
  would overwrite the first cataloger's record and get a 201 back. Silent
  clobber.

Recommended: record `derivedFrom` — undetectable duplication is worse than
recoverable clobber — surface the "already in Blue Core" annotation *before* the
write, and make `POST` return 409 with the existing URI on a dedup hit so it
becomes a cataloger's choice.
