import sys
import os

def base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def data_path(*parts: str) -> str:
    return os.path.join(base_dir(), *parts)
