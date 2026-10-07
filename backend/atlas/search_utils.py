from django.db.models import Case, Exists, IntegerField, Q, Value, When


_ARABIC_TO_PERSIAN = str.maketrans({
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
})
_PERSIAN_TO_ARABIC = str.maketrans({
    "ی": "ي",
    "ک": "ك",
})


def search_variants(value: str):
    value = value.strip()
    if not value:
        return ()
    return tuple(dict.fromkeys((
        value,
        value.translate(_ARABIC_TO_PERSIAN),
        value.translate(_PERSIAN_TO_ARABIC),
    )))


def icontains_any(fields, value: str):
    query = Q()
    for variant in search_variants(value):
        for field in fields:
            query |= Q(**{f"{field}__icontains": variant})
    return query


def ranked_public_search(queryset, value, aliases, fields, *, extra_match=None):
    """Aliases must already be public and correlated to the canonical owner."""
    match = icontains_any(fields, value) | Exists(aliases.filter(icontains_any(("text",), value)))
    if extra_match is not None:
        match |= extra_match
    exact, exact_alias = Q(), Q()
    for variant in search_variants(value):
        for field in ("name_en", "name_fa", "slug"):
            exact |= Q(**{field + "__iexact": variant})
        exact_alias |= Q(text__iexact=variant)
    return queryset.filter(match).annotate(search_rank=Case(
        When(exact | Exists(aliases.filter(exact_alias)), then=Value(0)),
        default=Value(1), output_field=IntegerField(),
    )).distinct().order_by("search_rank", "name_en", "id")
