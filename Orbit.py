from datetime import * # Will we need this after debugging?

# Orbital Mechanics info: http://www.braeunig.us/space/orbmech.htm
# Horizons emphemeris API: https://ssd-api.jpl.nasa.gov/doc/horizons.html

class Orbit:
    # TODO: In general, double check these parameters and their units
    def __init__(self, semimajor_axis, eccentricity, inclination, argument_of_periapsis, time_to_periapsis, longitude_of_ascending_node):
        self.sma = semimajor_axis               # in km
        self.ecc = eccentricity                 # between 0 and 1 where 0 is a circle
        self.inc = inclination                  # in degrees, to parent body's equator, not invariable plane 
                                                # TODO: Confirm that's the right choice
        self.argp = argument_of_periapsis       # in degrees
        self.lan = longitude_of_ascending_node  # in degrees, usually from the vernal equinox
                                                # TODO: Confirm that's correct
        self.ttp = time_to_periapsis            # TODO: Determine correct units

        # Other important properties that can be used in part of the signature to define the orbit
        # or derived from the above properties:
            # Apopasis distance
            # Periapsis distance
            # Period
            # True Anomaly

    def __str__(self):
        return f"Orbit(sma={self.sma}, ecc={self.ecc}, inc={self.inc}, argP={self.argp}, ttp={self.ttp}, lan={self.lan})"
    
    def __repr__(self):
        return self.__str__()

    def dict(self):
        return {
            "sma": self.sma,
            "ecc": self.ecc,
            "inc": self.inc,
            "argp": self.argp,
            "lan": self.lan,
            "ttp": self.ttp
        }
        
# Debugging, making some examples here to share to other files
# Earth will next arrive at it's perihelion on January 2nd, 2027 at 02:32 UTC
# https://in-the-sky.org/news.php?id=20270103_07_100
# TODO: Get this from the Horizons API instead
earth_perihelion_date = datetime(2027, 1, 2, 2, 32, tzinfo=timezone.utc)
ttp = (earth_perihelion_date - datetime.now(timezone.utc)).total_seconds()
earth_orbit = Orbit(149600000, 0.0167086, 7.155, 288.1, ttp, 147.9)
