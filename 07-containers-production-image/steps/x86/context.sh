# COPY . . sends .git, target/ and .env; a .dockerignore shrinks the context (v3).
ls -A
du -sh .git target .env settings.xml
docker builder prune -af > /dev/null
docker build --progress=plain -f docker/Dockerfile.v1 -t pf:v1 . 2>&1 | grep 'transferring context' | tail -1
docker run --rm --entrypoint ls pf:v1 -A /app
docker run --rm --entrypoint cat pf:v1 /app/.env
cat docker/Dockerfile.v3.dockerignore
docker builder prune -af > /dev/null
docker build --progress=plain -f docker/Dockerfile.v3 -t pf:v3 . 2>&1 | grep 'transferring context' | tail -1
docker run --rm --entrypoint ls pf:v3 -A /app
docker run --rm --entrypoint cat pf:v3 /app/.env
