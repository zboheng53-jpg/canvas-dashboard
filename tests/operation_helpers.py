"""Resolve the documented 202/status protocol in result-oriented API tests."""
import json
import time

from flask.testing import FlaskClient
from werkzeug.test import TestResponse


class OperationClient(FlaskClient):
    def open(self, *args, **kwargs):
        response = super().open(*args, **kwargs)
        if response.status_code != 202 or not response.json.get("async_task"):
            return response
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = super().open(response.json["status_url"]).json
            if result.get("state") == "done":
                return TestResponse(json.dumps(result["result"]), status=result["result_status"],
                                    headers=result.get("result_headers", {}), mimetype="application/json", request=response.request)
            time.sleep(0.01)
        raise AssertionError("operation did not complete within 10 seconds")


def operation_client(app):
    return OperationClient(app, app.response_class)


def wait_weather(client, campus="siping"):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get("/api/weather?campus=" + campus)
        if not response.json.get("pending"):
            return response
        time.sleep(0.01)
    raise AssertionError("weather refresh did not complete")
