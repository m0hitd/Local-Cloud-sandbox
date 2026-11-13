variable "ec2_ami_id" {
  description = "AMI ID for mock instances. LocalStack accepts placeholder IDs, so this only needs to look like one."
  type        = string
  default     = "ami-ff0fea8310f3"
}

variable "ec2_instance_type" {
  type    = string
  default = "t3.micro"
}

variable "ec2_instance_count" {
  type    = number
  default = 2
}

# Open to 0.0.0.0/0 because this only runs on a local workstation
resource "aws_security_group" "sandbox_vm" {
  name        = "sandbox-vm-sg"
  description = "Sandbox VM access: SSH and HTTP, plus unrestricted egress"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "sandbox_vm" {
  count                  = var.ec2_instance_count
  ami                    = var.ec2_ami_id
  instance_type          = var.ec2_instance_type
  vpc_security_group_ids = [aws_security_group.sandbox_vm.id]

  tags = {
    Name = "sandbox-vm-${count.index}"
    Role = "compute-demo"
  }
}
