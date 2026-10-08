#!/usr/bin/env bash
# Two-node Phase 3 test: evacuate KV over the network to a peer's DRAM, restore from it.
#
#   AWS_REGION=us-east-2 bash jobs/aws/two_node.sh
#
# 1. Launches a memory node (r7i.xlarge, 32 GB, ~$0.27/h) that exports 20 GB of RAM over
#    NFS (jobs/aws/peer_node.sh). It is tagged project=kvevac-peer, self-terminates
#    after 90 min, and this script terminates it on exit whatever happens.
# 2. Runs kvevac-aws.sh with KVEVAC_JOB=phase3 PHASE3_TIER=peer on an on-demand L40S in
#    the same zone (falling back to any zone), so the plugin's deadline flush and the
#    restore both go over the network to the peer's RAM.
# Expected cost: about $1.2 (L40S ~35 min) + $0.2 (memory node). Cap: ~$2.3.
set -euo pipefail
cd "$(dirname "$0")/../.."
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-2}" AWS_PAGER=""
AZ="${AZ:-${AWS_DEFAULT_REGION}c}"
PEER_TYPE="${PEER_TYPE:-r7i.xlarge}"
say() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

subnet="$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true \
  "Name=availability-zone,Values=$AZ" --query 'Subnets[0].SubnetId' --output text)"
ami="$(aws ssm get-parameter --name \
  /aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id \
  --query Parameter.Value --output text)"
peer="$(aws ec2 run-instances --instance-type "$PEER_TYPE" --image-id "$ami" \
  --subnet-id "$subnet" --count 1 --instance-initiated-shutdown-behavior terminate \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --user-data "file://jobs/aws/peer_node.sh" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=project,Value=kvevac-peer},{Key=Name,Value=kvevac-peer}]" \
  --query 'Instances[0].InstanceId' --output text)"
cleanup() {
  say "terminating memory node $peer"
  aws ec2 terminate-instances --instance-ids "$peer" >/dev/null || true
}
trap cleanup EXIT
peer_ip="$(aws ec2 describe-instances --instance-ids "$peer" \
  --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
say "memory node $peer ($PEER_TYPE) in $AZ at $peer_ip"
aws ec2 wait instance-running --instance-ids "$peer"

export KVEVAC_JOB=phase3 PHASE3_TIER=peer PEER_IP="$peer_ip" MARKET=on-demand \
  MAX_MIN="${MAX_MIN:-60}" KVEVAC_RUNS="${KVEVAC_RUNS:-$HOME/kvevac-runs/two-node}"
mkdir -p "$KVEVAC_RUNS"
SUBNET_ID="$subnet" RETRY_MIN="${SAME_AZ_RETRY_MIN:-20}" bash jobs/aws/kvevac-aws.sh || true
if ! grep -q '^IID=' "$KVEVAC_RUNS/latest/state.env" 2>/dev/null; then
  say "no L40S in $AZ; trying any zone (the tier is then cross-zone)"
  RETRY_MIN="${ANY_AZ_RETRY_MIN:-20}" bash jobs/aws/kvevac-aws.sh || true
fi
