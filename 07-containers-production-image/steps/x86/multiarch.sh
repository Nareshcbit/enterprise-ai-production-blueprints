# One tag, two architectures. First: both images built on this x86 host (arm64 under QEMU).
docker run --privileged --rm public.ecr.aws/vend/tonistiigi/binfmt:latest --install arm64 > /dev/null 2>&1; echo "binfmt rc=$?"
docker buildx create --name bk --driver docker-container --driver-opt image=public.ecr.aws/vend/moby/buildkit:buildx-stable-1 --use
docker buildx inspect --bootstrap bk | grep -E '^(Platforms|BuildKit version):'
time docker buildx build --builder bk --no-cache --quiet --platform linux/amd64 -f docker/Dockerfile.v6 \
  -t $REPO:v6-amd64 --push .
time docker buildx build --builder bk --no-cache --quiet --platform linux/arm64 -f docker/Dockerfile.v6 \
  -t $REPO:v6-arm64-qemu --push .
