# Scanner findings for v3, v4 and v5: Trivy, run as a pinned container.
trivy() { docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$HOME/.cache/trivy:/root/.cache/trivy" \
  public.ecr.aws/aquasecurity/trivy:0.76.2 "$@"; }
trivy --version
export TRIVY_DB_REPOSITORY=public.ecr.aws/aquasecurity/trivy-db:2 TRIVY_JAVA_DB_REPOSITORY=public.ecr.aws/aquasecurity/trivy-java-db:1
for t in v3 v4 v5; do \
  trivy image -q --scanners vuln --db-repository $TRIVY_DB_REPOSITORY --java-db-repository $TRIVY_JAVA_DB_REPOSITORY \
    --format json pf:$t > /tmp/scan-$t.json; \
done
python3 ../tools/trivy_summary.py /tmp/scan-v3.json /tmp/scan-v4.json /tmp/scan-v5.json
