# Now on a Graviton host: run the amd64-only image.
uname -m
docker pull -q $REPO:v6-amd64-only
docker image inspect --format '{{.Os}}/{{.Architecture}}' $REPO:v6-amd64-only
docker run --rm $REPO:v6-amd64-only
