# Then natively on Graviton; join the two into one tag.
docker buildx create --name bk --driver docker-container --driver-opt image=public.ecr.aws/vend/moby/buildkit:buildx-stable-1 --use
docker buildx inspect --bootstrap bk | grep -E '^(Platforms|BuildKit version):'
time docker buildx build --builder bk --no-cache --quiet --platform linux/arm64 -f docker/Dockerfile.v6 \
  -t $REPO:v6-arm64 --push .
docker buildx imagetools create -t $REPO:v6 $REPO:v6-amd64 $REPO:v6-arm64
docker buildx imagetools inspect $REPO:v6
docker pull -q $REPO:v6
docker image inspect --format '{{.Os}}/{{.Architecture}}' $REPO:v6
docker run -d --name v6 -p 8080:8080 $REPO:v6
timeout 90 sh -c 'until curl -sf localhost:8080/actuator/health; do sleep 1; done'; echo
docker rm -f v6
