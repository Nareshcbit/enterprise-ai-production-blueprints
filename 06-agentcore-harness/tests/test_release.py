"""Which version each endpoint serves (walkthrough step B1)."""

from harnesskit.release import release_report


class FakeControl:
    def list_harness_versions(self, harnessId):
        return {
            "harnessVersions": [
                {"harnessVersion": "1", "status": "READY"},
                {"harnessVersion": "2", "status": "READY"},
            ]
        }

    def list_harness_endpoints(self, harnessId):
        return {
            "endpoints": [
                {"endpointName": "DEFAULT", "liveVersion": "2"},
                {"endpointName": "prod", "liveVersion": "1", "targetVersion": "1"},
            ]
        }


def test_report_shows_latest_version_and_what_each_endpoint_serves():
    lines = release_report(FakeControl(), "refund_agent-AbCdEfGhIj")
    assert lines == [
        "versions: 1, 2",
        "DEFAULT  -> version 2 (always the latest)",
        "prod     -> version 1",
    ]
