"""The command line reads the stack's outputs and builds the right target (Make targets)."""

from harnesskit.cli import build_target, parse_args, stack_outputs


class FakeCfn:
    def describe_stacks(self, StackName):
        return {
            "Stacks": [
                {
                    "Outputs": [
                        {
                            "OutputKey": "HarnessArn",
                            "OutputValue": "arn:aws:bedrock-agentcore:us-east-1:1:harness/refund-AbCdEfGhIj",
                        },
                        {"OutputKey": "PaymentsTable", "OutputValue": "refund-payments"},
                    ]
                }
            ]
        }


def test_outputs_become_a_dict():
    outputs = stack_outputs(FakeCfn(), "refund-harness")
    assert outputs["PaymentsTable"] == "refund-payments"


def test_prod_endpoint_is_the_default():
    args = parse_args(["--order", "A-1042", "--actor", "customer-1042"])
    target = build_target({"HarnessArn": "arn:x"}, args)
    assert target.qualifier == "prod"


def test_default_endpoint_can_be_chosen_explicitly():
    args = parse_args(["--order", "A-1042", "--actor", "customer-1042", "--endpoint", "DEFAULT"])
    assert build_target({"HarnessArn": "arn:x"}, args).qualifier == "DEFAULT"
