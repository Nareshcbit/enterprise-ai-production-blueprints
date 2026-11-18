# v5: distroless runtime, fewer packages, no shell; debug it from a second container.
diff docker/Dockerfile.v4 docker/Dockerfile.v5
docker build -q -f docker/Dockerfile.v5 -t pf:v5 .
for t in pf:v4 pf:v5; do echo "$t $(docker image inspect --format '{{.Size}}' $t) bytes"; done
docker run --rm --entrypoint sh pf:v4 -c 'dpkg-query -W | wc -l'
docker create --name x5 pf:v5 > /dev/null
docker export x5 | tar -t | grep '^var/lib/dpkg/status.d/' | grep -vc -e md5sums -e '/$'
docker rm x5 > /dev/null
docker run --rm --entrypoint sh pf:v5 -c 'echo I have a shell'
docker run -d --name v5 pf:v5 > /dev/null
docker run --rm --pid=container:v5 public.ecr.aws/docker/library/busybox:1.37 \
  sh -c 'ps -o pid,user,args; ls -l /proc/1/root/app'
docker rm -f v5 > /dev/null
