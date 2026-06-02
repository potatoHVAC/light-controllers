"""Fake NeoPixel: a list-backed pixel buffer that records the last write()."""


class NeoPixel:
    def __init__(self, pin, n):
        self.n        = n
        self._buf     = [(0, 0, 0)] * n
        self.written  = [(0, 0, 0)] * n   # snapshot of the last write()

    def __setitem__(self, i, color):
        self._buf[i] = tuple(color)

    def __getitem__(self, i):
        return self._buf[i]

    def __len__(self):
        return self.n

    def fill(self, color):
        self._buf = [tuple(color)] * self.n

    def write(self):
        self.written = list(self._buf)
