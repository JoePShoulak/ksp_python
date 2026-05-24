import { P5Canvas } from "@p5-wrapper/react";

function sketch(p5) {
  let props = {
    telemetry: null,
    width: 600,
    height: 300,
  };

  let trailLayer;

  function createTrailLayer() {
    trailLayer = p5.createFramebuffer({
      width: props.width,
      height: props.height,
    });

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

  function getThrottleColor(throttle) {
    const clampedThrottle = p5.constrain(throttle, 0, 1);
    const white = p5.color(255, 255, 255);
    const red = p5.color(180, 0, 0);

    return p5.lerpColor(white, red, clampedThrottle);
  }

  const groundHeight = () => 50;
  const skyHeight = () => p5.height - groundHeight();

  const ymap = value => {
    return p5.map(value, 70, 100000, skyHeight(), 0, true);
  };

  const xmap = longitude => {
    return p5.map(longitude, -180, 180, 0, p5.width, true);
  };

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

  const updateTrailLayer = (x, y, throttle) => {
    trailLayer.begin();

    withTopLeftCoordinates(() => {
      p5.fill(getThrottleColor(throttle));
      p5.noStroke();
      p5.circle(x, y, 2.5);
    });

    trailLayer.end();
  };

  const drawTrailLayer = () => {
    p5.image(trailLayer, -p5.width / 2, -p5.height / 2, p5.width, p5.height);
  };

  const drawBackground = () => {
    withTopLeftCoordinates(() => {
      drawSkyGradient();

      p5.fill(0, 75, 0);
      p5.noStroke();
      p5.rect(0, skyHeight(), p5.width, groundHeight());

      p5.stroke(180);
      p5.strokeWeight(1);
      p5.line(0, ymap(70000), p5.width, ymap(70000));
    });
  };

  function drawSkyGradient() {
    const topColor = p5.color(0, 0, 0);
    const bottomColor = p5.color(0, 80, 180);

    p5.noFill();

    for (let y = 0; y < skyHeight(); y += 1) {
      const linearAmount = y / skyHeight();
      const exponentialAmount = Math.pow(linearAmount, 2.5);
      const color = p5.lerpColor(topColor, bottomColor, exponentialAmount);

      p5.stroke(color);
      p5.line(0, y, p5.width, y);
    }
  }

  const drawApoapsisLine = apoapsis => {
    withTopLeftCoordinates(() => {
      const apoapsisY = ymap(apoapsis);

      p5.stroke("white");
      p5.strokeWeight(1);
      p5.line(0, apoapsisY, p5.width, apoapsisY);
    });
  };

  const drawShip = (x, y, throttle) => {
    withTopLeftCoordinates(() => {
      p5.fill(getThrottleColor(throttle));
      p5.noStroke();
      p5.circle(x, y, 10);
    });
  };

  let connected = false;

  p5.draw = () => {
    const telemetry = props.telemetry ?? {};

    const altitude = Number(telemetry.altitude ?? 0);
    const longitude = Number(telemetry.longitude ?? 0);
    const apoapsis = Number(telemetry.apoapsis ?? 0);
    const throttle = Number(telemetry.throttle ?? -1);

    if (throttle > -1) connected = true;

    const shipX = xmap(longitude);
    const shipY = ymap(altitude);

    p5.background(15);

    drawBackground();
    if (connected) {
      drawApoapsisLine(apoapsis);
      updateTrailLayer(shipX, shipY, throttle);
      drawTrailLayer();
      drawShip(shipX, shipY, throttle);
    }
  };
}

function KspSketch(props) {
  return <P5Canvas sketch={sketch} {...props} />;
}

export default KspSketch;
