import os
import sys

import pytest
from python_a2a import Task

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


class StubResponse:
    """Minimal stand-in for a ``requests`` response."""

    def __init__(self, payload=None, status_code=200, raise_for_status=None):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self._raise_for_status = raise_for_status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self._raise_for_status:
            raise self._raise_for_status


class StubClient:
    """Stand-in for an ``A2AClient`` that records the questions it is asked."""

    def __init__(self, answer="", error=None):
        self.answer = answer
        self.error = error
        self.questions = []

    def ask(self, question):
        self.questions.append(question)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def stub_response():
    return StubResponse


@pytest.fixture
def stub_client():
    return StubClient


@pytest.fixture
def make_task():
    def _make_task(text, google_format=False):
        if google_format:
            message = {"role": "user", "parts": [{"type": "text", "text": text}]}
        else:
            message = {"role": "user", "content": {"type": "text", "text": text}}
        return Task(message=message)

    return _make_task
