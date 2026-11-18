# A build-arg token shows in docker history (s1).
cat docker/Dockerfile.s1
docker build -q -f docker/Dockerfile.s1 --build-arg REPO_TOKEN=demo-not-a-real-token -t pf:s1 .
docker history --no-trunc --format '{{.CreatedBy}}' pf:s1 | head -2
docker save pf:s1 | grep -c demo-not-a-real-token
