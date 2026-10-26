"""Deterministic, Czech-aware matching for broad product searches.

This deliberately uses a small editable lexicon instead of an external model.
The lexicon is not a full Czech lemmatizer; unknown or ambiguous words stay
visible as lower-confidence matches rather than being silently guessed away.
"""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


_LEXICON_PATH = Path(__file__).with_name("product_terms.json")
try:
    _LEXICON: dict[str, Any] = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    _LEXICON = {}

ALIASES: dict[str, str] = _LEXICON.get("aliases", {})
QUERY_EXPANSIONS: dict[str, set[str]] = {
    key: {key, *values}
    for key, values in _LEXICON.get("query_expansions", {}).items()
}
PRODUCT_TYPES: dict[str, str] = _LEXICON.get("product_types", {})
ANIMAL_TYPES: set[str] = set(_LEXICON.get("animal_types", []))
IGNORED_TOKENS: set[str] = set(_LEXICON.get("ignored_tokens", []))
DISPLAY_NAMES: dict[str, str] = _LEXICON.get("display_names", {})
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_QUANTITY_TOKEN_RE = re.compile(r"^\d+(?:[.,]\d+)?(?:x\d+(?:[.,]\d+)?)?(?:mg|kg|g|ml|cl|dl|l|ks|kus|baleni)$")


