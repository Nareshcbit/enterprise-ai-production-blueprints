# v1: a one-line source change reruns the dependency download.
sed -i 's/"ACCEPTED"/"RECEIVED"/' src/main/java/com/payflow/PaymentsController.java
git diff --stat
time docker build --progress=plain -f docker/Dockerfile.v1 -t pf:v1-change . 2>&1 \
  | grep -E '^#[0-9]+ (\[[0-9]+/[0-9]+\]|CACHED|DONE)'
git checkout -- src
