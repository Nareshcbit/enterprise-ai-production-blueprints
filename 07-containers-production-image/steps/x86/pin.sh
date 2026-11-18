# v7: both bases pinned by digest.
diff docker/Dockerfile.v6 docker/Dockerfile.v7
docker buildx imagetools inspect public.ecr.aws/docker/library/maven:3.9-eclipse-temurin-21 --format '{{.Manifest.Digest}}'; echo
docker buildx imagetools inspect gcr.io/distroless/java21-debian13:nonroot --format '{{.Manifest.Digest}}'; echo
docker build -q -f docker/Dockerfile.v7 -t pf:v7 .
docker image inspect --format '{{.Config.User}} {{.Size}}' pf:v7
