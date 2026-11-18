# v1 is 824 MB: which Dockerfile lines made it big?
cat docker/Dockerfile.v1
docker build -q -f docker/Dockerfile.v1 -t pf:v1 .
docker image inspect --format '{{.Size}}' pf:v1
docker history --format '{{.Size}}\t{{.CreatedBy}}' pf:v1
docker run --rm --entrypoint du pf:v1 -sh /root/.m2 /app/target /app/.git
