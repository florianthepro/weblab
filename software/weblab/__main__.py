"""Startpunkt: python3 -m weblab"""
import sys

from web import serve

if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        sys.exit(0)
