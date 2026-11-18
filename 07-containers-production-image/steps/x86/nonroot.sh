# v6: distroless :nonroot runs as 65532; the Pod spec makes the kubelet check it.
diff docker/Dockerfile.v5 docker/Dockerfile.v6
docker build -q -f docker/Dockerfile.v6 -t pf:v6 .
docker image inspect --format '{{.Config.User}}' pf:v6
docker run -d --name v6 -p 8080:8080 pf:v6
timeout 90 sh -c 'until curl -sf localhost:8080/actuator/health; do sleep 1; done'; echo
curl -s -XPOST -H 'Content-Type: application/json' -d '{"fromAccount":"A","toAccount":"B","amount":10}' localhost:8080/payments; echo
ps -o uid=,comm= -p "$(docker inspect -f '{{.State.Pid}}' v6)"
docker rm -f v6
cat ../k8s/payflow-pod.yaml
