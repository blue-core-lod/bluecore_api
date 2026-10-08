"""Tests for the shared Accept-header parsing.

The policy for wildcards and for a header naming nothing available lives with
each caller -- the resource routes fall back to HTML, app/routes/convert.py
defaults to JSON-LD and raises 406 -- so only the parsing is tested here.
"""

import pytest

from bluecore_api.app.utils.serializer import accept_media_types


@pytest.mark.parametrize(
    "header,expected",
    [
        ("", [""]),
        ("text/turtle", ["text/turtle"]),
        ("application/ld+json, text/turtle", ["application/ld+json", "text/turtle"]),
        # q= is stripped, not ranked: the client's order decides.
        (
            "text/turtle;q=0.1, application/rdf+xml;q=0.9",
            ["text/turtle", "application/rdf+xml"],
        ),
        # Browser-style header, wildcard included and left for the caller.
        (
            "text/html,application/xhtml+xml,*/*;q=0.8",
            ["text/html", "application/xhtml+xml", "*/*"],
        ),
        ("  text/turtle  ,  application/json  ", ["text/turtle", "application/json"]),
        ("application/ld+json;charset=utf-8", ["application/ld+json"]),
    ],
)
def test_accept_media_types(header, expected):
    assert list(accept_media_types(header)) == expected
