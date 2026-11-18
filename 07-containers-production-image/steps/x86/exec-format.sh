# Build on x86, push an amd64-only image.
uname -m
docker tag pf:v6 $REPO:v6-amd64-only
docker push -q $REPO:v6-amd64-only
