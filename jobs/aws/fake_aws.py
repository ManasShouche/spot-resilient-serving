"""A stand-in `aws` CLI for dry-running kvevac-aws.sh on a laptop or CI box.

Implements only the calls the runner makes. `run-instances` checks the launch
parameters, unpacks the gzipped user-data and runs it locally as a process group (the
"instance"); `get-console-output` returns the last 64 KB the instance wrote to its
console file; FIS `start-experiment` tells the IMDS server (`fake_aws.py imds`, started
by dry_run.sh) to post a rebalance recommendation and an interruption notice, and that
server kills the instance when the announced time arrives.

`--query` is evaluated with jmespath (the library the real CLI uses) and `--output text`
is formatted like the CLI does for the shapes the runner queries.

Environment: FAKE_AWS_STATE (state directory, required), FAKE_AWS_NO_CAPACITY (zone that
answers InsufficientInstanceCapacity), FAKE_AWS_NOTICE_S (notice length, default 20).
"""

from __future__ import annotations

import gzip
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ACCOUNT = "123456789012"
STATE = Path(os.environ.get("FAKE_AWS_STATE", "/nonexistent"))
CONSOLE_WINDOW = 64 * 1024


class AwsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"An error occurred ({code}): {message}")


def _parse(argv: list[str]) -> tuple[str, str, dict[str, list[str]]]:
    service, op, rest = argv[0], argv[1], argv[2:]
    opts: dict[str, list[str]] = {}
    key = None
    for token in rest:
        if token.startswith("--"):
            key = token[2:]
            opts.setdefault(key, [])
        elif key is not None:
            opts[key].append(token)
    return service, op, opts


def _one(opts: dict[str, list[str]], key: str) -> str:
    values = opts.get(key) or []
    if len(values) != 1:
        raise AwsError("ValidationError", f"--{key} needs exactly one value, got {values}")
    return values[0]


def _instance() -> dict:
    path = STATE / "instance.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _save_instance(data: dict) -> None:
    (STATE / "instance.json").write_text(json.dumps(data))


def instance_state() -> str:
    data = _instance()
    if not data:
        return "none"
    if data["state"] == "running":
        try:
            os.killpg(data["pgid"], 0)
        except ProcessLookupError:
            return "terminated"  # the job ended and nothing kept it alive: powered off
    return data["state"]


def terminate() -> None:
    data = _instance()
    if not data or data["state"] == "terminated":
        return
    try:
        os.killpg(data["pgid"], signal.SIGKILL)
    except ProcessLookupError:
        pass
    data["state"] = "terminated"
    _save_instance(data)


def run_instances(opts: dict[str, list[str]]) -> dict:
    market = json.loads(_one(opts, "instance-market-options"))
    assert market["MarketType"] == "spot", market
    assert market["SpotOptions"]["SpotInstanceType"] == "one-time", market
    assert _one(opts, "instance-initiated-shutdown-behavior") == "terminate"
    assert "HttpTokens=required" in _one(opts, "metadata-options")
    devices = json.loads(_one(opts, "block-device-mappings"))
    assert devices[0]["Ebs"]["DeleteOnTermination"] is True, devices
    subnet = _one(opts, "subnet-id")
    zone = {"subnet-a": "us-east-1a", "subnet-b": "us-east-1b"}[subnet]
    if zone == os.environ.get("FAKE_AWS_NO_CAPACITY"):
        raise AwsError("InsufficientInstanceCapacity",
                       f"There is no Spot capacity available in {zone}")
    if _instance() and instance_state() != "terminated":
        raise AwsError("DryRunConflict", "the fake supports one instance at a time")
    source = _one(opts, "user-data")
    assert source.startswith("fileb://"), "gzipped user-data must be passed as fileb://"
    packed = Path(source[len("fileb://"):]).read_bytes()
    assert len(packed) < 16_384, f"user-data is {len(packed)} bytes"
    script = STATE / "user-data.sh"
    script.write_bytes(gzip.decompress(packed))
    tags = " ".join(opts.get("tag-specifications", []))
    assert "Key=project,Value=kvevac-aws" in tags, tags
    proc = subprocess.Popen(["bash", str(script)], start_new_session=True,
                            stdout=open(STATE / "cloud-init.log", "ab"),
                            stderr=subprocess.STDOUT)
    iid = "i-0fake%08d" % proc.pid
    _save_instance({"id": iid, "pgid": proc.pid, "state": "running", "zone": zone})
    return {"Instances": [{"InstanceId": iid}]}


def console_output(opts: dict[str, list[str]]) -> dict:
    path = Path(os.environ["KVEVAC_CONSOLE"])
    text = path.read_bytes()[-CONSOLE_WINDOW:].decode(errors="replace") if path.exists() else ""
    return {"InstanceId": _instance().get("id"), "Output": text or None}


def wait(opts: dict[str, list[str]], target: str) -> None:
    for _ in range(600):
        if instance_state() == target:
            return
        time.sleep(1)
    raise AwsError("WaiterError", f"instance never reached {target}")


def describe_instances(opts: dict[str, list[str]]) -> dict:
    data = _instance()
    if not data:
        return {"Reservations": []}
    state = instance_state()
    for item in opts.get("filters", []):
        name, _, values = item.partition(",")
        if name == "Name=instance-state-name" and state not in values[len("Values="):].split(","):
            return {"Reservations": []}
    return {"Reservations": [{"Instances": [{"InstanceId": data["id"],
                                             "State": {"Name": state}}]}]}


