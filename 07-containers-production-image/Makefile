# Production image lab. Each step target replays the step's recorded commands and output (offline).
# `make local STEP=<id>` runs the same commands on your own Docker; `make live` re-records on AWS CodeBuild.
PY ?= python3
STEPS = layers whiteout cache-miss cache-order cache-mount context secret-arg secret-mount stages \
        distroless scan root nonroot exec-format multiarch pin repro

.PHONY: setup $(STEPS) workspace local test lint live

setup:            ## install test and lint tools
	$(PY) -m pip install -r requirements.txt

layers:           ## the bug: v1 is 824 MB; docker history shows which lines made it big
	@cat recordings/layers.txt

whiteout:         ## the bug: a file deleted in a later RUN is still in an earlier layer
	@cat recordings/whiteout.txt

cache-miss:       ## the bug: a one-line source change reruns the dependency download (v1)
	@cat recordings/cache-miss.txt

cache-order:      ## fix: copy pom.xml and resolve dependencies first (v2)
	@cat recordings/cache-order.txt

cache-mount:      ## fix: RUN --mount=type=cache keeps ~/.m2 out of the image (v2c)
	@cat recordings/cache-mount.txt

context:          ## the bug, then the fix: COPY . . sends .git, target/, .env; .dockerignore (v3)
	@cat recordings/context.txt

secret-arg:       ## the bug: a build-arg token shows in docker history (s1)
	@cat recordings/secret-arg.txt

secret-mount:     ## fix: RUN --mount=type=secret leaves no trace in history or docker save (s3)
	@cat recordings/secret-mount.txt

stages:           ## fix: two stages ship only the JRE and the jar (v4)
	@cat recordings/stages.txt

distroless:       ## fix: distroless runtime, no shell (v5); debug from a second container
	@cat recordings/distroless.txt

scan:             ## how: Trivy findings for v3, v4 and v5
	@cat recordings/scan.txt

root:             ## the bug: v1 and v4 run as uid 0
	@cat recordings/root.txt

nonroot:          ## fix: distroless :nonroot runs as 65532 (v6); runAsNonRoot in the Pod spec
	@cat recordings/nonroot.txt

exec-format:      ## the bug: an amd64 image on a Graviton host fails with exec format error
	@cat recordings/exec-format.txt

multiarch:        ## fix: one tag, an image index for amd64 and arm64; QEMU vs native build time
	@cat recordings/multiarch.txt

pin:              ## fix: both bases pinned by digest (v7)
	@cat recordings/pin.txt

repro:            ## how: two clean builds differ; SOURCE_DATE_EPOCH + rewrite-timestamp match
	@cat recordings/repro.txt

workspace:        ## build work/, the developer working copy the steps run in (needs Docker)
	bash tools/prepare_workspace.sh

local:            ## run one step on your Docker: make local STEP=layers (writes out/local/<step>.txt)
	@test -n "$(STEP)" || (echo "usage: make local STEP=<step id>" && exit 2)
	@test -d work || bash tools/prepare_workspace.sh
	cd steps/x86 && $(PY) ../../tools/record.py --host "local $$(uname -m)" --out ../../out/local --cwd ../../work $(STEP).sh
	@cat out/local/$(STEP).txt

test:             ## recordings, Dockerfile checks and tool tests (no AWS needed)
	$(PY) -m pytest -q

lint:             ## ruff on the Python tools and tests
	ruff check . && ruff format --check .

live:             ## re-record every step on AWS CodeBuild, then tear down (costs a few dollars)
	@echo "WARNING: creates CodeBuild projects, an ECR repository, an S3 bucket and an IAM role, runs"
	@echo "two builds, then deletes everything. Press Ctrl-C within 5 seconds to cancel." && sleep 5
	bash infra/live.sh all
