# Runbook: Phase 2 calibration

**Recommended route: Job 0**, one script in AWS CloudShell that does the GPU calibration
and the spot-notice timing on the same spot instance for about $1–3. Jobs A and B are
the older routes (Vast.ai with tokens, and a t3.micro-only FIS run); they still work.

| Job | Where | What it measures | Expected cost |
|---|---|---|---|
| **0. AWS one-shot** | AWS CloudShell → 1 × g6e.xlarge spot (L40S 48 GB) + AWS FIS | everything in A, plus B's notice timing on the GPU instance itself | ≈ $1–3 per run (instance self-terminates at 90 min) |
| A. GPU calibration | Vast.ai, 1 × L40S (48 GB) | prefill throughput + attention knee, decode rate, receiver slowdown under KV ingest | ≈ $0.50–2 per run (job hard-capped at 120 min) |
| B. Spot-notice timing | AWS, 1 × t3.micro spot + AWS FIS | rebalance lead time, announced vs real notice, early terminations | ≈ $0.30–0.50 per run; 3–5 runs |
| C. Phase 3 dev (later) | Vast.ai, RTX 4090 | development only | ≈ $0.30–0.60/h × ~25 h |

Set a spending limit first: an AWS Budgets alert at $10, and (for Vast) only $10–20 of
credit.

---

## Job 0: everything on one AWS spot instance, from CloudShell

No tokens, SSH keys, S3 buckets or instance IAM roles. The instance has internet access
for pip and HuggingFace but no AWS credentials; results come back over its serial
console (`get-console-output`) as numbered, SHA-256-checked chunks.

### Permissions
CloudShell runs as your console identity, which normally has what it needs. To run with
a narrower IAM user instead (for example the `kvevac` user Claude uses), attach
`jobs/aws/iam-policy.json` to it as an inline policy. It allows launching only
`g6e.xlarge`, terminating only instances tagged `project=kvevac-aws`, the FIS calls, and
creating and passing only the `kvevac-fis` role.

### Run it
1. Open AWS CloudShell in the region you want (us-east-1 has the most g6e capacity).
2. Actions → **Upload file** → `jobs/aws/kvevac-aws.sh` from this repo.
3. `bash kvevac-aws.sh`

It prints the instance's progress as it goes (install, model download, vLLM healthy,
prefill sweep, slowdown runs) and finishes with a summary. Expect 30–45 minutes.

**CloudShell ends a session after about 20–30 minutes without keyboard input**, even
while a script runs. Press a key now and then. If the session is lost anyway, the
instance keeps measuring; reopen CloudShell and run `bash kvevac-aws.sh resume`. Either
way the instance powers itself off (and is deleted) 90 minutes after boot.

### What the script does
1. Checks credentials, refuses to start if a `project=kvevac-aws` instance is already
   running, and creates the IAM role `kvevac-fis` for FIS if it does not exist (the role
   is kept: it is free and reused next time).
2. Launches one one-time spot `g6e.xlarge` from the Deep Learning Base OSS Nvidia GPU
   AMI (Ubuntu 22.04, looked up in SSM), IMDSv2 required, shutdown behaviour terminate,
   150 GB gp3 root volume deleted on termination. It tries the default VPC's zones from
   cheapest spot price up and moves on when a zone has no capacity. Your spot G quota (5
   vCPUs) covers the 4 it needs.
3. On the instance (`jobs/aws/instance_job.sh`, embedded in gzipped user-data): arms
   `shutdown -h +90`, starts the spot-notice logger, installs vLLM with uv (Python 3.12
   venv), serves `NousResearch/Meta-Llama-3.1-8B-Instruct` (ungated mirror) with prefix
   caching off and its logs off the console, then runs `kvevac.measure.prefill` (1k–120k
   tokens, 3 repeats), `kvevac.measure.interference` (host and h2d) and the prefill fit.
4. The instance sends a results tarball over the serial console and re-sends it every
   2 minutes. CloudShell polls `get-console-output --latest` every 15 s, merges the
   overlapping 64 KB windows (`kvevac/measure/console_channel.py`) and verifies every
   chunk and the whole file.
