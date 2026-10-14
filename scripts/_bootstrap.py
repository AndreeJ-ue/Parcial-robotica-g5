from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/parcial_jetcobot'),str(ROOT/'src/arm_broker')]
