# Tech layers

kOS     => Performs ops in KSP and returns monitoring data
telnet  => Middleware between kOS and kRPC
kRPC    => Allows context for advanced operations and calculations
Python  => Actual non-horrible language with vast connection options
Web API => Robust control and access

# Important Equations
## Tsiolkovsky rocket equation
dv = v_e ln(m_0/m_f)

where v_e is the exhaust velocity, m_0 is the initial total mass, and m_f is the final total mass
v_e is also equal to I_sp g0 where g0 is 9.80665m/s^2 and I_sp is the seconds of g0 thrust produced per unit propellant

## vis-viva
v^2 = G M (2/r - 1/a)

v is the relative speed of the two bodies
r is the distance between the two bodies' centers of mass
a is the length of the semi-major axis (a > 0 for ellipses, a = ∞ or 1/a = 0 for parabolas, and a < 0 for hyperbolas)
G is the gravitational constant (https://en.wikipedia.org/wiki/Gravitational_constant)
M is the mass of the central body
The product of GM can also be expressed as the standard gravitational parameter using the Greek letter μ.

## SOI
r_SOI ~= a(m/M)^(2/5)
a is the semimajor axis of the smaller object's orbit around the larger body
m and M are the masses of the smaller and larger bodies respectively 
