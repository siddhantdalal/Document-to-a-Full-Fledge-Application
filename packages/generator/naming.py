import re


def snake(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip())
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"_+", "_", s)
    return s.lower().strip("_")


def pascal(name: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", name.strip())
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def plural(snake_name: str) -> str:
    if (
        snake_name.endswith("y")
        and len(snake_name) > 1
        and snake_name[-2] not in "aeiou"
    ):
        return snake_name[:-1] + "ies"
    if snake_name.endswith(("s", "x", "z")) or snake_name.endswith(("ch", "sh")):
        return snake_name + "es"
    return snake_name + "s"
