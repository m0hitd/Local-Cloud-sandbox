"""
Inspect and control the sandbox EC2 instances created by Terraform.

Usage (from the repo root, after terraform apply):
    python services/vm-compute/vm_manager.py list
    python services/vm-compute/vm_manager.py inspect
    python services/vm-compute/vm_manager.py stop
    python services/vm-compute/vm_manager.py start
    python services/vm-compute/vm_manager.py ssh-mock

Instances are found by the Project tag that Terraform applies to every resource.
ssh-mock prints the command you would run against a real instance. LocalStack
does not run an SSH server on mock instances, so treat that output as a reference.
"""
import argparse
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
PROJECT_TAG = "local-multicloud-sandbox"
SSH_USER = os.environ.get("SANDBOX_SSH_USER", "ec2-user")
SSH_KEY = os.environ.get("SANDBOX_SSH_KEY", "~/.ssh/sandbox-key.pem")


def ec2_client():
    return boto3.client("ec2", endpoint_url=ENDPOINT, region_name=REGION)


def find_instances(ec2, states=None):
    filters = [{"Name": "tag:Project", "Values": [PROJECT_TAG]}]
    if states:
        filters.append({"Name": "instance-state-name", "Values": states})
    reservations = ec2.describe_instances(Filters=filters)["Reservations"]
    return [inst for res in reservations for inst in res["Instances"]]


def display_name(instance):
    for tag in instance.get("Tags", []):
        if tag["Key"] == "Name":
            return tag["Value"]
    return instance["InstanceId"]


def cmd_list(ec2, _args):
    instances = find_instances(ec2)
    if not instances:
        print("No sandbox instances found. Run terraform apply first.")
        return
    for inst in instances:
        print(
            f"{inst['InstanceId']}  {display_name(inst):<16} "
            f"{inst['State']['Name']:<10} {inst['InstanceType']}"
        )


def cmd_inspect(ec2, _args):
    instances = find_instances(ec2)
    if not instances:
        print("No sandbox instances found. Run terraform apply first.")
        return
    for inst in instances:
        print(f"Name:        {display_name(inst)}")
        print(f"Instance ID: {inst['InstanceId']}")
        print(f"State:       {inst['State']['Name']}")
        print(f"Type:        {inst['InstanceType']}")
        print(f"AMI:         {inst['ImageId']}")
        print(f"Private IP:  {inst.get('PrivateIpAddress', 'n/a')}")
        print(f"Public IP:   {inst.get('PublicIpAddress', 'n/a')}")
        print()


def cmd_stop(ec2, _args):
    ids = [i["InstanceId"] for i in find_instances(ec2, ["running"])]
    if not ids:
        print("No running sandbox instances to stop.")
        return
    ec2.stop_instances(InstanceIds=ids)
    print(f"Stop requested for: {', '.join(ids)}")


def cmd_start(ec2, _args):
    ids = [i["InstanceId"] for i in find_instances(ec2, ["stopped"])]
    if not ids:
        print("No stopped sandbox instances to start.")
        return
    ec2.start_instances(InstanceIds=ids)
    print(f"Start requested for: {', '.join(ids)}")


def cmd_ssh_mock(ec2, _args):
    instances = find_instances(ec2, ["running"])
    if not instances:
        print("No running sandbox instances. Start them first.")
        return
    for inst in instances:
        ip = inst.get("PrivateIpAddress", "<private-ip>")
        print(f"# {display_name(inst)}")
        print(f"ssh -i {SSH_KEY} {SSH_USER}@{ip}")
        print()
    print("LocalStack mock instances have no SSH daemon. Use this as a reference for real VMs.")


COMMANDS = {
    "list": cmd_list,
    "inspect": cmd_inspect,
    "stop": cmd_stop,
    "start": cmd_start,
    "ssh-mock": cmd_ssh_mock,
}


def main():
    parser = argparse.ArgumentParser(description="Manage sandbox EC2 instances on LocalStack.")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args()

    try:
        COMMANDS[args.command](ec2_client(), args)
    except (ClientError, BotoCoreError) as exc:
        print(f"EC2 request failed: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
