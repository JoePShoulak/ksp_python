def low_fuel(conn, fuel_type='SolidFuel', threshold=0.1):
  vessel = conn.space_center.active_vessel

  fuel_amount = conn.get_call(vessel.resources.amount, fuel_type)
  expr = conn.krpc.Expression.less_than(
    conn.krpc.Expression.call(fuel_amount),
    conn.krpc.Expression.constant_float(threshold))
  return conn.krpc.add_event(expr)

def above_altitude(conn, alt=10000):
  vessel = conn.space_center.active_vessel

  mean_altitude = conn.get_call(getattr, vessel.flight(), 'mean_altitude')
  expr = conn.krpc.Expression.greater_than(
    conn.krpc.Expression.call(mean_altitude),
    conn.krpc.Expression.constant_double(alt))
  return conn.krpc.add_event(expr)

def apoapsis_above(conn, alt=100000):
  vessel = conn.space_center.active_vessel

  apoapsis_altitude = conn.get_call(getattr, vessel.orbit, 'apoapsis_altitude')
  expr = conn.krpc.Expression.greater_than(
    conn.krpc.Expression.call(apoapsis_altitude),
    conn.krpc.Expression.constant_double(alt))
  return conn.krpc.add_event(expr)

def below_altitude(conn, alt=2000):
  vessel = conn.space_center.active_vessel
  
  srf_altitude = conn.get_call(getattr, vessel.flight(), 'surface_altitude')
  expr = conn.krpc.Expression.less_than(
    conn.krpc.Expression.call(srf_altitude),
    conn.krpc.Expression.constant_double(2000))
  return conn.krpc.add_event(expr)
