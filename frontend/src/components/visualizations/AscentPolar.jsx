import { P5Canvas } from "@p5-wrapper/react";
import { DEFAULT_CANVAS_SIZE, getFiniteNumber } from "./p5Helpers";

const KERBIN_RADIUS = 600000;
const MAX_ALTITUDE = 100000;
const ATMOSPHERE_ALTITUDE = 70000;

const KERBIN_DRAW_RADIUS_RATIO = 0.58;
const MAX_ALTITUDE_DRAW_RADIUS_RATIO = 0.94;

const TRAIL_DOT_SIZE = 2.5;
const SHIP_DOT_SIZE = 10;

const ORBIT_DOT_COUNT = 220;
const ORBIT_DOT_SIZE = 2;

const CIRCLE_SEGMENTS = 720;

function sketch(p5) {
  let props = {
    telemetry: null,
    width: DEFAULT_CANVAS_SIZE,
    height: DEFAULT_CANVAS_SIZE,
  };

  let trailLayer;
  let hasTelemetryConnected = false;

  function createTrailLayer() {
    trailLayer = p5.createFramebuffer({
      width: props.width,
      height: props.height,
    });

    clearTrailLayer();
  }

  function clearTrailLayer() {
    trailLayer.begin();
    p5.clear();
    trailLayer.end();
  }

  function withTopLeftCoordinates(drawFn) {
    p5.push();
    p5.translate(-p5.width / 2, -p5.height / 2);
    drawFn();
    p5.pop();
  }

  function getCenterX() {
    return p5.width / 2;
  }

  function getCenterY() {
    return p5.height / 2;
  }

  function getMaxDrawRadius() {
    return Math.min(p5.width, p5.height) * 0.5;
  }

  function getKerbinDrawRadius() {
    return getMaxDrawRadius() * KERBIN_DRAW_RADIUS_RATIO;
  }

  function getMaxAltitudeDrawRadius() {
    return getMaxDrawRadius() * MAX_ALTITUDE_DRAW_RADIUS_RATIO;
  }

  function mapAltitudeToRadius(altitude, shouldClamp = true) {
    if (altitude < 0) {
      return p5.map(
        altitude,
        -KERBIN_RADIUS,
        0,
        0,
        getKerbinDrawRadius(),
        shouldClamp,
      );
    }

    return p5.map(
      altitude,
      0,
      MAX_ALTITUDE,
      getKerbinDrawRadius(),
      getMaxAltitudeDrawRadius(),
      shouldClamp,
    );
  }

  function mapOrbitalRadiusToDrawRadius(orbitalRadius) {
    const altitude = orbitalRadius - KERBIN_RADIUS;

    return mapAltitudeToRadius(altitude, true);
  }

  function getThrottleColor(throttle) {
    const clampedThrottle = p5.constrain(throttle, 0, 1);
    const noThrottleColor = p5.color(255, 255, 255);
    const fullThrottleColor = p5.color(180, 0, 0);

    return p5.lerpColor(noThrottleColor, fullThrottleColor, clampedThrottle);
  }

  function getAngleFromLongitude(longitude) {
    return p5.radians(longitude - 90);
  }

  function getPointFromRadiusAndAngle(radius, angle) {
    return {
      x: getCenterX() + Math.cos(angle) * radius,
      y: getCenterY() - Math.sin(angle) * radius,
    };
  }

  function getPolarPoint(altitude, longitude) {
    const radius = mapAltitudeToRadius(altitude);
    const angle = getAngleFromLongitude(longitude);
    const point = getPointFromRadiusAndAngle(radius, angle);

    return {
      ...point,
      angle,
    };
  }

  function getFallbackOrbitShape() {
    return {
      periapsisRadius: 1,
      apoapsisRadius: 1,
      semiMajorAxis: 1,
      eccentricity: 0,
      semiLatusRectum: 1,
    };
  }

  function getOrbitShape(periapsis, apoapsis) {
    const periapsisRadius = KERBIN_RADIUS + periapsis;
    const apoapsisRadius = KERBIN_RADIUS + apoapsis;

    if (apoapsisRadius <= 0) {
      return getFallbackOrbitShape();
    }

    const safePeriapsisRadius = Math.max(periapsisRadius, 1);
    const safeApoapsisRadius = Math.max(apoapsisRadius, 1);

    const semiMajorAxis = (safePeriapsisRadius + safeApoapsisRadius) / 2;
    const eccentricity = p5.constrain(
      (safeApoapsisRadius - safePeriapsisRadius) /
        (safeApoapsisRadius + safePeriapsisRadius),
      0,
      0.99,
    );

    const semiLatusRectum = semiMajorAxis * (1 - eccentricity * eccentricity);

    return {
      periapsisRadius,
      apoapsisRadius,
      semiMajorAxis,
      eccentricity,
      semiLatusRectum,
    };
  }

  function getOrbitRadiusAtTrueAnomaly(trueAnomaly, orbitShape) {
    if (orbitShape.eccentricity <= 0.0001) {
      return orbitShape.semiMajorAxis;
    }

    return (
      orbitShape.semiLatusRectum /
      (1 + orbitShape.eccentricity * Math.cos(trueAnomaly))
    );
  }

  function getTrueAnomalyForRadius(currentOrbitalRadius, orbitShape) {
    if (orbitShape.eccentricity <= 0.0001) {
      return 0;
    }

    const cosine =
      (orbitShape.semiLatusRectum / currentOrbitalRadius - 1) /
      orbitShape.eccentricity;

    return Math.acos(p5.constrain(cosine, -1, 1));
  }

  function getOrbitRotation({
    altitude,
    longitude,
    verticalSpeed,
    periapsis,
    apoapsis,
  }) {
    const shipAngle = getAngleFromLongitude(longitude);
    const currentOrbitalRadius = KERBIN_RADIUS + altitude;
    const orbitShape = getOrbitShape(periapsis, apoapsis);

    let currentTrueAnomaly = getTrueAnomalyForRadius(
      currentOrbitalRadius,
      orbitShape,
    );

    if (verticalSpeed < 0) {
      currentTrueAnomaly *= -1;
    }

    return shipAngle - currentTrueAnomaly;
  }

  p5.updateWithProps = nextProps => {
    props = {
      ...props,
      ...nextProps,
    };

    if (p5.canvas && (p5.width !== props.width || p5.height !== props.height)) {
      p5.resizeCanvas(props.width, props.height);
      createTrailLayer();
    }
  };

  p5.setup = () => {
    p5.createCanvas(props.width, props.height, p5.WEBGL);
    createTrailLayer();
  };

  function updateTrailLayer(x, y, throttle) {
    trailLayer.begin();

    withTopLeftCoordinates(() => {
      p5.fill(getThrottleColor(throttle));
      p5.noStroke();
      p5.circle(x, y, TRAIL_DOT_SIZE);
    });

    trailLayer.end();
  }

  function drawTrailLayer() {
    p5.image(trailLayer, -p5.width / 2, -p5.height / 2, p5.width, p5.height);
  }

  function drawSmoothCircleOutline(radius) {
    p5.beginShape();

    for (let index = 0; index <= CIRCLE_SEGMENTS; index += 1) {
      const angle = p5.map(index, 0, CIRCLE_SEGMENTS, 0, p5.TWO_PI);
      const point = getPointFromRadiusAndAngle(radius, angle);

      p5.vertex(point.x, point.y);
    }

    p5.endShape();
  }

  function drawBackground() {
    withTopLeftCoordinates(() => {
      drawSpace();
      drawAtmosphereGradient();
      drawKerbin();
      drawAtmosphereLine();
    });
  }

  function drawSpace() {
    p5.background(0);
  }

  function drawKerbin() {
    const kerbinRadius = getKerbinDrawRadius();

    p5.fill(0, 90, 0);
    p5.noStroke();
    p5.circle(getCenterX(), getCenterY(), kerbinRadius * 2);
  }

  function drawAtmosphereGradient() {
    const kerbinRadius = getKerbinDrawRadius();
    const atmosphereRadius = mapAltitudeToRadius(ATMOSPHERE_ALTITUDE);
    const steps = 50;

    p5.noStroke();

    for (let index = steps; index >= 0; index -= 1) {
      const amount = index / steps;
      const radius = p5.lerp(kerbinRadius, atmosphereRadius, amount);
      const alpha = p5.map(amount, 0, 1, 95, 0);

      p5.fill(0, 90, 180, alpha);
      p5.circle(getCenterX(), getCenterY(), radius * 2);
    }
  }

  function drawAtmosphereLine() {
    const atmosphereRadius = mapAltitudeToRadius(ATMOSPHERE_ALTITUDE);

    p5.noFill();
    p5.stroke(180);
    p5.strokeWeight(1);
    drawSmoothCircleOutline(atmosphereRadius);
  }

  function drawOrbitProjection({
    altitude,
    longitude,
    verticalSpeed,
    periapsis,
    apoapsis,
  }) {
    const orbitShape = getOrbitShape(periapsis, apoapsis);
    const orbitRotation = getOrbitRotation({
      altitude,
      longitude,
      verticalSpeed,
      periapsis,
      apoapsis,
    });

    p5.fill(170);
    p5.noStroke();

    for (let index = 0; index < ORBIT_DOT_COUNT; index += 1) {
      const trueAnomaly = p5.map(index, 0, ORBIT_DOT_COUNT, 0, p5.TWO_PI);
      const orbitalRadius = getOrbitRadiusAtTrueAnomaly(
        trueAnomaly,
        orbitShape,
      );

      if (orbitalRadius < KERBIN_RADIUS) {
        continue;
      }

      const displayRadius = mapOrbitalRadiusToDrawRadius(orbitalRadius);
      const displayAngle = trueAnomaly + orbitRotation;
      const point = getPointFromRadiusAndAngle(displayRadius, displayAngle);

      p5.circle(point.x, point.y, ORBIT_DOT_SIZE);
    }
  }

  function drawShip(x, y, throttle) {
    p5.fill(getThrottleColor(throttle));
    p5.noStroke();
    p5.circle(x, y, SHIP_DOT_SIZE);
  }

  function drawDisconnectedState() {
    withTopLeftCoordinates(() => {
      p5.fill(220);
      p5.noStroke();
      p5.textAlign(p5.CENTER, p5.CENTER);
      p5.textSize(16);
      p5.text("Waiting for telemetry", getCenterX(), getCenterY());
    });
  }

  p5.draw = () => {
    const telemetry = props.telemetry ?? {};

    const altitude = getFiniteNumber(telemetry.altitude);
    const longitude = getFiniteNumber(telemetry.longitude);
    const verticalSpeed = getFiniteNumber(telemetry.vertical_speed);
    const periapsis = getFiniteNumber(telemetry.periapsis);
    const apoapsis = getFiniteNumber(telemetry.apoapsis);
    const throttle = getFiniteNumber(telemetry.throttle, -1);

    if (throttle > -1) {
      hasTelemetryConnected = true;
    }

    const shipPosition = getPolarPoint(altitude, longitude);

    drawBackground();

    if (!hasTelemetryConnected) {
      drawDisconnectedState();
      return;
    }

    withTopLeftCoordinates(() => {
      drawOrbitProjection({
        altitude,
        longitude,
        verticalSpeed,
        periapsis,
        apoapsis,
      });
    });

    updateTrailLayer(shipPosition.x, shipPosition.y, throttle);
    drawTrailLayer();

    withTopLeftCoordinates(() => {
      drawShip(shipPosition.x, shipPosition.y, throttle);
    });
  };
}

function AscentPolar(props) {
  return <P5Canvas sketch={sketch} {...props} />;
}

export default AscentPolar;
