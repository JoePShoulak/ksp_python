from telemetry import TLM
from krpc_utils import safe_value

def vessel_is_down(vessel):
  return vessel.situation in (
    vessel.situation.landed,
    vessel.situation.splashed,
  )

def has_usable_thrust(vessel):
  return TLM.read("liquid_fuel") > 0.1 and vessel.available_thrust > 0.1

def parachute_has_left_stowed_state(parachute):
  try:
    if parachute.deployed:
      return True
  except Exception:
    pass

  try:
    state = str(parachute.state).lower()
  except Exception:
    return False

  return bool(state and "stowed" not in state)

def parachutes_have_deployed(vessel):
  try:
    parachutes = list(vessel.parts.parachutes)
  except Exception:
    return False

  return any(parachute_has_left_stowed_state(parachute) for parachute in parachutes)

def stage_has_engine(vessel, stage_number):
  return any(
    engine.part.stage == stage_number
    for engine in vessel.parts.engines
  )

def engine_uses_resource(engine, resource_name):
  propellants = safe_value(lambda: list(engine.propellants), [])

  return any(
    safe_value(lambda propellant=propellant: propellant.name) == resource_name
    for propellant in propellants
  )

def engine_is_active(engine):
  return bool(safe_value(lambda: engine.active, False))

def engine_available_thrust(engine):
  return safe_value(lambda: float(engine.available_thrust), 0) or 0

def engine_decouple_stage(engine):
  return safe_value(lambda: engine.part.decouple_stage)

def engine_activation_stage(engine):
  return safe_value(lambda: engine.part.stage)

def engine_has_been_staged(engine, current_stage):
  activation_stage = engine_activation_stage(engine)

  return activation_stage is not None and activation_stage >= current_stage

def has_active_liquid_thrust(vessel, current_stage):
  return any(
    (engine_is_active(engine) or engine_has_been_staged(engine, current_stage))
    and not engine_uses_resource(engine, "SolidFuel")
    and engine_available_thrust(engine) > 0.1
    for engine in safe_value(lambda: list(vessel.parts.engines), [])
  )

def spent_solid_boosters_for_stage(vessel, stage_number):
  return [
    engine
    for engine in safe_value(lambda: list(vessel.parts.engines), [])
    if engine_uses_resource(engine, "SolidFuel")
    and engine_has_been_staged(engine, stage_number)
    and engine_available_thrust(engine) <= 0.1
    and engine_decouple_stage(engine) == stage_number
  ]

def should_stage_spent_solid_boosters(vessel, current_stage, decouple_stage):
  return (
    has_active_liquid_thrust(vessel, current_stage)
    and len(spent_solid_boosters_for_stage(vessel, decouple_stage)) > 0
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

