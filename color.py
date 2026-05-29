import math


def hsv_to_rgb(h, s, v):
    """Convert HSV to RGB. h, s, v all 0-255. Returns (r, g, b) 0-255."""
    if s == 0:
        return (v, v, v)
    region = h * 6 // 256
    remainder = (h * 6) % 256
    p = v * (255 - s) // 255
    q = v * (255 - (s * remainder // 255)) // 255
    t = v * (255 - (s * (255 - remainder) // 255)) // 255
    if region == 0: return (v, t, p)
    if region == 1: return (q, v, p)
    if region == 2: return (p, v, t)
    if region == 3: return (p, q, v)
    if region == 4: return (t, p, v)
    return (v, p, q)


def scale(color, factor):
    """Scale an (r, g, b) tuple by a float 0.0–1.0."""
    r, g, b = color
    return (int(r * factor), int(g * factor), int(b * factor))


def color_max(a, b):
    """Per-channel max of two (r, g, b) tuples. Used to blend overlapping pulses."""
    return (max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]))


def exp_falloff(distance):
    """Exponential brightness falloff for pulse tails. Returns 1.0 at head, decays toward 0."""
    return math.exp(-0.46 * distance)
