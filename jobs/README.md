# Runbook: Phase 2 calibration (recommended-minimum route, ≈ $15–25)

Two independent jobs. Neither needs this repo's maintainer to SSH anywhere. Results
come back as git branches or console text.

| Job | Where | What it measures | Expected cost |
|---|---|---|---|
| A. GPU calibration | Vast.ai, 1 × L40S (48 GB) | prefill throughput + attention knee, decode rate, receiver slowdown under KV ingest | ≈ $0.50–2 per run (job hard-capped at 120 min) |
| B. Spot-notice timing | AWS, 1 × t3.micro spot + AWS FIS | rebalance lead time, announced vs real notice, early terminations | ≈ $0.30–0.50 per run; 3–5 runs |
| C. Phase 3 dev (later) | Vast.ai, RTX 4090 | development only | ≈ $0.30–0.60/h × ~25 h |

Set a spending limit first: put only $10–20 of credit on Vast, and an AWS Budgets
alert at $10 for the FIS work.

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
