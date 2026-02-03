import sys
sys.path.append('backend')
from nash_engine import parse_mark

m = "23.86"
val = parse_mark(m)
print(f"Mark: {m}, Parsed: {val}")

m2 = "2:05.10"
val2 = parse_mark(m2)
print(f"Mark: {m2}, Parsed: {val2}")

m3 = "20-02.50"
val3 = parse_mark(m3)
print(f"Mark: {m3}, Parsed: {val3}")

m4 = "6.83"
val4 = parse_mark(m4)
print(f"Mark: {m4}, Parsed: {val4}")
