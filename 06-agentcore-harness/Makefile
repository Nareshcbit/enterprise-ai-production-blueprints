# AgentCore harness kit. Targets follow the walkthrough's steps:
# https://nmadiraju.com/posts/genai-how-agentcore-harness-works/
# Everything except `setup`, `test` and `lint` uses your AWS account and costs money. Run `make teardown` after.
PY ?= python3
STACK ?= refund-harness
REGION ?= us-east-1
CRASH_ACTOR ?= customer-3001
AWS := aws --region $(REGION)
CLI := $(PY) -m harnesskit.cli --stack $(STACK) --region $(REGION)
OUT = $(AWS) cloudformation describe-stacks --stack-name $(STACK) --query "Stacks[0].Outputs[?OutputKey=='$(1)'].OutputValue" --output text

.PHONY: setup test lint deploy ops A1 B1 B1-promote B1-rollback B2 B4 C2 D1 D2 D3 teardown

setup:        ## install dependencies (boto3 1.43.126 or later is needed for harness endpoints)
	$(PY) -m pip install -r requirements.txt

test:         ## unit tests, offline
	$(PY) -m pytest -q

lint:
	ruff check . && ruff format --check .

deploy:       ## create or update the stack (about 10 minutes the first time)
	$(AWS) cloudformation deploy --stack-name $(STACK) --template-file infra/harness.yaml \
	  --capabilities CAPABILITY_NAMED_IAM --tags project=agentcore-harness-kit $(if $(PARAMS),--parameter-overrides $(PARAMS))

ops:          ## alarms on the prod endpoint and a CloudTrail trail for harness invokes (step D3)
	$(AWS) cloudformation deploy --stack-name $(STACK)-ops --template-file ops/alarms.yaml \
	  --parameter-overrides HarnessStack=$(STACK) $(if $(EMAIL),AlarmEmail=$(EMAIL))

A1:           ## one refund request, end to end, through the prod endpoint
	$(CLI) --order A-1042 --actor customer-1042 --auto-approve

B1:           ## new instructions = new version. DEFAULT moves at once; prod stays put
	$(MAKE) deploy PARAMS='Instructions="You help customers with duplicate charges. Look up the order first. Refund only an exact duplicate, with the refund tool. Reply in one sentence."'
	$(PY) -m harnesskit.release --stack $(STACK) --region $(REGION)

B1-promote:   ## after testing, point prod at the newest version (in code: the ProdVersion parameter)
	$(MAKE) deploy PARAMS="ProdVersion=$$($(call OUT,HarnessVersion))"

B1-rollback:  ## point prod back at version 1
	$(MAKE) deploy PARAMS='ProdVersion=1'

B2:           ## the refund stops for a person's approval in your app
	$(CLI) --order A-1042 --actor customer-1042

B4:           ## two customers, two actor IDs: memory stays apart
	$(CLI) --order A-2001 --actor customer-2001 --auto-approve \
	  --prompt "My name is Priya and my card ends in 4417. Is order A-2001 charged twice?"
	$(CLI) --order A-1042 --actor customer-1042 --auto-approve \
	  --prompt "What card do I have on file, and what is my name?"

C2:           ## show the execution role the stack created
	$(AWS) iam get-role-policy --role-name $(STACK)-BedrockAgentCore-harness --policy-name refund-harness \
	  --query PolicyDocument.Statement[].Sid --output text

D1:           ## crash after paying, before answering (fresh actor: memory of earlier refunds would skip it)
	-$(CLI) --order A-1042 --actor $(CRASH_ACTOR) --auto-approve --crash-after-pay

D2:           ## rerun after the crash: the same refund ID returns the first refund
	@test -n "$(SESSION)" || (echo "usage: make D2 SESSION=<id printed by make D1>"; exit 1)
	$(CLI) --order A-1042 --actor $(CRASH_ACTOR) --auto-approve --session $(SESSION)
	$(AWS) dynamodb scan --table-name $$($(call OUT,PaymentsTable)) --query "Items[].refund_id.S" --output text

D3:           ## the metrics the harness emitted (alarms in ops/alarms.yaml use these)
	$(AWS) cloudwatch list-metrics --namespace AWS/Bedrock-AgentCore --query "Metrics[].MetricName" --output text

teardown:     ## delete everything (the KMS key is scheduled for deletion in 7 days)
	-$(AWS) s3 rm --recursive s3://$$($(AWS) cloudformation describe-stacks --stack-name $(STACK)-ops --query "Stacks[0].Outputs[0].OutputValue" --output text)
	-$(AWS) cloudformation delete-stack --stack-name $(STACK)-ops
	-$(AWS) cloudformation wait stack-delete-complete --stack-name $(STACK)-ops
	$(AWS) cloudformation delete-stack --stack-name $(STACK)
	$(AWS) cloudformation wait stack-delete-complete --stack-name $(STACK)
