class Orbit:
    # TODO: In general, double check these parameters and their units
    def __init__(self, semimajor_axis, eccentricity, inclination, argument_of_periapsis, time_to_periapsis, longitude_of_ascending_node):
        self.sma = semimajor_axis               # in km
        self.ecc = eccentricity                 # between 0 and 1 where 0 is a circle
        self.inc = inclination                  # in degrees, to parent body's equator, not invariable plane 
                                                # TODO: Confirm that's the right choice
        self.argp = argument_of_periapsis       # in degrees
        self.ttp = time_to_periapsis            # TODO: Determine correct units
        self.lan = longitude_of_ascending_node  # in degrees, usually from the vernal equinox
                                                # TODO: Confirm that's correct

        # Other important properties that can be used in part of the signature to define the orbit
        # or derived from the above properties:
            # Apopasis distance
            # Periapsis distance
            # Period
            # True Anomaly

    def __str__(self):
        return f"Orbit(sma={self.sma}, ecc={self.ecc}, inc={self.inc}, argP={self.argp}, ttp={self.ttp}, lan={self.lan})"
    def __repr__(self):
        return self.__str__() # TODO: Do I need a different __repr__?
