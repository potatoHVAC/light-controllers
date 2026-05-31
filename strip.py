from machine import Pin
from neopixel import NeoPixel
from color import scale, color_max, exp_falloff

BLACK = (0, 0, 0)
PULSE_LEN = 10


class Strip:
    def __init__(self, name, pin, num_leds):
        """Single NeoPixel strip. name is used by fixtures and scenes for identification."""
        self.name = name
        self.num_leds = num_leds
        self._np = NeoPixel(Pin(pin), num_leds)
        self._dim = 1.0
        # Unscaled pattern buffer. show() reads from here so dim scaling never
        # compounds between ticks when a pattern has a timing gate.
        self._buf = [(0, 0, 0)] * num_leds

    @property
    def dim(self):
        return self._dim

    @dim.setter
    def dim(self, factor):
        self._dim = max(0.0, min(1.0, factor))

    def __setitem__(self, index, color):
        self._buf[index] = color
        self._np[index] = color

    def __getitem__(self, index):
        return self._buf[index]

    def fill(self, color):
        """Set every LED to the same color without pushing to hardware."""
        for i in range(self.num_leds):
            self._buf[i] = color
            self._np[i] = color

    def show(self):
        """Push the current pixel buffer to hardware, applying dim scaling.
        Reads from the unscaled _buf so scaling never compounds across ticks."""
        if self._dim < 1.0:
            for i in range(self.num_leds):
                r, g, b = self._buf[i]
                self._np[i] = (int(r * self._dim), int(g * self._dim), int(b * self._dim))
        self._np.write()

    def clear(self):
        """Turn off all LEDs and push immediately."""
        self.fill(BLACK)
        self.show()

    def draw_pulse(self, head_pos, direction, color):
        """Draw a comet-tail pulse at head_pos moving in direction (+1 or -1).
        Brightness falls off exponentially behind the head. Does not call show()."""
        for i in range(PULSE_LEN):
            idx = head_pos - (direction * i)
            if 0 <= idx < self.num_leds:
                new_color = color_max(self._buf[idx], scale(color, exp_falloff(i)))
                self._buf[idx] = new_color
                self._np[idx] = new_color
