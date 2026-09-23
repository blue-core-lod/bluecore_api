"""Measure how well id.loc.gov answers known-item lookups, with and without
the adapter's local re-ranking.

    uv run python benchmarks/loc_relevance.py

Hits id.loc.gov live, sequentially, with a short pause between requests. About
fifty requests for the default run.

Scoring: a hit counts when its title -- minus any name/title access point
prefix -- starts with the expected title, and its contributors name the
expected author. That is strict enough to exclude criticism, which is the whole
difficulty: "The rhetorical implications of Chinua Achebe's Things fall apart"
matches the query as well as the novel does. An earlier version of this
benchmark scored a plain substring match and reported a misleading 12/12.

DESIGN_SET is the set the comparison heuristic was written against. HELDOUT_SET
was not looked at while writing it, and is the one to believe.

The "reranked" column is a yardstick, not a proposal: the adapter deliberately
returns suggest2's own order. What the two columns together say is how much
relevance is being left on the table upstream, which is the input to deciding
whether Blue Core needs a search index of its own rather than a live lookup.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, "src")

from bluecore_api.federated.base import FederatedResult
from bluecore_api.federated.sources.loc import summary_jsonld

USER_AGENT = "BlueCore-API/relevance-benchmark (+https://bcld.info/)"
PAUSE_SECONDS = 0.4

# (query a cataloger would type, expected work title, expected author surname)
DESIGN_SET = [
    ("melville moby dick", "moby dick", "melville"),
    ("pynchon crying of lot 49", "crying of lot 49", "pynchon"),
    ("tolstoy war and peace", "war and peace", "tolstoy"),
    ("morrison beloved", "beloved", "morrison"),
    ("austen pride and prejudice", "pride and prejudice", "austen"),
    ("achebe things fall apart", "things fall apart", "achebe"),
    ("woolf mrs dalloway", "mrs dalloway", "woolf"),
    ("borges ficciones", "ficciones", "borges"),
    (
        "kuhn structure of scientific revolutions",
        "structure of scientific revolutions",
        "kuhn",
    ),
    ("carson silent spring", "silent spring", "carson"),
    ("baldwin the fire next time", "fire next time", "baldwin"),
    ("ellison invisible man", "invisible man", "ellison"),
]

HELDOUT_SET = [
    ("hemingway the old man and the sea", "old man and the sea", "hemingway"),
    ("dickens great expectations", "great expectations", "dickens"),
    ("darwin on the origin of species", "origin of species", "darwin"),
    ("adam smith wealth of nations", "wealth of nations", "smith"),
    ("friedan the feminine mystique", "feminine mystique", "friedan"),
    ("hurston their eyes were watching god", "their eyes were watching god", "hurston"),
    (
        "angelou i know why the caged bird sings",
        "i know why the caged bird sings",
        "angelou",
    ),
    ("said orientalism", "orientalism", "said"),
    ("chomsky syntactic structures", "syntactic structures", "chomsky"),
    ("steinbeck the grapes of wrath", "grapes of wrath", "steinbeck"),
    ("bronte jane eyre", "jane eyre", "bronte"),
    ("thoreau walden", "walden", "thoreau"),
]

ARTICLES = ("the ", "a ", "an ")


# ---------------------------------------------------------------------------
# A local reordering, for comparison only.
#
# This is NOT what the adapter does. It lives here because the interesting
# question is not "can we patch LC's ranking" -- we can, cheaply -- but "how
# far off is LC's own ranking", and the gap between the two columns is the
# answer. Reordering in the adapter would hide that gap behind a heuristic,
# and the gap is the evidence for whether Blue Core needs its own index.
# ---------------------------------------------------------------------------
def rerank(query: str, results: list[FederatedResult]) -> list[FederatedResult]:
    """Prefer a concise title carrying every non-author query token, in order."""

    def score(result: FederatedResult) -> float:
        query_tokens = normalize(query).split()
        title = main_title(result)
        agents = agent_names(result)
        author_tokens = [t for t in query_tokens if t in agents]
        title_tokens = [t for t in query_tokens if t not in author_tokens]
        value = 2.0 if author_tokens else 0.0
        if title_tokens and all(t in title for t in title_tokens):
            value += 2.0
            if title.startswith(" ".join(title_tokens)):
                value += 3.0
        # A study of a book repeats its title and adds a great many words.
        return value - 0.02 * len(title.split())

    return sorted(results, key=score, reverse=True)


def normalize(text: str) -> str:
    text = (text or "").casefold().replace("&", " and ")
    text = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()
    for article in ARTICLES:
        if text.startswith(article):
            return text[len(article) :]
    return text


def fetch(query: str, count: int = 25) -> list[FederatedResult]:
    """One suggest2 works search, mapped the way the adapter maps it."""
    url = "https://id.loc.gov/resources/works/suggest2/?" + urllib.parse.urlencode(
        {"q": query, "searchtype": "keyword", "count": count, "offset": 0}
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except Exception as error:  # noqa: BLE001 - a benchmark, not a service
            if attempt == 2:
                print(f"  giving up on {query!r}: {error}")
                return []
            time.sleep(2 * (attempt + 1))
    return [
        FederatedResult(
            source="loc",
            source_label="Library of Congress",
            uri=hit["uri"],
            type="works",
            data=summary_jsonld(hit),
        )
        for hit in payload.get("hits", [])
    ]


def rank_of(results: list[FederatedResult], title: str, author: str) -> int | None:
    wanted = normalize(title)
    for position, result in enumerate(results, start=1):
        if main_title(result).startswith(wanted) and author in agent_names(result):
            return position
    return None


def main_title(result: FederatedResult) -> str:
    titles = result.data.get("title")
    if isinstance(titles, list) and titles and isinstance(titles[0], dict):
        return normalize(str(titles[0].get("mainTitle", "")))
    return ""


def agent_names(result: FederatedResult) -> str:
    contributions = result.data.get("contribution")
    if not isinstance(contributions, list):
        return ""
    names = []
    for contribution in contributions:
        if isinstance(contribution, dict):
            agent = contribution.get("agent")
            if isinstance(agent, dict):
                names.append(str(agent.get("label", "")))
    return normalize(" ".join(names))


def report(label: str, tasks: list[tuple[str, str, str]]) -> None:
    print(f"\n=== {label} ({len(tasks)} known-item queries)")
    print(f"{'query':<42}{'as-is':>7}{'reranked':>10}")
    scores: dict[str, list[int | None]] = {"as-is": [], "reranked": []}
    for query, title, author in tasks:
        hits = fetch(query)
        as_is = rank_of(hits[:10], title, author)
        reranked = rank_of(rerank(query, hits)[:10], title, author)
        scores["as-is"].append(as_is)
        scores["reranked"].append(reranked)
        print(f"{query[:42]:<42}{as_is or '-':>7}{reranked or '-':>10}")
        time.sleep(PAUSE_SECONDS)

    print(f"\n{'':<12}{'top-1':>7}{'top-3':>7}{'top-10':>8}{'MRR':>7}")
    for name, ranks in scores.items():
        total = len(ranks)
        print(
            f"{name:<12}"
            f"{sum(1 for r in ranks if r == 1):>7}"
            f"{sum(1 for r in ranks if r and r <= 3):>7}"
            f"{sum(1 for r in ranks if r):>8}"
            f"{sum(1 / r for r in ranks if r) / total:>7.2f}"
        )


if __name__ == "__main__":
    report("DESIGN SET (heuristic was written against this)", DESIGN_SET)
    report("HELD-OUT SET (believe this one)", HELDOUT_SET)
