import os

import pytest

from voxlibera.server import load_dotenv


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_load_dotenv_reads_common_windows_encodings(tmp_path, monkeypatch, encoding):
    monkeypatch.delenv("VOXLIBERA_TEST_VALUE", raising=False)
    path = tmp_path / ".env"
    path.write_text('# comment\nVOXLIBERA_TEST_VALUE="hello"\n', encoding=encoding)
    load_dotenv(str(path))
    assert os.environ["VOXLIBERA_TEST_VALUE"] == "hello"


def test_environment_variables_win_over_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXLIBERA_TEST_VALUE", "from-environment")
    path = tmp_path / ".env"
    path.write_text("VOXLIBERA_TEST_VALUE=from-file\n", encoding="utf-8")
    load_dotenv(str(path))
    assert os.environ["VOXLIBERA_TEST_VALUE"] == "from-environment"
