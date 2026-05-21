class Orbit:
    def __init__(self, sma, ecc, inc, argP, ttp, lan):
        self.sma = sma # semimajor axis in km
        self.ecc = ecc # eccentricity
        self.inc = inc # inclination, in desgrees, to parent body's equator, not invariable plane 
                       # TODO: Confirm that's the right choice
        self.argP = argP # argument of periapsis, in degrees
        self.ttp = ttp # time to periapsis passage (unlisted for earth on wiki at the moment)
        self.lan = lan # in degrees, usually from the vernal equinox
                       # TODO: Confirm that's correct
        # Other inmportant properties that can be used in part of the signature to define the orbit
        # or derived from the above properties:
            # Apopasis distance
            # Periapsis distance
            # Period
            # True Anomaly

    def __str__(self):
        return f"Orbit(sma={self.sma}, ecc={self.ecc}, inc={self.inc}, argP={self.argP}, ttp={self.ttp}, lan={self.lan})"
    def __repr__(self):
        return self.__str__() # TODO: Do I need a different __repr__?