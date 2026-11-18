# v2: copy pom.xml and resolve dependencies first; the same change rebuilds in seconds.
diff docker/Dockerfile.v1 docker/Dockerfile.v2
docker build -q -f docker/Dockerfile.v2 -t pf:v2 .
sed -i 's/"ACCEPTED"/"RECEIVED"/' src/main/java/com/payflow/PaymentsController.java
time docker build --progress=plain -f docker/Dockerfile.v2 -t pf:v2-change . 2>&1 \
  | grep -E '^#[0-9]+ (\[[0-9]+/[0-9]+\]|CACHED|DONE)'
git checkout -- src
