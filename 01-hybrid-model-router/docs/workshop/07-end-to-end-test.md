# 07 — End-to-end test

**Goal:** prove each routing path works: rules, the semantic cache, the
background judge, and the circuit breaker's fallback to Bedrock.

Run these from a **CloudShell VPC environment** (set up in
[02](02-gateway.md#test-it-from-cloudshell)) with `ALB` and `KEY` set.

## 1. A helper

```bash
ask(){
  local extra=""; [ -n "$2" ] && extra=",\"metadata\":{\"tags\":[\"$2\"]}"
  curl -s -D /tmp/h -o /tmp/b $ALB/v1/chat/completions \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"${3:-auto}\",\"max_tokens\":60$extra,\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}]}" \
    -w "%{http_code} %{time_total}s "
  grep -i '^x-litellm-model-group' /tmp/h | tr -d '\r' | cut -d' ' -f2 | tr '\n' ' '
  echo " ${1:0:60}"
}
```

The `x-litellm-model-group` response header says which backend answered:
`vllm-local` (the spot GPU) or `bedrock-claude`.

## 2. The scenarios

```bash
# A. Short extraction: rules say standard -> vLLM
ask "Extract the invoice number from: INV-4471, due 2026-11-01."

# B. Reasoning tag: hard rule -> Bedrock, no cache or judge
ask "Is a verbal contract enforceable?" reasoning

# C. Over 2,000 tokens: hard rule -> Bedrock
ask "Summarize: $(printf 'The quarterly report shows revenue growth. %.0s' {1..200})"

# D. A request like A, after the judge stored A's verdict -> cache hit -> vLLM
sleep 5
ask "Extract the invoice number from: INV-9902, due 2026-12-15."

# E. Complex wording without a tag: the judge marks it complex, so the
#    similar second request hits the cache and goes to Bedrock
ask "Compare the liability clauses in contracts A and B and flag risks."
sleep 5
ask "Compare the indemnity terms in contracts C and D and flag risks."

# F. Caller names a model: the router steps aside
ask "Say hello." "" bedrock-claude
```

## You should see

| Scenario | Answered by | Router log |
|---|---|---|
| A | `vllm-local` | `route.decision source=rule ... cache=miss`, then `route.judged tier=standard cached=1` |
| B, C | `bedrock-claude` | only `route.chosen model=bedrock-claude` |
| D | `vllm-local` | `route.decision source=cache ... cache=hit cached_tier=standard similarity=0.9x` |
| E, 2nd | `bedrock-claude` | `cache=hit cached_tier=complex rule_tier=standard` |
| F | `bedrock-claude` | no `route.*` lines |

Measured in the rehearsal (from inside the VPC):

```
== A. short extraction (rules say standard)
  HTTP/1.1 200 OK | x-litellm-model-group: vllm-local
  -> The invoice number is INV-4471.
== B. reasoning tag (rule says complex)
  HTTP/1.1 200 OK | x-litellm-model-group: bedrock-claude
== C. similar extraction (semantic cache)
  HTTP/1.1 200 OK | x-litellm-model-group: vllm-local
```

```
route.decision source=rule mode=active cache=miss
route.chosen model=vllm-local
route.chosen model=bedrock-claude
route.judged tier=standard cached=1
route.decision source=cache mode=active cache=hit cached_tier=standard rule_tier=standard similarity=0.941
route.chosen model=vllm-local
```

The gateway runs 2 tasks, each with its own in-memory cache, so a request can
miss once on each task before both hit.

Read the router's decisions:

```bash
aws logs tail /aws/ecs/<name>-gateway/litellm-gateway --region us-east-1 \
  --since 15m --format short --filter-pattern route
```

## 3. The fallback

Pause vLLM ([06](06-vllm.md#turning-the-gpu-off-between-sessions)) and rerun
scenario A. The circuit breaker can't read vLLM's queue, so A goes to
`bedrock-claude` — the caller still gets an answer.
