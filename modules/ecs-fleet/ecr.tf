locals {
  runner_image = var.runner_image != "" ? var.runner_image : "${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}"
  label_images = {
    for label, _ in var.extra_runner_images : label =>
    "${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}-${label}"
  }
}

resource "aws_ecr_repository" "runner" {
  name = "github-runner"
}


resource "null_resource" "build_base_image" {
  triggers = {
    dockerfile_sha = filesha1("${path.module}/../../runner/Dockerfile")
    image_tag      = var.runner_image_tag
  }

  provisioner "local-exec" {
    command     = <<EOT
aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.runner.repository_url}
docker build --platform linux/amd64 -t ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag} ${path.module}/../../runner
docker push ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}
EOT
    interpreter = ["bash", "-c"]
  }
}

resource "null_resource" "build_extra_image" {
  for_each = var.extra_runner_images

  triggers = {
    dockerfile_sha = filesha1("${each.value}/Dockerfile")
    image_tag      = var.runner_image_tag
  }

  provisioner "local-exec" {
    command     = <<EOT
aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.runner.repository_url}
docker build --platform linux/amd64 --build-arg BASE_IMAGE=${local.runner_image} -t ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}-${each.key} ${each.value}
docker push ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}-${each.key}
EOT
    interpreter = ["bash", "-c"]
  }

  depends_on = [null_resource.build_base_image]
}
