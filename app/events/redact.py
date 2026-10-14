import re

_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s\-().]{8,}\d(?!\w)")


def mask_phones(text: str) -> str:
    if not text:
        return text
    return _PHONE_RE.sub("[redacted-phone]", text)
