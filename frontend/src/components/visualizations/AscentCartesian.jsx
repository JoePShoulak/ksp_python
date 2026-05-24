import { P5Canvas } from "@p5-wrapper/react";
import { DEFAULT_CANVAS_SIZE, getFiniteNumber } from "./p5Helpers";

const GROUND_HEIGHT = 50;

const MIN_ALTITUDE = 70;
const MAX_ALTITUDE = 100000;

const MIN_LONGITUDE = -180;
const MAX_LONGITUDE = 180;

const ATMOSPHERE_ALTITUDE = 70000;

const TRAIL_DOT_SIZE = 2.5;
const SHIP_DOT_SIZE = 10;
const MAX_TRAIL_INTERPOLATION_STEPS = 36;

function sketch(p5) {
  let props = {
    telemetry: null,
    width: DEFAULT_CANVAS_SIZE,
    height: DEFAULT_CANVAS_SIZE,
  };

  let trailLayer;
  let hasTelemetryConnected = false;
  let previousTrailPoint = null;

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
    previousTrailPoint = null;
  }

  function withTopLeftCoordinates(drawFn) {
    p5.push();
    p5.translate(-p5.width / 2, -p5.height / 2);
    drawFn();
    p5.pop();
  }

  function getSkyHeight() {
    return p5.height - GROUND_HEIGHT;
  }

  function mapAltitudeToY(altitude) {
    return p5.map(
      altitude,
      MIN_ALTITUDE,
      MAX_ALTITUDE,
      getSkyHeight(),
      0,
      true,
    );
  }

  function mapLongitudeToX(longitude) {
    return p5.map(longitude, MIN_LONGITUDE, MAX_LONGITUDE, 0, p5.width, true);
  }

  function getThrottleColor(throttle) {
    const clampedThrottle = p5.constrain(throttle, 0, 1);
    const noThrottleColor = p5.color(255, 255, 255);
    const fullThrottleColor = p5.color(180, 0, 0);

    return p5.lerpColor(noThrottleColor, fullThrottleColor, clampedThrottle);
  }

  function getAscentPosition(telemetry) {
    const altitude = getFiniteNumber(telemetry.altitude);
    const longitude = getFiniteNumber(telemetry.longitude);

    return {
      x: mapLongitudeToX(longitude),
      y: mapAltitudeToY(altitude),
    };
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

  function updateTrailLayer(x, y, throttle, warpFactor) {
    trailLayer.begin();

    withTopLeftCoordinates(() => {
      p5.fill(getThrottleColor(throttle));
      p5.noStroke();

      const currentPoint = { x, y };
      const previousPoint = previousTrailPoint ?? currentPoint;
      const distance = p5.dist(previousPoint.x, previousPoint.y, x, y);
      const warpBoost = Math.max(1, Number(warpFactor) || 1);
      const stepCount = Math.min(
        MAX_TRAIL_INTERPOLATION_STEPS,
        Math.max(1, Math.ceil(distance / 8) * warpBoost),
      );

      for (let index = 1; index <= stepCount; index += 1) {
        const amount = index / stepCount;

        p5.circle(
          p5.lerp(previousPoint.x, x, amount),
          p5.lerp(previousPoint.y, y, amount),
          TRAIL_DOT_SIZE,
        );
      }
    });

    trailLayer.end();
    previousTrailPoint = { x, y };
  }

  function drawTrailLayer() {
    p5.image(trailLayer, -p5.width / 2, -p5.height / 2, p5.width, p5.height);
  }

  function drawBackground() {
    withTopLeftCoordinates(() => {
      drawSkyGradient();
      drawGround();
      drawAtmosphereLine();
    });
  }

  function drawSkyGradient() {
    const skyHeight = getSkyHeight();

    const topColor = p5.color(0, 0, 0);
    const bottomColor = p5.color(0, 80, 180);

    p5.noFill();

    for (let y = 0; y < skyHeight; y += 1) {
      const linearAmount = y / skyHeight;
      const exponentialAmount = Math.pow(linearAmount, 2.5);
      const color = p5.lerpColor(topColor, bottomColor, exponentialAmount);

      p5.stroke(color);
      p5.line(0, y, p5.width, y);
    }
  }

  function drawGround() {
    p5.fill(0, 75, 0);
    p5.noStroke();
    p5.rect(0, getSkyHeight(), p5.width, GROUND_HEIGHT);
  }

  function drawAtmosphereLine() {
    const atmosphereY = mapAltitudeToY(ATMOSPHERE_ALTITUDE);

    p5.stroke(180);
    p5.strokeWeight(1);
    p5.line(0, atmosphereY, p5.width, atmosphereY);
  }

  function drawApoapsisLine(apoapsis) {
    withTopLeftCoordinates(() => {
      const apoapsisY = mapAltitudeToY(apoapsis);

      p5.stroke("white");
      p5.strokeWeight(1);
      p5.line(0, apoapsisY, p5.width, apoapsisY);
    });
  }

  function drawShip(x, y, throttle) {
    withTopLeftCoordinates(() => {
      p5.fill(getThrottleColor(throttle));
      p5.noStroke();
      p5.circle(x, y, SHIP_DOT_SIZE);
    });
  }

  function drawDisconnectedState() {
    withTopLeftCoordinates(() => {
      p5.fill(220);
      p5.noStroke();
      p5.textAlign(p5.CENTER, p5.CENTER);
      p5.textSize(16);
      p5.text("Waiting for telemetry", p5.width / 2, getSkyHeight() / 2);
    });
  }

  p5.draw = () => {
    const telemetry = props.telemetry ?? {};

    const apoapsis = getFiniteNumber(telemetry.apoapsis);
    const throttle = getFiniteNumber(telemetry.throttle, -1);
    const warpFactor = getFiniteNumber(telemetry.warp?.factor_index, 1);

    if (throttle > -1) {
      hasTelemetryConnected = true;
    }

    const { x: shipX, y: shipY } = getAscentPosition(telemetry);

    p5.background(15);

    drawBackground();

    if (!hasTelemetryConnected) {
      drawDisconnectedState();
      return;
    }

    drawApoapsisLine(apoapsis);
    updateTrailLayer(shipX, shipY, throttle, warpFactor);
    drawTrailLayer();
    drawShip(shipX, shipY, throttle);
  };
}

function AscentCartesian(props) {
  return <P5Canvas sketch={sketch} {...props} />;
}

export default AscentCartesian;
