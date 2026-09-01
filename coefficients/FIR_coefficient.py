import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import firwin, freqz


CUTOFF_RATE_HZ = 8000 
SAMPLE_RATE_HZ = 48000
NUM_TAPS = 63

COEFF_WIDTH = 16
COEFF_FRAC_BITS = 15 #Q1.15

OUTPUT_FILE = Path("fir_8khz_63tap_q15.mem")

coeff_float = firwin(
    numtaps=NUM_TAPS,
    cutoff=CUTOFF_RATE_HZ, 
    fs=SAMPLE_RATE_HZ,
    window = "hamming",
    pass_zero= "lowpass", 
    scale= True)

assert len(coeff_float) == NUM_TAPS

scale = 1 << COEFF_FRAC_BITS
coeff_int = np.rint(coeff_float*scale).astype(np.int64)

for index in range(0, NUM_TAPS//2, 1):
    coeff_int[NUM_TAPS-index-1] = coeff_int[index]

center_index = NUM_TAPS//2

coeff_sum = np.rint(np.sum(coeff_int))
if not coeff_sum == scale:
    modififed = scale - coeff_sum
    coeff_int[center_index] = coeff_int[center_index] + modififed

assert scale == np.rint(np.sum(coeff_int))

min_val = -(1<<(COEFF_WIDTH-1))
max_val = (1<<(COEFF_WIDTH-1)) -1

if np.any(coeff_int < min_val):
    raise ValueError("A coefficient is below the signed 16-bit minimum")

if np.any(coeff_int > max_val):
    raise ValueError("A coefficient is above the signed 16-bit maximum")

assert np.array_equal(coeff_int, coeff_int[::-1])
assert int(np.sum(coeff_int)) == scale

coeff_quantized = coeff_int.astype(np.float64) / scale

print(f"Number of taps: {NUM_TAPS}")
print(f"Coefficient integer sum: {np.sum(coeff_int)}")
print(f"Quantized DC gain: {np.sum(coeff_quantized):.10f}")
print(f"Minimum coefficient: {np.min(coeff_int)}")
print(f"Maximum coefficient: {np.max(coeff_int)}")
print(f"Center coefficient: {coeff_int[center_index]}")
print(f"Center coefficient value: {coeff_quantized[center_index]:.10f}")

mask = (1 << COEFF_WIDTH) - 1

with OUTPUT_FILE.open("w", encoding="ascii") as file:
    for coefficient in coeff_int:
        encoded = int(coefficient) & mask
        file.write(f"{encoded:04X}\n")

print(f"Wrote coefficient file: {OUTPUT_FILE}")



