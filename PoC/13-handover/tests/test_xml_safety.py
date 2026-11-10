import zipfile

import pytest
from defusedxml.common import DefusedXmlException

from app.hwpx_text import open_with_breaks


def test_hwpx_dtd_is_rejected_before_external_reader(tmp_path):
    path = tmp_path / "untrusted.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", '<!DOCTYPE x [<!ENTITY injected "must-not-expand">]><x>&injected;</x>')
    with pytest.raises(DefusedXmlException):
        open_with_breaks(path)
