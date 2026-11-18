#!/usr/bin/env bash
# Builds work/: the developer's working copy every step runs in. It is app/ plus what a real checkout
# carries: a .git directory, a target/ left by a local build, a .env and a settings.xml. Both files
# hold dummy values made up for this lab; no real secret is used anywhere.
# Also logs in to ECR and ECR Public and pulls the base and tool images, so build times leave out pulls.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf work && mkdir work && cp -R app/. work/ && cd work

printf 'PAYFLOW_DB_PASSWORD=demo-not-a-real-password\n' > .env
printf '<settings><servers><server><id>payflow-nexus</id><username>ci</username><password>%s</password></server></servers></settings>\n' \
  demo-not-a-real-token > settings.xml
git init -q && git add -A
git -c user.name=payflow-dev -c user.email=dev@payflow.example commit -qm "payments-api"
if command -v mvn >/dev/null; then mvn -B -q package -DskipTests; fi

if [ -n "${ECR_REG:-}" ]; then
  aws ecr get-login-password | docker login -u AWS --password-stdin "$ECR_REG" >/dev/null
  aws ecr-public get-login-password --region us-east-1 | docker login -u AWS --password-stdin public.ecr.aws >/dev/null
fi
for base in public.ecr.aws/docker/library/maven:3.9-eclipse-temurin-21 \
            public.ecr.aws/docker/library/eclipse-temurin:21-jre \
            gcr.io/distroless/java21-debian13 gcr.io/distroless/java21-debian13:nonroot \
            public.ecr.aws/docker/library/busybox:1.37 public.ecr.aws/aquasecurity/trivy:0.76.2 \
            public.ecr.aws/vend/tonistiigi/binfmt:latest; do
  docker pull -q "$base" >/dev/null
done
echo "work/ ready: $(du -sh . | cut -f1) on $(uname -m)"
