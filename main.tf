module "ecs_fleet" {
  source              = "./modules/ecs-fleet"
  aws_region          = var.aws_region
  github_repo         = var.github_repo
  runner_image_tag    = var.runner_image_tag
  extra_runner_images = var.extra_runner_images
}

module "control_plane" {
  source                     = "./modules/control-plane"
  ecs_cluster                = module.ecs_fleet.cluster_name
  ecs_subnet_ids             = var.subnet_ids
  security_groups            = var.security_groups
  github_pat                 = var.github_pat
  github_repo                = var.github_repo
  webhook_secret             = var.webhook_secret
  runner_class_sizes         = var.runner_class_sizes
  task_definition_arn        = module.ecs_fleet.task_definition_arn
  label_task_definition_arns = module.ecs_fleet.extra_task_definition_arns
}

output "webhook_url" {
  value = module.control_plane.webhook_url
}
