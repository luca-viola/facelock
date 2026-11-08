// Run with: gjs -m tests/test_gaze.js
import System from 'system';

import {cameraToScreen, pupilOffset} from '../extension/gaze.js';

const WIDTH = 1920;
const HEIGHT = 1080;
const RANGE = 100;
const EYES = [{x: 240, y: 270}, {x: 1680, y: 270}, {x: 240, y: 810}, {x: 1680, y: 810}];

let failures = 0;
function check(name, passed) {
    print(`${passed ? 'ok  ' : 'FAIL'} ${name}`);
    if (!passed)
        failures++;
}

const offsets = (x, y) => EYES.map(eye =>
    pupilOffset(eye, cameraToScreen(x, y, WIDTH, HEIGHT), RANGE, RANGE, WIDTH));

check('someone on the left of the camera image makes every eye look right',
    offsets(0, 0.5).every(offset => offset.x > 0));
check('someone on the right of the camera image makes every eye look left',
    offsets(1, 0.5).every(offset => offset.x < 0));
check('someone at the top of the camera image makes every eye look up',
    offsets(0.5, 0).every(offset => offset.y < 0));
check('eyes converge on someone in the middle',
    offsets(0.5, 0.5)[0].x > 0 && offsets(0.5, 0.5)[1].x < 0);
check('pupils stay in range at every position',
    [0, 0.5, 1].flatMap(x => [0, 0.5, 1].flatMap(y => offsets(x, y)))
        .every(({x, y}) => Math.hypot(x, y) <= RANGE));

System.exit(failures ? 1 : 0);
