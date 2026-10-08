#!/bin/bash
# Memory node for the two-node Phase 3 test (jobs/aws/two_node.sh): exports RAM (tmpfs)
# over NFS, standing in for a surviving peer's DRAM tier. The GPU node evacuates KV to it
# over the network and restores from it. No GPU, no credentials; the default security
# group only admits members of the same group. Powers itself off after MAX_MIN minutes.
MAX_MIN="${KVEVAC_MAX_MIN:-90}"
RAM_GB="${PEER_RAM_GB:-20}"
shutdown -h "+$MAX_MIN" "kvevac spending cap"
say() { echo "KVEVAC {\"event\": \"job\", \"stage\": \"peer\", \"msg\": \"$*\"}" >/dev/ttyS0 2>/dev/null; }
say "boot; exporting ${RAM_GB} GB of RAM over NFS"
export DEBIAN_FRONTEND=noninteractive
for _ in 1 2 3; do apt-get update -qq && apt-get install -y -qq nfs-kernel-server && break; sleep 10; done
mkdir -p /export
mount -t tmpfs -o "size=${RAM_GB}g" tmpfs /export
chmod 777 /export
echo "/export *(rw,async,no_root_squash,no_subtree_check,insecure,fsid=1)" >/etc/exports
# More server threads than the default 8, for 8 parallel client connections (nconnect).
sed -i 's/^RPCNFSDCOUNT=.*/RPCNFSDCOUNT=32/' /etc/default/nfs-kernel-server 2>/dev/null
systemctl restart nfs-kernel-server && exportfs -ra
say "nfs ready: $(exportfs -v | tr -s ' ' | head -1)"
while true; do
  say "mem $(free -g | awk '/Mem/{print "used " $3 "G avail " $7 "G"}'); export $(df -h /export | awk 'NR==2{print $3}')"
  sleep 60
done
