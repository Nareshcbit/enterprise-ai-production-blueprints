# RUN --mount=type=secret leaves no trace in history or docker save (s3).
cat docker/Dockerfile.s3
printf demo-not-a-real-token > /tmp/repo_token
docker build -q -f docker/Dockerfile.s3 --secret id=repo_token,src=/tmp/repo_token -t pf:s3 .
docker history --no-trunc --format '{{.CreatedBy}}' pf:s3 | head -1
docker save pf:s3 | grep -c demo-not-a-real-token
