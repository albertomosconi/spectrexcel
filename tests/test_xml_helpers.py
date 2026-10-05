from xml.etree import ElementTree as ET

import pytest

from tests.xml_helpers import required_attribute, required_text


def test_required_text_preserves_namespaced_values():
    root = ET.fromstring('<root xmlns="urn:test"><value>0.25</value></root>')
    assert required_text(root, "s:value", {"s": "urn:test"}) == "0.25"


@pytest.mark.parametrize("xml", ["<root/>", "<root><value/></root>"])
def test_required_text_rejects_missing_value(xml):
    with pytest.raises(AssertionError, match="value"):
        required_text(ET.fromstring(xml), "value")


def test_required_attribute_preserves_value():
    assert required_attribute(ET.fromstring('<min val="-0.5"/>'), "val") == "-0.5"


@pytest.mark.parametrize("element", [None, ET.fromstring("<min/>")])
def test_required_attribute_rejects_missing_value(element):
    with pytest.raises(AssertionError, match="val"):
        required_attribute(element, "val")
