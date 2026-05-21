# Orbital Mechanics info: http://www.braeunig.us/space/orbmech.htm

# Horizons emphemeris API: https://ssd-api.jpl.nasa.gov/doc/horizons.html

from datetime import *

class Orbit:
    def __init__(self, sma, ecc, inc, argP, tpp, lan):
        self.sma = sma # semimajor axis in km
        self.ecc = ecc # eccentricity
        self.inc = inc # inclination, in desgrees, to parent body's equator, not invariable plane 
                       # TODO: Confirm that's the right choice
        self.argP = argP # argument of periapsis, in degrees
        self.tpp = tpp # time to periapsis passage (unlisted for earth on wiki at the moment)
        self.lan = lan # in degrees, usually from the vernal equinox
                       # TODO: Confirm that's correct
        # Other inmportant properties that can be used in part of the signature to define the orbit
        # or derived from the above properties:
        # Apopasis distance
        # Periapsis distance
        # Period
        # True Anomaly

    def __str__(self):
        return f"Orbit(sma={self.sma}, ecc={self.ecc}, inc={self.inc}, argP={self.argP}, tpp={self.tpp}, lan={self.lan})"
    def __repr__(self):
        return self.__str__() # TODO: Do I need a different __repr__?

# Earth will next arrive at it's perihelion on January 2nd, 2027 at 02:32 UTC
# https://in-the-sky.org/news.php?id=20270103_07_100

today_date = datetime.now(timezone.utc)
earth_perihelion_date = datetime(2027, 1, 2, 2, 32, tzinfo=timezone.utc)
tpp = (earth_perihelion_date - today_date).total_seconds()
print(today_date)
print(earth_perihelion_date)
print(tpp)

earth_orbit = Orbit(149600000, 0.0167086, 7.155, 288.1, tpp, 147.9)
print(earth_orbit)