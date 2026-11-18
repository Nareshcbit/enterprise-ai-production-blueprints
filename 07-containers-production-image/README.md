# Project 7: What Makes an Image Production-Ready?

A hands-on lab. You take a naive Dockerfile for a Java 21 Spring Boot service to a production image:
small, cached builds, no secrets in layers, multi-stage, distroless, non-root, multi-arch for Graviton,
pinned by digest and reproducible. Every step proves its point with `docker history`,
`docker image inspect`, `docker buildx imagetools inspect` or a scanner.

It pairs with the hands-on page *What Makes an Image Production-Ready?* on nmadiraju.com. The page's
commands and output are read from `recordings/`, so every number on it comes out of this repo.

## The scenario

PayFlow, a (fictional) bank payments team, runs its payments API on Amazon EKS. The service is Spring
Boot 3.5.16 on Java 21 with web, actuator, validation, spring-kafka, the PostgreSQL driver, Micrometer and
the AWS SDK v2. Its first Dockerfile (`v1`) is the one most teams start with. You fix it one step at a
time, up to `v7`.

> **Dummy secrets.** The working copy has a `.env` and a `settings.xml` so the secret steps have
> something to leak. `tools/prepare_workspace.sh` writes them with made-up values
> (`demo-not-a-real-password`, `demo-not-a-real-token`); they are never committed.

## Quick start

```sh
cd 07-containers-production-image
python3 -m venv .venv && . .venv/bin/activate
make setup
make layers        # replay a step: its commands and the recorded output
make test          # recordings, Dockerfile checks, tool tests
```

Python 3.12, `pytest` and `ruff`. Replaying needs nothing else. To run a step yourself you need Docker
with BuildKit (Docker Engine 23 or later) and, for a real `target/`, Maven and Java 21:

```sh
make local STEP=layers     # builds work/ on first use, writes out/local/layers.txt
```

Your sizes and times will differ from the recordings (your CPU, your Docker storage driver, the day's
base images). The recorded values come from two AWS CodeBuild hosts:

- x86: `aws/codebuild/standard:7.0`, `BUILD_GENERAL1_MEDIUM` (4 vCPU), privileged.
- Arm (Graviton): `aws/codebuild/amazonlinux-aarch64-standard:3.0`, `ARM_CONTAINER`
  `BUILD_GENERAL1_LARGE` (8 vCPU), privileged.

## The steps

| Step | Kind | What you see | Image |
|---|---|---|---|
| `layers` | bug | v1 is big; `docker history` shows which lines made it big | v1 |
| `whiteout` | bug | A file deleted in a later `RUN` is still in an earlier layer; extract it | s2 |
| `cache-miss` | bug | A one-line source change reruns the dependency download | v1 |
| `cache-order` | fix | Copy `pom.xml`, resolve dependencies, then copy the source | v2 |
| `cache-mount` | fix | `RUN --mount=type=cache` keeps `~/.m2` on the builder, out of the image | v2c |
| `context` | bug, fix | `COPY . .` sends `.git`, `target/` and `.env`; a `.dockerignore` shrinks the context | v1, v3 |
| `secret-arg` | bug | A build-arg token shows in `docker history` | s1 |
| `secret-mount` | fix | `RUN --mount=type=secret` leaves no trace in history or `docker save` | s3 |
| `stages` | fix | Two stages: the image ships only the JRE and the jar | v4 |
| `distroless` | fix | Distroless runtime: fewer packages, no shell; debug from a second container | v5 |
| `scan` | how | Trivy findings for v3, v4 and v5, OS packages vs Java libraries | v3–v5 |
| `root` | bug | v1 and v4 run as uid 0 | v1, v4 |
| `nonroot` | fix | Distroless `:nonroot` runs as 65532; `runAsNonRoot` in the Pod spec | v6 |
| `exec-format` | bug | An amd64-only image on a Graviton host: `exec format error` | v6 |
| `multiarch` | fix | One tag, an image index for amd64 and arm64; QEMU vs native build time | v6 |
| `pin` | fix | Both bases pinned by digest | v7 |
| `repro` | how | Two clean builds differ; `SOURCE_DATE_EPOCH` + `rewrite-timestamp` make them identical | v7 |

`make <step>` replays `recordings/<step>.txt`. The commands are in `steps/x86/<step>.sh` (and
`steps/arm/<step>.sh` for the two steps that finish on Graviton).

## What's in the box

```
app/                     the service: pom.xml, src/, docker/Dockerfile.v1..v7, s1..s3, per-Dockerfile .dockerignore
k8s/payflow-pod.yaml     the runAsNonRoot Pod spec the nonroot step shows
steps/x86, steps/arm     each step's commands, one per line
recordings/<step>.txt    what the page shows: the transcript, long output cut with a '…' line
recordings/raw/          the untrimmed transcripts, per host and joined
tools/record.py          runs a step file in one bash session and writes the transcript
tools/prepare_workspace.sh   builds work/, the developer's working copy (.git, target/, .env, settings.xml)
tools/trivy_summary.py   counts Trivy findings per image
tools/assemble.py        joins the x86 and Arm parts of a step
infra/                   CodeBuild buildspecs, IAM policies and live.sh (make live)
tests/                   checks the recordings, the Dockerfiles and the tools
```

## How the recordings are made

A recording is a transcript: lines starting `$ ` are commands (a trailing `\` continues one), the rest is
output. The line `# host: ...` after the first command is written by `tools/record.py` and says which
host ran the step; a step that moves to the Arm host has a second one. The AWS account ID is replaced
with `<account>`. `recordings/<step>.txt` is `recordings/raw/<step>.txt` with whole lines cut;
`make test` checks that nothing else changed.

Before the steps run, `tools/prepare_workspace.sh` logs in to Amazon ECR and ECR Public and pulls the
base images, so build times leave out base-image pulls. Base images come from the ECR Public mirror of
Docker Official Images (`public.ecr.aws/docker/library/...`) and from `gcr.io/distroless`. Image sizes
are uncompressed, as `docker image inspect .Size` reports them.

## Re-record on AWS (`make live`)

Needs AWS credentials in the environment, Region us-east-1. `infra/live.sh` creates an S3 bucket, an
IAM role with an inline policy, two CodeBuild projects, their log groups and the ECR repository
`containers-lab/payflow`, all tagged `Project=containers-lab`; runs the x86 build, then the Arm build;
downloads the transcripts into `recordings/raw/`; then deletes everything and checks with the resource
tagging API that nothing tagged `Project=containers-lab` is left. Every create and delete goes to
`infra/teardown.log`. Then cut long output into `recordings/<step>.txt` and run `make test`.

The scan step runs Trivy as a pinned container (`public.ecr.aws/aquasecurity/trivy:0.76.2`) on the build
host. The lab never enables Amazon Inspector and never changes ECR scanning settings: enabling Inspector
can turn on continuous scanning for every repository in the account.

## Out of scope

Kubernetes deployment beyond the `runAsNonRoot` snippet, image signing, SBOM attestations, registry
replication.
