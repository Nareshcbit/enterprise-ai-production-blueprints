# Eval harness lab. Each target is one step of the walkthrough
# https://nmadiraju.com/posts/genai-eval-harness/
PY ?= python3

.PHONY: setup A1 A2 A3 B1 B2 B3 B4 C1 C2 D1 D2 test lint check-solutions live live-judge bedrock-eval bedrock-eval-submit

setup:            ## install dependencies
	$(PY) -m pip install -r requirements.txt

A1:               ## one case, one recorded output
	@grep C-1042 data/cases.jsonl
	@grep '"C-1042"' recordings/triage_v1.jsonl

A2:               ## the bug: exact string match on free text
	$(PY) -m harness.run --prompt v1 --grader string

A3:               ## fix: structured output graded in code
	$(PY) -m pytest -q tests/test_step_A3.py
	$(PY) -m harness.run --prompt v2 --show C-1042

B1:               ## the bug: 74% hides the urgent misses
	$(PY) -m harness.run --prompt v2

B2:               ## fix: per-class matrix and urgent recall
	$(PY) -m pytest -q tests/test_step_B2.py
	$(PY) -m harness.run --prompt v2 --per-class

B3:               ## the bug: same prompt, three scores
	$(PY) -m harness.run --prompt v2 --runs 3

B4:               ## fix: majority of 3, margin of error, save the per-case baseline
	$(PY) -m pytest -q tests/test_step_B4.py
	$(PY) -m harness.run --prompt v2 --runs 3 --majority --show C-1042 --save baselines/v2.json

C1:               ## the bug: exact match cannot grade the reason
	@grep '"C-1042"' recordings/triage_v2.jsonl | head -1

C2:               ## fix: an LLM judge, calibrated against adjusters
	$(PY) -m pytest -q tests/test_step_C2.py
	$(PY) -m harness.judge_run

D1:               ## the bug: v3 raises the total and hides regressions
	$(PY) -m harness.run --prompt v3 --runs 3 --majority

D2:               ## fix: the CI gate (exits 1 on v3, 0 on v4)
	$(PY) -m pytest -q tests/test_step_D2.py
	-$(PY) -m harness.ci --candidate v3 --baseline baselines/v2.json
	$(PY) -m harness.ci --candidate v4 --baseline baselines/v2.json

test:             ## all step tests
	$(PY) -m pytest -q

lint:
	ruff check . && ruff format --check .

check-solutions:  ## run every test against solutions/ in a temp copy (your files untouched)
	@tmp=$$(mktemp -d) && cp -R . $$tmp && cp solutions/*.py $$tmp/harness/ && cd $$tmp && $(PY) -m pytest -q

live:             ## same eval against Bedrock (costs money; needs AWS credentials and model access)
	$(PY) -m harness.run --prompt v4 --runs 3 --per-class --majority --live

live-judge:       ## calibrate the judge model on Bedrock
	$(PY) -m harness.judge_run --live

bedrock-eval:     ## free dry run: write the Bedrock Evaluations dataset and print the job request
	$(PY) -m harness.bedrock_eval --dry-run

bedrock-eval-submit: ## real Bedrock Evaluations job on the v2 recordings (costs money: judge tokens)
	@echo "WARNING: starts a Bedrock Evaluations job. You pay for the judge model's tokens"
	@echo "(100 prompts, on-demand pricing). Needs BEDROCK_EVAL_ROLE_ARN and BEDROCK_EVAL_BUCKET."
	@echo "Press Ctrl-C within 5 seconds to cancel." && sleep 5
	$(PY) -m harness.bedrock_eval --submit
