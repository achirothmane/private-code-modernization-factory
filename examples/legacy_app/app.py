import imp
from collections import MutableMapping


def load_plugin(name):
    return imp.load_source(name, name + ".py")


class Config(MutableMapping):
    def __init__(self):
        self.data = {}
    def __getitem__(self, key): return self.data[key]
    def __setitem__(self, key, value): self.data[key] = value
    def __delitem__(self, key): del self.data[key]
    def __iter__(self): return iter(self.data)
    def __len__(self): return len(self.data)
