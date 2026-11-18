#!/usr/bin/env bash
# Re-records every step on AWS CodeBuild: an x86 host, then a Graviton (Arm) host.
#   bash infra/live.sh up     create the bucket, role, log groups, ECR repository and two projects
#   bash infra/live.sh run    upload the lab, run x86 then Arm, download transcripts to recordings/raw/
#   bash infra/live.sh down   delete everything 'up' created and check nothing tagged Project=containers-lab is left
#   bash infra/live.sh all    up, run, down (down runs even if run fails)
# Costs a few dollars of CodeBuild time. Never enables Amazon Inspector or changes ECR scanning settings.
# Every create and delete is appended to $TEARDOWN_LOG (default: infra/teardown.log).
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
TAG_KEY=Project TAG_VALUE=containers-lab
STATE=infra/.live-state
LOG=${TEARDOWN_LOG:-infra/teardown.log}
ROLE=containers-lab-codebuild
REPO_NAME=containers-lab/payflow
PROJECTS=(containers-lab-x86 containers-lab-arm)

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
account() { aws sts get-caller-identity --query Account --output text; }

up() {
  local bucket acct
  acct=$(account)
  bucket="containers-lab-$(openssl rand -hex 4)"
  echo "BUCKET=$bucket" > "$STATE"
  aws s3api create-bucket --bucket "$bucket" > /dev/null
  aws s3api put-bucket-tagging --bucket "$bucket" --tagging "TagSet=[{Key=$TAG_KEY,Value=$TAG_VALUE}]"
  log "CREATE s3-bucket $bucket"
  aws iam create-role --role-name "$ROLE" --tags "Key=$TAG_KEY,Value=$TAG_VALUE" \
    --assume-role-policy-document file://infra/trust-policy.json > /dev/null
  log "CREATE iam-role $ROLE"
  sed -e "s/ACCOUNT/$acct/g" -e "s/BUCKET/$bucket/g" infra/role-policy.json > infra/.role-policy.json
  aws iam put-role-policy --role-name "$ROLE" --policy-name "$ROLE" --policy-document file://infra/.role-policy.json
  rm infra/.role-policy.json
  log "CREATE iam-inline-policy $ROLE/$ROLE"
  aws ecr create-repository --repository-name "$REPO_NAME" --image-scanning-configuration scanOnPush=false \
    --tags "Key=$TAG_KEY,Value=$TAG_VALUE" > /dev/null
  log "CREATE ecr-repository $REPO_NAME"
  for arch in x86 arm; do
    aws logs create-log-group --log-group-name "/containers-lab/codebuild-$arch" --tags "$TAG_KEY=$TAG_VALUE"
    log "CREATE log-group /containers-lab/codebuild-$arch"
  done
  sleep 15 # the new role must be assumable before CodeBuild accepts it
  create_project containers-lab-x86 LINUX_CONTAINER aws/codebuild/standard:7.0 BUILD_GENERAL1_MEDIUM x86 "$bucket" "$acct"
  create_project containers-lab-arm ARM_CONTAINER aws/codebuild/amazonlinux-aarch64-standard:3.0 BUILD_GENERAL1_LARGE arm "$bucket" "$acct"
}

create_project() { # name type image compute arch bucket account
  aws codebuild create-project --name "$1" \
    --source "type=S3,location=$6/source.zip,buildspec=infra/buildspec-$5.yml" \
    --artifacts "type=S3,location=$6,path=artifacts,name=$5.zip,packaging=ZIP" \
    --environment "type=$2,image=$3,computeType=$4,privilegedMode=true" \
    --service-role "arn:aws:iam::$7:role/$ROLE" --timeout-in-minutes 60 \
    --logs-config "cloudWatchLogs={status=ENABLED,groupName=/containers-lab/codebuild-$5}" \
    --tags "key=$TAG_KEY,value=$TAG_VALUE" > /dev/null
  log "CREATE codebuild-project $1"
}

run_build() { # project: start, wait, fail unless SUCCEEDED
  local id status
  id=$(aws codebuild start-build --project-name "$1" --query build.id --output text)
  echo "started $1"
  while :; do
    status=$(aws codebuild batch-get-builds --ids "$id" --query 'builds[0].buildStatus' --output text)
    [ "$status" != IN_PROGRESS ] && break
    sleep 20
  done
  echo "$1 $status"
  [ "$status" = SUCCEEDED ]
}

run() {
  # shellcheck disable=SC1090
  source "$STATE"
  rm -f infra/source.zip
  zip -qr infra/source.zip app steps tools infra/buildspec-x86.yml infra/buildspec-arm.yml k8s
  aws s3 cp --quiet infra/source.zip "s3://$BUCKET/source.zip" && rm infra/source.zip
  run_build containers-lab-x86
  run_build containers-lab-arm
  for arch in x86 arm; do
    aws s3 cp --quiet "s3://$BUCKET/artifacts/$arch.zip" "infra/$arch.zip"
    rm -rf "recordings/raw/$arch" && unzip -qo "infra/$arch.zip" -d recordings/raw && rm "infra/$arch.zip"
  done
  python3 tools/assemble.py recordings/raw
}

down() {
  local bucket=""
  [ -f "$STATE" ] && bucket=$(sed -n 's/^BUCKET=//p' "$STATE")
  for p in "${PROJECTS[@]}"; do
    aws codebuild delete-project --name "$p" 2> /dev/null && log "DELETE codebuild-project $p"
  done
  for arch in x86 arm; do
    aws logs delete-log-group --log-group-name "/containers-lab/codebuild-$arch" 2> /dev/null \
      && log "DELETE log-group /containers-lab/codebuild-$arch"
  done
  aws ecr delete-repository --repository-name "$REPO_NAME" --force > /dev/null 2>&1 && log "DELETE ecr-repository $REPO_NAME"
  aws iam delete-role-policy --role-name "$ROLE" --policy-name "$ROLE" 2> /dev/null \
    && log "DELETE iam-inline-policy $ROLE/$ROLE"
  aws iam delete-role --role-name "$ROLE" 2> /dev/null && log "DELETE iam-role $ROLE"
  if [ -n "$bucket" ]; then
    aws s3 rm --quiet --recursive "s3://$bucket" && aws s3api delete-bucket --bucket "$bucket" && log "DELETE s3-bucket $bucket"
  fi
  rm -f "$STATE"
  verify
}

verify() {
  local left
  sleep 5
  left=$(aws resourcegroupstaggingapi get-resources --tag-filters "Key=$TAG_KEY,Values=$TAG_VALUE" \
    --query 'length(ResourceTagMappingList)' --output text)
  log "VERIFY tagged $TAG_KEY=$TAG_VALUE resources left: $left"
  if aws iam get-role --role-name "$ROLE" > /dev/null 2>&1; then log "VERIFY iam-role $ROLE still exists"; else log "VERIFY iam-role $ROLE gone"; fi
  log "VERIFY ecr registry scanning: $(aws ecr get-registry-scanning-configuration \
    --query 'scanningConfiguration.[scanType,length(rules)]' --output text)"
  log "VERIFY inspector2 ECR status: $(aws inspector2 batch-get-account-status \
    --query 'accounts[0].resourceState.ecr.status' --output text 2>&1)"
}

case "${1:-}" in
  up) up ;;
  run) run ;;
  down) down ;;
  verify) verify ;;
  all) up && { run || echo "run failed; tearing down"; } ; down ;;
  *) echo "usage: $0 up|run|down|verify|all" && exit 2 ;;
esac
