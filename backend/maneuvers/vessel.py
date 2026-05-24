from telemetry import TLM

def vessel_is_down(vessel):
  return vessel.situation in (
    vessel.situation.landed,
    vessel.situation.splashed,
  )

def has_usable_thrust(vessel):
  return TLM.read("liquid_fuel") > 0.1 and vessel.available_thrust > 0.1

def stage_has_engine(vessel, stage_number):
  return any(
    engine.part.stage == stage_number
    for engine in vessel.parts.engines
  )

def estimate_full_throttle_burn_time(vessel):
  propellant_requirements = {}

  active_engines = [
    engine
    for engine in vessel.parts.engines
    if engine.active and engine.available_thrust > 0
  ]

  for engine in active_engines:
    for propellant in engine.propellants:
      if propellant.current_requirement <= 0:
        continue

      if propellant.name not in propellant_requirements:
        propellant_requirements[propellant.name] = {
          "available": propellant.total_resource_available,
          "required": 0,
        }

      propellant_requirements[propellant.name]["required"] += propellant.current_requirement

  burn_times = [
    data["available"] / data["required"]
    for data in propellant_requirements.values()
    if data["required"] > 0
  ]

  if not burn_times:
    return 0

  return min(burn_times)

