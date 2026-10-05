"""Assert required workbook XML values before converting them to numbers."""

from xml.etree.ElementTree import Element


def required_text(
    element: Element, path: str, namespaces: dict[str, str] | None = None
) -> str:
    value = element.findtext(path, namespaces=namespaces)
    assert value, f"Missing XML text: {path}"
    return value


def required_attribute(element: Element | None, name: str) -> str:
    assert element is not None, f"Missing XML element for attribute: {name}"
    value = element.get(name)
    assert value is not None, f"Missing XML attribute: {name}"
    return value
