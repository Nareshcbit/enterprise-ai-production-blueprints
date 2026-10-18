# Project 2: Enterprise Hybrid RAG with Automated CI/CD "Shift-Left" Evaluation

## The Enterprise Problem It Solves

Most RAG proofs-of-concept fail in production because naive vector search returns irrelevant context, models hallucinate, and engineers have no objective way to test whether a prompt or chunking tweak broke the application.

```
                                [ CI/CD Pipeline ]
                                        │ (PR / Code Change)
                                        ▼
                         [ Synthetic Golden Dataset ]
                                (50 test queries)
                                        │
                                        ▼
                          [ Hybrid Retrieval Engine ]
                           ├── Amazon OpenSearch Serverless (Dense Vector)
                           ├── BM25 Keyword Search
                           └── Reciprocal Rank Fusion (RRF) + BGE Reranker
                                        │
                                        ▼
                             [ Generation (Bedrock) ]
                                        │
                                        ▼
                             [ Ragas Evaluation Gate ]
                           ├── Context Recall    (Target: ≥ 0.85)
                           ├── Context Precision (Target: ≥ 0.85)
                           ├── Faithfulness      (Target: ≥ 0.90)
                           └── Answer Relevance  (Target: ≥ 0.85)
                                        │
                      ┌─────────────────┴─────────────────┐
                      ▼ (Pass)                            ▼ (Fail)
               [ Deploy to EKS / ECS ]             [ Block PR Merge ]
```

## What You Build (The Deliverables)

### Data Ingestion & Hybrid Search Pipeline
- Deploy an Amazon OpenSearch Serverless collection via Terraform.
- Write an ingestion worker that extracts text from messy PDFs, applies semantic chunking, and stores both vector embeddings (Amazon Titan Embeddings v2) and raw text for BM25.
- Implement a two-stage retrieval algorithm: Hybrid search using Reciprocal Rank Fusion (RRF), followed by a cross-encoder reranker (e.g., Cohere or BGE-Reranker) to return top-5 chunks.

### Bedrock Guardrails Integration
- Configure an Amazon Bedrock Guardrail to intercept PII (SSNs, credit card numbers) and block prompt injection attempts.

### Automated "Evals-as-Code" GitHub Actions Pipeline
- Curate a "Golden Dataset" of 30–50 domain-specific questions, target context passages, and expected ground truths.
- Build a pytest suite using the Ragas framework that executes the RAG pipeline against the dataset.
- Configure GitHub Actions to compute the RAG Triad scores. The pipeline fails and blocks the PR if Faithfulness drops below 0.90 or Context Precision drops below 0.85.
