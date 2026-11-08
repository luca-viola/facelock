// Where the eyes' pupils point. Pure math, so it can be tested without a shell.

// How far in front of the screen the other person is assumed to be, in screen widths.
const DEPTH_WIDTHS = 0.5;
// Stretches positions past the screen edges, so that a face at the side of the camera
// image turns every eye that way, even the eyes already on that side of the screen.
const SPREAD = 2;

// Converts a position in the camera image (0 to 1) to screen coordinates. The camera
// faces the user, so someone on the left of its image is on the right of the screen.
// It's assumed to be at the top of the screen, so a face in the middle of its image is
// level with the top edge.
export function cameraToScreen(x, y, width, height) {
    return {
        x: width / 2 + (0.5 - x) * SPREAD * width,
        y: (y - 0.5) * SPREAD * height,
    };
}

// Returns how far a pupil moves from the center of its eye to look at a screen position
// in front of the screen. The result stays within rangeX and rangeY.
export function pupilOffset(eye, target, rangeX, rangeY, width) {
    const dx = target.x - eye.x;
    const dy = target.y - eye.y;
    const distance = Math.hypot(dx, dy, width * DEPTH_WIDTHS);
    return {x: dx / distance * rangeX, y: dy / distance * rangeY};
}
