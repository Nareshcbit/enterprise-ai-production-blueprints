"""Command line for the Make targets: one refund conversation against the deployed stack.

python -m harnesskit.cli --order A-1042 --actor customer-1042 [--auto-approve] [--crash-after-pay]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3

from harnesskit.agent import SimulatedCrash, Target, make_session_id, run
from harnesskit.payments import DynamoPayments
from harnesskit.pending import PendingStore
from harnesskit.stream import ToolCall


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run one refund conversation against the harness.")
    p.add_argument("--stack", default=os.environ.get("STACK", "refund-harness"))
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--order", required=True)
    p.add_argument("--actor", required=True, help="the customer's ID, sent as actorId")
    p.add_argument("--endpoint", default="prod", help="named endpoint (qualifier); DEFAULT is the latest")
    p.add_argument("--session", help="reuse a session ID")
    p.add_argument("--prompt", help="override the customer's message")
    p.add_argument("--auto-approve", action="store_true", help="approve refunds without asking")
    p.add_argument("--crash-after-pay", action="store_true", help="crash after paying, before answering")
    return p.parse_args(argv)


def stack_outputs(cfn, stack: str) -> dict[str, str]:
    outputs = cfn.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def build_target(outputs: dict[str, str], args: argparse.Namespace) -> Target:
    return Target(harness_arn=outputs["HarnessArn"], qualifier=args.endpoint)


def ask_person(call: ToolCall) -> bool:
    print(f"\nAPPROVAL NEEDED  {call.name} {json.dumps(call.input)}")
    return input("Approve? [y/N] ").strip().lower() == "y"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    session = boto3.Session(region_name=args.region)
    outputs = stack_outputs(session.client("cloudformation"), args.stack)
    payments = DynamoPayments(session.client("dynamodb"), outputs["PaymentsTable"])
    session_id = args.session or make_session_id(args.actor, args.order)
    prompt = args.prompt or f"I was charged twice for order {args.order}. Please refund the duplicate."
    print(f"session {session_id}\nactor   {args.actor}\nendpoint {args.endpoint}")
    try:
        result = run(
            session.client("bedrock-agentcore"),
            build_target(outputs, args),
            session_id,
            args.actor,
            prompt,
            approve=(lambda c: True) if args.auto_approve else ask_person,
            payments=payments,
            crash_after_pay=args.crash_after_pay,
            pending=PendingStore(Path(".state/pending")),
        )
    except SimulatedCrash as crash:
        print(f"\nCRASH  {crash}\nrerun with: --session {session_id}")
        return 2
    print(f"\ntools the harness ran: {result.tools_run}\nstop: {result.stop_reason}  usage: {result.usage}")
    print(f"\n{result.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
