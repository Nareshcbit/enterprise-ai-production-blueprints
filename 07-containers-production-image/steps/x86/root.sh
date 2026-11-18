# v1 and v4 run as uid 0.
for t in pf:v1 pf:v4; do echo "$t Config.User='$(docker image inspect --format '{{.Config.User}}' $t)'"; done
docker run --rm --entrypoint id pf:v1
docker run --rm --entrypoint id pf:v4