def fis_create_template(opts: dict[str, list[str]]) -> dict:
    source = _one(opts, "cli-input-json")
    template = json.loads(Path(source[len("file://"):]).read_text())
    arn = f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/{_instance()['id']}"
    assert template["targets"]["kvevacSpot"]["resourceArns"] == [arn], template
    action = template["actions"]["interrupt"]
    assert action["actionId"] == "aws:ec2:send-spot-instance-interruptions", action
    assert template["roleArn"].startswith("arn:aws:iam::"), template["roleArn"]
    (STATE / "fis-template.json").write_text(json.dumps(template))
    return {"experimentTemplate": {"id": "EXTfake"}}


def handle(service: str, op: str, opts: dict[str, list[str]]) -> object:
    if service == "sts":
        return {"Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:user/dry-run"}
    if service == "iam":
        role = {"Role": {"Arn": f"arn:aws:iam::{ACCOUNT}:role/kvevac-fis"}}
        if op == "get-role":
            if not (STATE / "role").exists():
                raise AwsError("NoSuchEntity", "The role with name kvevac-fis cannot be found.")
            return role
        if op == "create-role":
            (STATE / "role").touch()
            return role
        if op == "attach-role-policy":
            return None
    if service == "ssm":
        return {"Parameter": {"Value": "ami-0fake"}}
    if service == "ec2":
        if op == "describe-images":
            return {"Images": [{"RootDeviceName": "/dev/sda1", "BlockDeviceMappings": [
                {"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 75}}]}]}
        if op == "describe-instance-type-offerings":
            return {"InstanceTypeOfferings": [{"Location": "us-east-1a"},
                                              {"Location": "us-east-1b"}]}
        if op == "describe-spot-price-history":
            return {"SpotPriceHistory": [
                {"AvailabilityZone": "us-east-1b", "SpotPrice": "0.910000"},
                {"AvailabilityZone": "us-east-1a", "SpotPrice": "0.850000"}]}
        if op == "describe-subnets":
            return {"Subnets": [{"SubnetId": "subnet-c", "AvailabilityZone": "us-east-1c"},
                                {"SubnetId": "subnet-b", "AvailabilityZone": "us-east-1b"},
                                {"SubnetId": "subnet-a", "AvailabilityZone": "us-east-1a"}]}
        if op == "run-instances":
            return run_instances(opts)
        if op == "describe-instances":
            return describe_instances(opts)
        if op == "get-console-output":
            return console_output(opts)
        if op == "terminate-instances":
            terminate()
            return {"TerminatingInstances": [{"InstanceId": _instance().get("id")}]}
    if service == "fis":
        if op == "create-experiment-template":
            return fis_create_template(opts)
        if op == "start-experiment":
            assert _one(opts, "experiment-template-id") == "EXTfake"
            (STATE / "fis-start").touch()
            return {"experiment": {"id": "EXPfake"}}
        if op == "get-experiment":
            return {"experiment": {"id": "EXPfake", "state": {"status": "completed"}}}
        if op == "delete-experiment-template":
            (STATE / "fis-template.json").unlink(missing_ok=True)
            return None
        if op == "list-experiment-templates":
            exists = (STATE / "fis-template.json").exists()
            return {"experimentTemplates": [{"id": "EXTfake", "tags": {"project": "kvevac-aws"}}]
                    if exists else []}
    raise AwsError("InvalidAction", f"fake aws does not implement {service} {op}")


def _text(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, list):
        if value and all(isinstance(v, list) for v in value):
            return "\n".join("\t".join(_text(x) for x in row) for row in value)
        return "\t".join(_text(v) for v in value)
    if isinstance(value, dict):
        return "\t".join(_text(v) for v in value.values())
    return str(value)


def imds_server() -> None:
    """Mock IMDS for the instance; turns a FIS start into a notice and a termination."""
    from kvevac.notice.imds import MockIMDS

    notice_s = float(os.environ.get("FAKE_AWS_NOTICE_S", "20"))
    with MockIMDS() as imds:
        (STATE / "imds-url").write_text(imds.base_url)
        while not (STATE / "fis-start").exists():
            time.sleep(0.5)
        imds.schedule_interruption(notice_s=notice_s, rebalance_lead_s=1.0, after_s=0.5)
        time.sleep(notice_s + 1.5)
        terminate()


def main(argv: list[str]) -> int:
    if argv[:1] == ["imds"]:
        imds_server()
        return 0
    if argv[:2] == ["configure", "get"]:
        print("us-east-1")  # the real command prints the bare value
        return 0
    service, op, opts = _parse(argv)
    with open(STATE / "calls.log", "a") as log:
        log.write(" ".join([service, op]) + "\n")
    try:
        if service == "ec2" and op == "wait":
            targets = {"instance-running": "running", "instance-terminated": "terminated"}
            wait(opts, targets[argv[2]])
            return 0
        result = handle(service, op, opts)
    except AwsError as error:
        print(error, file=sys.stderr)
        return 254
    if result is None:
        return 0
    if "query" in opts:
        import jmespath

        result = jmespath.search(_one(opts, "query"), result)
    output = (opts.get("output") or ["json"])[0]
    print(_text(result) if output == "text" else json.dumps(result, indent=4))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
