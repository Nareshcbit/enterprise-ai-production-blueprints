# v4: two stages; the image ships only the JRE and the jar.
cat docker/Dockerfile.v4
docker build -q -f docker/Dockerfile.v4 -t pf:v4 .
for t in pf:v3 pf:v4; do echo "$t $(docker image inspect --format '{{.Size}}' $t) bytes"; done
docker history --format '{{.Size}}\t{{.CreatedBy}}' pf:v4 | head -4
