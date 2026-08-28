from django.db.models import Q


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
