"""Show which harness version each endpoint serves (walkthrough step B1).

python -m harnesskit.release --stack refund-harness
"""

import argparse
import sys

import boto3

from harnesskit.cli import stack_outputs


def release_report(control, harness_id: str) -> list[str]:
    versions = sorted(
        (v["harnessVersion"] for v in control.list_harness_versions(harnessId=harness_id)["harnessVersions"]),
        key=int,
    )
    lines = [
        f"versions: {', '.join(versions)}",
        f"{'DEFAULT':<8} -> version {versions[-1]} (always the latest)",
    ]
    for ep in control.list_harness_endpoints(harnessId=harness_id)["endpoints"]:
        if ep["endpointName"] == "DEFAULT":
            continue
        lines.append(f"{ep['endpointName']:<8} -> version {ep.get('liveVersion') or ep.get('targetVersion')}")
    return lines


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stack", default="refund-harness")
    p.add_argument("--region", default="us-east-1")
    args = p.parse_args(argv)
    session = boto3.Session(region_name=args.region)
    outputs = stack_outputs(session.client("cloudformation"), args.stack)
    print("\n".join(release_report(session.client("bedrock-agentcore-control"), outputs["HarnessId"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
