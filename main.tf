module "ecs_fleet" {
  source = "./modules/ecs-fleet"
}

module "control_plane" {
  source                = "./modules/control-plane"
  ecs_cluster           = module.ecs_fleet.cluster_name
  ecs_subnet_ids        = var.subnet_ids
  security_groups       = var.security_groups
  github_pat            = var.github_pat
  github_repo           = var.github_repo
  webhook_secret        = var.webhook_secret
  runner_class_sizes    = var.runner_class_sizes
  event_bus_name        = var.event_bus_name
  runner_repository_url = module.ecs_fleet.repository_url
  runner_image_tag      = var.runner_image_tag
  execution_role_arn    = module.ecs_fleet.execution_role_arn
  task_role_arn         = module.ecs_fleet.task_role_arn
  log_group_name        = module.ecs_fleet.log_group_name
  image_build_project   = var.image_build_project
}

module "image_build_project" {
  count        = var.image_build_project == "" ? 0 : 1
  source       = "./modules/image-build-project"
  project_name = var.image_build_project
  github_repo  = var.github_repo
  github_pat   = var.github_pat
  ecr_url      = module.ecs_fleet.repository_url
}

output "webhook_url" {
  value = module.control_plane.webhook_url
}