5. With results in hand, it creates a FIS experiment template that targets exactly this
   instance (from `jobs/aws_fis/fis-template.json`) and starts a 2-minute spot
   interruption. It follows the console until the instance is gone and runs
   `kvevac.measure.notice_timing` on the transcript.
6. It terminates the instance (if FIS has not already), deletes the FIS template and
   prints a summary with an estimated cost.

### Results
Everything lands in `~/kvevac-runs/<UTC stamp>/` in CloudShell and is packed into
`~/kvevac-runs/<stamp>.tar.gz`: `results/prefill.json`, `fit.json`,
`interference-host.json`, `interference-h2d.json`, `env.json` (vLLM, torch and CUDA
versions, KV bytes per token), the job and vLLM log tails, `console.txt` (the merged
console transcript) and `notice.json`. Download the tarball (Actions → Download file)
and attach it in the project thread.

### Settings
Environment variables, e.g. `MAX_MIN=60 bash kvevac-aws.sh`: `INSTANCE_TYPE`
(g6e.xlarge), `MAX_MIN` (90, the self-terminate timer), `ROOT_GB` (150), `SUBNET_ID`,
`POLL_S` (15), `SKIP_FIS=1`, `RETRY_MIN` (0; keep retrying every zone for this many
minutes when none has capacity, every `RETRY_EVERY_S`=300 s; nothing is billed
until a launch succeeds), `MARKET` (`spot`; `on-demand` runs the calibration
measurements only, since FIS cannot interrupt an on-demand instance, and costs
`ON_DEMAND_PRICE`=1.861 $/h); passed to the instance: `MODEL`, `MAX_MODEL_LEN`,
`VLLM_SPEC` (e.g. `vllm==0.11.0` to pin), `PREFILL_CONTEXTS`, `PREFILL_REPEATS`,
`INTERFERENCE_REPEATS`.

### If something goes wrong
- `bash kvevac-aws.sh cleanup` terminates every `project=kvevac-aws` instance and
  deletes leftover FIS templates. Run it if you are unsure; it is safe to repeat.
- "spot vCPU quota too low": request an increase for *All G and VT Spot Instance
  Requests* in Service Quotas.
- "no zone had spot capacity": g6e spot capacity is often exhausted region-wide (on
  7 Oct 2026 us-east-1 refused it in all four zones, with spot priced at about the
  on-demand rate). Check first with
  `aws ec2 get-spot-placement-scores --instance-types g6e.xlarge --target-capacity 1
  --region-names us-east-1 us-east-2 us-west-2` (1 = unlikely, 10 = likely). Then
  either wait with `RETRY_MIN=120`, try a region where you have G quota
  (`AWS_REGION=us-east-2`), or run the measurements on demand with `MARKET=on-demand`
  and time the FIS notice in a later spot run.
- The results tarball always includes `job.tail.log` and `vllm.tail.log`, also when
  the job failed, so the cause is visible.

### Editing the runner
`kvevac-aws.sh` is generated. Edit `jobs/aws/driver.sh` (CloudShell side),
`jobs/aws/instance_job.sh` (instance side) or the embedded modules, then run
`python jobs/aws/build.py`. A test fails if the generated file is stale.

`bash jobs/aws/dry_run.sh` runs the whole thing on a CPU box with a fake `aws` CLI
(`jobs/aws/fake_aws.py`), a mock IMDS, a fake vLLM server and a fake `nvidia-smi`. It
checks the launch parameters, the zone fallback, the 64 KB console windows, chunk
reassembly, a lost CloudShell session followed by `resume`, the FIS notice timing,
cleanup and the summary. It needs `pip install jmespath`. What it cannot check: the
real AWS API and permissions, the AMI, cloud-init, the uv/vLLM install, CUDA and the
model download.

---

## Job A: GPU calibration on Vast.ai

### One-time setup (you)
1. **HuggingFace:** accept the Llama 3.1 license on the model page
   (`meta-llama/Llama-3.1-8B-Instruct`), then create a **read** token.
2. **GitHub:** create a *fine-grained* personal access token. Repository access:
   only `ManasShouche/spot-resilient-serving`. Permissions: **Contents: Read and
   write**. Expiry: 7 days.
3. Put both tokens into the Vast instance's environment variables as `HF_TOKEN` and
   `GH_TOKEN`. Never paste them into chat, a file, or the on-start script.

