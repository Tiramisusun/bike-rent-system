# ── SSH Key Pair ──────────────────────────────────────────────────────────────

resource "aws_key_pair" "deployer" {
  key_name   = "${var.project_name}-key"
  public_key = file(var.ssh_public_key_path)
}

# ── EC2 Security Group ────────────────────────────────────────────────────────

resource "aws_security_group" "ec2" {
  name        = "${var.project_name}-ec2-sg"
  description = "Allow SSH, HTTP, HTTPS and Flask"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # restrict to your IP for production
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Flask (direct access)"
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-ec2-sg" }
}

# ── EC2 Instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.ec2_instance_type
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  key_name               = aws_key_pair.deployer.key_name

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    db_url                 = "mysql+pymysql://${var.db_username}:${var.db_password}@${aws_db_instance.mysql.address}:3306/${var.db_name}"
    jcdecaux_api_key       = var.jcdecaux_api_key
    jcdecaux_contract_name = var.jcdecaux_contract_name
    openweather_api_key    = var.openweather_api_key
    city_name              = var.city_name
  })

  # Ensure RDS is ready before EC2 tries to connect
  depends_on = [aws_db_instance.mysql]

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = { Name = "${var.project_name}-app" }
}