def _ascii_text(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def _canonical_token(token: str) -> str:
    return ALIASES.get(token, token)


def tokenize(value: str | None) -> list[str]:
    """Normalize accents, punctuation, measures, and common Czech inflections."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(_ascii_text(value)):
        if raw.isdigit() or _QUANTITY_TOKEN_RE.fullmatch(raw) or len(raw) < 2:
            continue
        token = _canonical_token(raw)
        if token in IGNORED_TOKENS or token.isdigit():
            continue
        tokens.append(token)
    return tokens


def _normalize_exact(value: str | None) -> str:
    text = _ascii_text(value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _contains_sequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    return any(haystack[index:index + len(needle)] == needle for index in range(len(haystack) - len(needle) + 1))


def _excluded(product_name: str, excluded_terms: list[str], excluded_products: list[str]) -> bool:
    # Exact-product exclusions retain quantities and variant markers so
    # excluding "400 g" does not also hide the same brand's "300 g" pack.
    product_norm = _normalize_exact(product_name)
    for excluded_product in excluded_products:
        if _normalize_exact(excluded_product) == product_norm:
            return True
    product_tokens = tokenize(product_name)
    for term in excluded_terms:
        term_tokens = tokenize(term)
        if term_tokens and _contains_sequence(product_tokens, term_tokens):
            return True
    return False


def _query_group(token: str) -> set[str]:
    return QUERY_EXPANSIONS.get(token, {token})


def _display(token: str) -> str:
    return DISPLAY_NAMES.get(token, token)


def _reason(
    query_tokens: list[str],
    product_tokens: list[str],
    matched: list[str],
    missing: list[str],
    suggested_term: str | None,
    fuzzy_token: str | None = None,
) -> str | None:
    matched_text = ", ".join(f"„{_display(token)}“" for token in matched)
    missing_text = ", ".join(f"„{_display(token)}“" for token in missing)

    if fuzzy_token:
        return f"Název je jen podobný hledanému výrazu „{_display(fuzzy_token)}“."
    if suggested_term and missing:
        if matched_text:
            return (
                f"Obsahuje {matched_text}, ale místo hledaného {missing_text} "
                f"se objevuje typ produktu „{_display(suggested_term)}“."
            )
        return f"Nalezen typ produktu „{_display(suggested_term)}“, chybí {missing_text}."
    if missing and matched_text:
        return f"Nalezena část dotazu ({matched_text}); chybí jeho zpřesnění ({missing_text})."
    if missing:
        return f"Ve výsledku chybí hledané výrazy: {missing_text}."
    if matched_text:
        return f"Odpovídá hledaným výrazům {matched_text}."
    return None


def score_product(
    query: str,
    product_name: str | None,
    *,
    match_mode: str = "smart",
    exact_product_name: str | None = None,
    excluded_terms: list[str] | None = None,
    excluded_products: list[str] | None = None,
) -> dict[str, str | None]:
    """Return confidence metadata; ``none`` means the offer must be omitted."""
    name = product_name or ""
    if not name:
        return {"confidence": "none", "match_reason": None, "suggested_exclusion_term": None}

    if _excluded(name, excluded_terms or [], excluded_products or []):
        return {"confidence": "none", "match_reason": None, "suggested_exclusion_term": None}

    if match_mode == "exact":
        # Preserve the legacy exact phrase check, including size letters and
        # package quantities that smart tokenization intentionally ignores.
        exact_norm = _normalize_exact(exact_product_name or query)
        name_norm = _normalize_exact(name)
        if exact_norm and exact_norm in name_norm:
            return {"confidence": "high", "match_reason": None, "suggested_exclusion_term": None}
        return {"confidence": "none", "match_reason": None, "suggested_exclusion_term": None}

    query_tokens = list(dict.fromkeys(tokenize(query)))
    product_tokens = tokenize(name)
    if not query_tokens or not product_tokens:
        return {"confidence": "none", "match_reason": None, "suggested_exclusion_term": None}

    matched: list[str] = []
    missing: list[str] = []
    accepted_tokens: set[str] = set()
    for token in query_tokens:
        group = _query_group(token)
        accepted_tokens.update(group)
        if any(candidate in group for candidate in product_tokens):
            matched.append(token)
        else:
            missing.append(token)

    # Product type words such as "párek" distinguish a different category
    # from the query. Their display labels also provide a safe exclusion chip.
    extra_product_type = next(
        (token for token in product_tokens if token in PRODUCT_TYPES and token not in accepted_tokens),
        None,
    )
    unknown_extra = next(
        (
            token for token in product_tokens
            if token not in accepted_tokens and token not in PRODUCT_TYPES
        ),
        None,
    )

    # A different animal is a meaningful mismatch only if the query specifies
    # an animal. A generic "maso" search should still accept other meats.
    query_animals = set(query_tokens) & ANIMAL_TYPES
    product_animals = set(product_tokens) & ANIMAL_TYPES
    conflicting_animal = next(iter(product_animals - query_animals), None) if query_animals else None
    suggested = extra_product_type or (conflicting_animal if conflicting_animal in DISPLAY_NAMES else None)

    if not matched:
        # Keep typo-adjacent candidates visible as low confidence, but discard
        # unrelated Kupi spillover with no lexical relationship to the query.
        best_pair: tuple[float, str] | None = None
        for query_token in query_tokens:
            for product_token in product_tokens:
                ratio = SequenceMatcher(None, query_token, product_token).ratio()
                if ratio >= 0.82 and (best_pair is None or ratio > best_pair[0]):
                    best_pair = (ratio, query_token)
        if best_pair:
            reason = _reason(query_tokens, product_tokens, [], query_tokens, None, best_pair[1])
            return {"confidence": "low", "match_reason": reason, "suggested_exclusion_term": None}
        return {"confidence": "none", "match_reason": None, "suggested_exclusion_term": None}

    coverage = len(matched) / len(query_tokens)
    if coverage == 1 and suggested is None and unknown_extra is None:
        confidence = "high"
    elif coverage >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    reason = None if confidence == "high" else _reason(
        query_tokens,
        product_tokens,
        matched,
        missing,
        suggested,
    )
    if unknown_extra and not suggested:
        extra_reason = (
            f"Dotaz odpovídá, ale název obsahuje další nerozpoznaný výraz "
            f"„{_display(unknown_extra)}“; může jít o značku nebo jiný typ výrobku."
        )
        reason = f"{reason} {extra_reason}" if reason else extra_reason
    return {
        "confidence": confidence,
        "match_reason": reason,
        "suggested_exclusion_term": _display(suggested) if suggested else None,
    }