### Launch
1. On Vast, filter for **1× L40S** (an RTX A6000 48 GB also works). Reliability
   ≥ 98%, disk ≥ 80 GB, download ≥ 500 Mbps, and a **low $/TB bandwidth** price
   (the model is about 16 GB).
2. Image: `vllm/vllm-openai:latest`. Launch mode: SSH or Jupyter. Either way, Vast
   runs the on-start script.
3. Paste the contents of `jobs/vast/onstart.sh` into **On-start script**.
4. Environment: `HF_TOKEN`, `GH_TOKEN`. Optional: `JOB_TIMEOUT_MIN` (default 120)
   and `MODEL`.
5. Start it. The job takes roughly 20–40 minutes: install, model download, about
   21 prefill points up to 120k tokens, and 10 slowdown configurations.

### Results and cleanup
- The job pushes branch `calibration/<gpu>-<UTC timestamp>` containing
  `prefill.json`, `fit.json`, `interference-host.json`, `interference-h2d.json`,
  `env.json` (vLLM, torch and CUDA versions, KV bytes per token), `job.log`, and the
  vLLM log tail. It pushes even on failure or timeout, so the logs say what went
  wrong.
- **Destroy the instance in the Vast console when the branch appears.** The job
  tries to destroy itself, but that depends on Vast-injected credentials that have
  not been verified, and storage bills until the instance is deleted.
- Tell Claude the branch name. Next steps are `python -m kvevac.experiments all
  --calibration <prefill.json-derived file>`, plus setting `ingress_slowdown` from
  the interference results.

### Verified before spending money
`bash jobs/vast/dry_run.sh` runs the whole job on a CPU with a fake GPU, a fake vLLM
server, and a local git remote. It checks the clone, measurement, fit, push, and the
timeout path. What the dry run *cannot* check: the real vLLM install, the model
download, CUDA, and Vast's environment variables.

---

## Job B: spot-notice timing with AWS FIS

Needs the AWS CLI with credentials for your account (run from your own machine or
CloudShell; this Claude session's AWS credentials do not currently work).

```bash
REGION=us-east-1
# 1. Build user-data (embeds jobs/aws_fis/notice_logger.py; no credentials inside)
bash jobs/aws_fis/make_user_data.sh

# 2. One-time: FIS role
aws iam create-role --role-name kvevac-fis --assume-role-policy-document file://jobs/aws_fis/fis-trust.json
aws iam attach-role-policy --role-name kvevac-fis \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSFaultInjectionSimulatorEC2Access
ROLE_ARN=$(aws iam get-role --role-name kvevac-fis --query Role.Arn --output text)
sed "s|REPLACE_WITH_FIS_ROLE_ARN|$ROLE_ARN|" jobs/aws_fis/fis-template.json > /tmp/fis.json
TEMPLATE_ID=$(aws fis create-experiment-template --cli-input-json file:///tmp/fis.json \
  --region $REGION --query experimentTemplate.id --output text)

# 3. Per run: launch a tagged t3.micro spot instance (IMDSv2 required)
IID=$(aws ec2 run-instances --region $REGION --instance-type t3.micro \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --instance-market-options 'MarketType=spot,SpotOptions={SpotInstanceType=one-time,InstanceInterruptionBehavior=terminate}' \
  --metadata-options HttpTokens=required \
  --user-data file://jobs/aws_fis/user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=project,Value=kvevac-fis}]' \
  --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --region $REGION --instance-ids $IID; sleep 90  # boot + logger

# 4. Interrupt it (2-minute notice), then grab the console log right after termination
aws fis start-experiment --region $REGION --experiment-template-id $TEMPLATE_ID
sleep 200
aws ec2 get-console-output --region $REGION --instance-id $IID --latest --output text > run1.txt
python -m kvevac.measure.notice_timing run1.txt
```

Repeat step 3 and 4 three to five times, then commit the `run*.txt` files under
`results/notice/`. If `get-console-output` comes back empty after termination, fetch
it during the 2-minute window instead (around `sleep 100`); the heartbeats still
bracket the end. **Check afterwards that no `project=kvevac-fis` instances are
running.**

Cost: a t3.micro spot instance costs a fraction of a cent per run. FIS bills about
$0.10 per action-minute, about $0.20–0.30 per run.
