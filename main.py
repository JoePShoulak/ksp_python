# Orbital Mechanics info: http://www.braeunig.us/space/orbmech.htm
# Horizons emphemeris API: https://ssd-api.jpl.nasa.gov/doc/horizons.html

from datetime import *

from Orbit import Orbit

# Earth will next arrive at it's perihelion on January 2nd, 2027 at 02:32 UTC
# https://in-the-sky.org/news.php?id=20270103_07_100
# TODO: Get this from the Horizons API instead

earth_perihelion_date = datetime(2027, 1, 2, 2, 32, tzinfo=timezone.utc)
ttp = (earth_perihelion_date - datetime.now(timezone.utc)).total_seconds()
# print(today_date)
# print(earth_perihelion_date)
# print(tpp)

earth_orbit = Orbit(149600000, 0.0167086, 7.155, 288.1, ttp, 147.9)
print(earth_orbit)
# print([earth_orbit])
