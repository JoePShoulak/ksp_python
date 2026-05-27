import { P5Canvas } from "@p5-wrapper/react";
import { DEFAULT_CANVAS_SIZE, getFiniteNumber } from "./p5Helpers";

const FALLBACK_KERBIN_RADIUS = 600000;
const FALLBACK_MAX_WORLD_RADIUS = 47000000 * 1.05;
const ATMOSPHERE_ALTITUDE = 70000;

const ORBIT_SEGMENTS = 720;
const SHIP_ORBIT_SEGMENTS = 360;

const MUN_DOT_SIZE = 10;
const MINMUS_DOT_SIZE = 9;
const SHIP_DOT_SIZE = 8;

function sketch(p5) {
  let props = {
    telemetry: null,
    width: DEFAULT_CANVAS_SIZE,
    height: DEFAULT_CANVAS_SIZE,
  };

  function getCenterX() {
    return p5.width / 2;
  }

  function getCenterY() {
    return p5.height / 2;
  }

  function getMaxDrawRadius() {
    return Math.min(p5.width, p5.height) * 0.45;
  }

  function isFiniteNumber(value) {
    return Number.isFinite(Number(value));
  }

  function hasVector(vector) {
    return (
      vector &&
      isFiniteNumber(vector.x) &&
      isFiniteNumber(vector.y) &&
      isFiniteNumber(vector.z)
    );
  }

  function getMapVector(vector) {
    return {
      x: getFiniteNumber(vector?.x),
      y: getFiniteNumber(vector?.z),
    };
  }

  function getMapVectorMagnitude(vector) {
    const mapVector = getMapVector(vector);

    return Math.sqrt(mapVector.x * mapVector.x + mapVector.y * mapVector.y);
  }

  function getAngleFromMapVector(vector) {
    const mapVector = getMapVector(vector);

    return Math.atan2(mapVector.y, mapVector.x);
  }

  function getMaxWorldRadius(system) {
    const visualMaxWorldRadius = props.telemetry?.visualizations?.kerbin_system
      ?.max_world_radius;

    if (isFiniteNumber(visualMaxWorldRadius)) {
      return visualMaxWorldRadius;
    }

    const bodyRadii = (system?.bodies ?? [])
      .filter(body => hasVector(body?.position))
      .map(body => getMapVectorMagnitude(body.position));

    const vesselRadius = hasVector(system?.vessel?.position)
      ? getMapVectorMagnitude(system.vessel.position)
      : 0;

    return Math.max(FALLBACK_MAX_WORLD_RADIUS, vesselRadius, ...bodyRadii);
  }

  function mapWorldRadiusToDisplayRadius(worldRadius, maxWorldRadius) {
    const normalizedRadius = p5.constrain(worldRadius / maxWorldRadius, 0, 1);

    const compressedRadius = Math.pow(normalizedRadius, 0.38);

    return compressedRadius * getMaxDrawRadius();
  }

  function getPointFromRadiusAndAngle(radius, angle) {
    return {
      x: getCenterX() + Math.cos(angle) * radius,
      y: getCenterY() - Math.sin(angle) * radius,
    };
  }

  function getPointFromWorldVector(vector, maxWorldRadius) {
    const worldRadius = getMapVectorMagnitude(vector);
    const displayRadius = mapWorldRadiusToDisplayRadius(
      worldRadius,
      maxWorldRadius,
    );

    const angle = getAngleFromMapVector(vector);

    return getPointFromRadiusAndAngle(displayRadius, angle);
  }

  function getPointFromVisual(visual) {
    if (
      visual &&
      isFiniteNumber(visual.radius_ratio) &&
      isFiniteNumber(visual.angle)
    ) {
      return getPointFromRadiusAndAngle(
        getMaxDrawRadius() * visual.radius_ratio,
        visual.angle,
      );
    }

    return null;
  }

  function getBodyColor(name) {
    if (name === "Minmus") {
      return [120, 255, 180];
    }

    if (name === "Mun") {
      return [180, 180, 180];
    }

    return [200, 200, 200];
  }

  function getBodyDotSize(name) {
    if (name === "Minmus") {
      return MINMUS_DOT_SIZE;
    }

    if (name === "Mun") {
      return MUN_DOT_SIZE;
    }

    return 8;
  }

  function drawSmoothCircleOutline(radius) {
    p5.beginShape();

    for (let index = 0; index <= ORBIT_SEGMENTS; index += 1) {
      const angle = p5.map(index, 0, ORBIT_SEGMENTS, 0, p5.TWO_PI);
      const point = getPointFromRadiusAndAngle(radius, angle);

      p5.vertex(point.x, point.y);
    }

    p5.endShape();
  }

  function drawSpace() {
    p5.background(0);
  }

  function drawKerbin(system, maxWorldRadius) {
    const visualSystem = props.telemetry?.visualizations?.kerbin_system;
    const kerbin = visualSystem?.reference_body ?? system?.reference_body;
    const kerbinRadius = getFiniteNumber(
      kerbin?.radius,
      FALLBACK_KERBIN_RADIUS,
    );
    const atmosphereRadius = isFiniteNumber(
      kerbin?.visual?.atmosphere_radius_ratio,
    )
      ? kerbin.visual.atmosphere_radius_ratio * getMaxDrawRadius()
      : mapWorldRadiusToDisplayRadius(
          kerbinRadius + ATMOSPHERE_ALTITUDE,
          maxWorldRadius,
        );

    const displayKerbinRadius = isFiniteNumber(kerbin?.visual?.radius_ratio)
      ? kerbin.visual.radius_ratio * getMaxDrawRadius()
      : mapWorldRadiusToDisplayRadius(kerbinRadius, maxWorldRadius);

    const gradientSteps = 28;

    p5.noStroke();

    for (let index = gradientSteps; index >= 0; index -= 1) {
      const amount = index / gradientSteps;
      const radius = p5.lerp(displayKerbinRadius, atmosphereRadius, amount);
      const alpha = p5.map(amount, 0, 1, 78, 0);

      p5.fill(0, 90, 180, alpha);
      p5.circle(getCenterX(), getCenterY(), radius * 2);
    }

    p5.fill(0, 90, 0);
    p5.circle(getCenterX(), getCenterY(), displayKerbinRadius * 2);

    p5.noFill();
    p5.stroke(180, 210, 235, 110);
    p5.strokeWeight(1);
    drawSmoothCircleOutline(atmosphereRadius);

    p5.fill(180, 220, 255);
    p5.noStroke();
    p5.textAlign(p5.CENTER, p5.CENTER);
    p5.textSize(12);
    p5.text(kerbin?.name ?? "Kerbin", getCenterX(), getCenterY());
  }

  function drawCircularOrbitFromPosition(body, maxWorldRadius) {
    const displayRadius = isFiniteNumber(body?.visual?.radius_ratio)
      ? body.visual.radius_ratio * getMaxDrawRadius()
      : null;

    if (displayRadius === null && !hasVector(body?.position)) {
      return;
    }

    const orbitRadius = displayRadius ?? mapWorldRadiusToDisplayRadius(
      getMapVectorMagnitude(body.position),
      maxWorldRadius,
    );

    p5.noFill();
    p5.stroke(90);
    p5.strokeWeight(1);
    drawSmoothCircleOutline(orbitRadius);
  }

  function drawBody(body, maxWorldRadius) {
    if (!body?.visual && !hasVector(body?.position)) {
      return;
    }

    const color = getBodyColor(body.name);
    const dotSize = getBodyDotSize(body.name);
    const point = getPointFromVisual(body.visual) ??
      getPointFromWorldVector(body.position, maxWorldRadius);

    p5.noStroke();
    p5.fill(...color);
    p5.circle(point.x, point.y, dotSize);

    p5.fill(...color);
    p5.textAlign(p5.LEFT, p5.CENTER);
    p5.textSize(12);
    p5.text(body.name, point.x + 10, point.y);
  }

  function getOrbitShape(periapsisRadius, apoapsisRadius) {
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

  function getShipOrbitRotation(system, orbitShape) {
    const vessel = system?.vessel;

    if (!hasVector(vessel?.position)) {
      return 0;
    }

    const shipAngle = getAngleFromMapVector(vessel.position);
    const currentOrbitalRadius = getMapVectorMagnitude(vessel.position);

    const currentTrueAnomaly = getTrueAnomalyForRadius(
      currentOrbitalRadius,
      orbitShape,
    );

    return shipAngle - currentTrueAnomaly;
  }

  function drawShipOrbit(system, maxWorldRadius) {
    const visualPoints = props.telemetry?.visualizations?.kerbin_system
      ?.ship_orbit_points;

    if (visualPoints) {
      p5.stroke(180);
      p5.strokeWeight(1.5);
      p5.noFill();

      let previousPoint = null;

      for (const visualPoint of visualPoints) {
        const point = getPointFromVisual(visualPoint);

        if (!point) {
          previousPoint = null;
          continue;
        }

        if (previousPoint) {
          p5.line(previousPoint.x, previousPoint.y, point.x, point.y);
        }

        previousPoint = point;
      }

      return;
    }

    const vessel = system?.vessel;
    const kerbinRadius = getFiniteNumber(
      system?.reference_body?.radius,
      FALLBACK_KERBIN_RADIUS,
    );

    if (
      !vessel ||
      !isFiniteNumber(vessel.periapsis) ||
      !isFiniteNumber(vessel.apoapsis)
    ) {
      return;
    }

    const orbitShape = getOrbitShape(vessel.periapsis, vessel.apoapsis);
    const orbitRotation = getShipOrbitRotation(system, orbitShape);

    p5.stroke(180);
    p5.strokeWeight(1.5);
    p5.noFill();

    let previousPoint = null;

    for (let index = 0; index <= SHIP_ORBIT_SEGMENTS; index += 1) {
      const trueAnomaly = p5.map(index, 0, SHIP_ORBIT_SEGMENTS, 0, p5.TWO_PI);
      const orbitalRadius = getOrbitRadiusAtTrueAnomaly(
        trueAnomaly,
        orbitShape,
      );

      if (orbitalRadius < kerbinRadius) {
        previousPoint = null;
        continue;
      }

      const displayRadius = mapWorldRadiusToDisplayRadius(
        orbitalRadius,
        maxWorldRadius,
      );

      const displayAngle = trueAnomaly + orbitRotation;
      const point = getPointFromRadiusAndAngle(displayRadius, displayAngle);

      if (previousPoint) {
        p5.line(previousPoint.x, previousPoint.y, point.x, point.y);
      }

      previousPoint = point;
    }
  }

  function drawShip(system, maxWorldRadius) {
    const visualSystem = props.telemetry?.visualizations?.kerbin_system;
    const vessel = visualSystem?.vessel ?? system?.vessel;

    if (!vessel?.visual && !hasVector(vessel?.position)) {
      return;
    }

    const point = getPointFromVisual(vessel.visual) ??
      getPointFromWorldVector(vessel.position, maxWorldRadius);

    p5.noStroke();
    p5.fill(255);
    p5.circle(point.x, point.y, SHIP_DOT_SIZE);

    p5.fill(255);
    p5.textAlign(p5.LEFT, p5.CENTER);
    p5.textSize(12);
    p5.text(vessel.name ?? "Ship", point.x + 10, point.y);
  }

  function drawDisconnectedState() {
    p5.fill(220);
    p5.noStroke();
    p5.textAlign(p5.CENTER, p5.CENTER);
    p5.textSize(16);
    p5.text("Waiting for Kerbin system telemetry", getCenterX(), getCenterY());
  }

  p5.updateWithProps = nextProps => {
    props = {
      ...props,
      ...nextProps,
    };

    if (p5.canvas && (p5.width !== props.width || p5.height !== props.height)) {
      p5.resizeCanvas(props.width, props.height);
    }

    if (p5.canvas) {
      p5.redraw();
    }
  };

  p5.setup = () => {
    p5.createCanvas(props.width, props.height);
    p5.noLoop();
  };

  p5.draw = () => {
    const system = props.telemetry?.kerbin_system;
    const maxWorldRadius = getMaxWorldRadius(system);

    drawSpace();

    if (!system) {
      drawDisconnectedState();
      return;
    }

    const visualSystem = props.telemetry?.visualizations?.kerbin_system;
    const bodies = visualSystem?.bodies ?? system.bodies ?? [];

    for (const body of bodies) {
      drawCircularOrbitFromPosition(body, maxWorldRadius);
    }

    drawKerbin(system, maxWorldRadius);

    drawShipOrbit(system, maxWorldRadius);

    for (const body of bodies) {
      drawBody(body, maxWorldRadius);
    }

    drawShip(system, maxWorldRadius);
  };
}

function KerbinSystemMap(props) {
  return <P5Canvas sketch={sketch} {...props} />;
}

export default KerbinSystemMap;
