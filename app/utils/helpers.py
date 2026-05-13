from pathlib import Path


def safe_filename(filename):
    return Path(filename).name.replace(" ", "_")


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()

