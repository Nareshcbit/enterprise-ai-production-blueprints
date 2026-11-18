# v2c: RUN --mount=type=cache keeps ~/.m2 on the builder, out of the image.
diff docker/Dockerfile.v2 docker/Dockerfile.v2c
docker build -q -f docker/Dockerfile.v2c -t pf:v2c .
for t in pf:v2 pf:v2c; do echo "$t $(docker image inspect --format '{{.Size}}' $t) bytes"; done
docker run --rm --entrypoint du pf:v2 -sh /root/.m2
docker run --rm --entrypoint ls pf:v2c -A /root/.m2
docker buildx du --verbose --filter type=exec.cachemount | grep -E '^(Description|Size):'
