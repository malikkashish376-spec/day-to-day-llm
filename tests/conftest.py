from __future__ import annotations

import pytest

from daytoday.agent import Agent
from daytoday.db import connect, init_db
from daytoday.llm.mock import MockLLM
from daytoday.tools import build_registry


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return str(path)


@pytest.fixture()
def conn(db_path):
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture()
def registry():
    return build_registry()


@pytest.fixture()
def agent(db_path):
    return Agent(client=MockLLM(), db_path=db_path)
