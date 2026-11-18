# A file deleted in a later RUN is still in the image.
cat docker/Dockerfile.s2
docker build -q -f docker/Dockerfile.s2 -t pf:s2 .
docker run --rm --entrypoint ls pf:s2 -A /root/.m2
docker save pf:s2 -o /tmp/s2.tar && mkdir -p /tmp/s2 && tar -xf /tmp/s2.tar -C /tmp/s2
for blob in /tmp/s2/blobs/sha256/*; do \
  tar -tf "$blob" 2>/dev/null | grep settings.xml | sed "s|^|$(basename "$blob" | cut -c1-12)  |"; \
done
for blob in /tmp/s2/blobs/sha256/*; do tar -xOf "$blob" root/.m2/settings.xml 2>/dev/null; done
