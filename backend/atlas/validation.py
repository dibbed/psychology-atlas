from rest_framework.exceptions import ValidationError


def positive_int(value, *, field: str, maximum: int | None = None) -> int:
    """Parse a positive integer without allowing pathological giant integer strings."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValidationError({field: "مقدار باید یک عدد صحیح مثبت باشد."})

    if isinstance(value, str):
        value = value.strip()
        if not value or not value.isascii() or not value.isdigit() or len(value) > 12:
            raise ValidationError({field: "مقدار باید یک عدد صحیح مثبت معتبر باشد."})

    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError({field: "مقدار باید یک عدد صحیح مثبت معتبر باشد."})

    if parsed <= 0:
        raise ValidationError({field: "مقدار باید بزرگ‌تر از صفر باشد."})
    if maximum is not None and parsed > maximum:
        raise ValidationError({field: f"مقدار نمی‌تواند بیشتر از {maximum} باشد."})
    return parsed
