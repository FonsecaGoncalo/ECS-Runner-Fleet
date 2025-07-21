module "control_plane" {
  source = "./modules/control-plane"

}

module "ecs_fleet" {
  source = "./modules/ecs-fleet"

}