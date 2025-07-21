locals {
  runner_image = var.runner_image != "" ? var.runner_image :
    "${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}"
  label_images = {
    for label, _ in var.extra_runner_images : label =>
    "${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}-${label}"
  }
  build_images = merge({
    base = "${path.root}/runner"
  }, {
    for label, dir in var.extra_runner_images : label => "${path.root}/${dir}"
  })
}

resource "aws_ecr_repository" "runner" {
  name = "github-runner"
}

resource "null_resource" "build_runner_image" {
  for_each = local.build_images

  triggers = {
    dockerfile_sha = filesha1("${each.value}/Dockerfile")
    image_tag = var.runner_image_tag
  }

  provisioner "local-exec" {
    command = each.key == "base" ? join("\n", [
      "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.runner.repository_url}",
      "docker build --platform linux/amd64 -t ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag} ${each.value}",
      "docker push ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}"
    ]) : join("\n", [
      "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.runner.repository_url}",
      "docker build --platform linux/amd64 --build-arg BASE_IMAGE=${local.runner_image} -t ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}-${each.key} ${each.value}",
      "docker push ${aws_ecr_repository.runner.repository_url}:${var.runner_image_tag}-${each.key}"
    ])
    interpreter = ["bash", "-c"]
  }

  depends_on = each.key == "base" ? [] : [null_resource.build_runner_image["base"]]
}
