# Two clean builds of v7 differ; SOURCE_DATE_EPOCH plus rewrite-timestamp makes them identical.
for run in a b; do \
  docker buildx build --builder bk --no-cache --provenance=false --sbom=false --platform linux/amd64 \
    -f docker/Dockerfile.v7 --metadata-file /tmp/plain-$run.json \
    --output type=image,name=$REPO:repro-plain-$run,push=true . > /dev/null 2>&1; \
  jq -r '."containerimage.digest"' /tmp/plain-$run.json; \
done
diff <(docker buildx imagetools inspect --raw $REPO:repro-plain-a | jq -r '.config.digest, .layers[].digest') \
     <(docker buildx imagetools inspect --raw $REPO:repro-plain-b | jq -r '.config.digest, .layers[].digest')
export SOURCE_DATE_EPOCH=$(git log -1 --format=%ct); echo $SOURCE_DATE_EPOCH
for run in a b; do \
  docker buildx build --builder bk --no-cache --provenance=false --sbom=false --platform linux/amd64 \
    -f docker/Dockerfile.v7 --metadata-file /tmp/epoch-$run.json \
    --output type=image,name=$REPO:repro-epoch-$run,push=true,rewrite-timestamp=true . > /dev/null 2>&1; \
  jq -r '."containerimage.digest"' /tmp/epoch-$run.json; \
done
