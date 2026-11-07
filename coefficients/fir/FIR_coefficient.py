import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Use non-interactive backend

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import firwin, freqz


# FIR configuration
SAMPLE_RATE_HZ = 48000
NUM_TAPS = 63

COEFF_WIDTH = 16
COEFF_FRAC_BITS = 15  # Signed Q1.15
SCALE = 1 << COEFF_FRAC_BITS

FILTER_MODES = {
    "bright": 10000,
    "warm":    6000,
    "dark":    3500,
}

OUTPUT_DIR = Path(__file__).resolve().parent / "mem"


# Generate and quantize FIR coefficients
def generate_coefficients(cutoff_hz):

    # Generate floating-point low-pass FIR coefficients
    coeff_float = firwin(
        numtaps=NUM_TAPS,
        cutoff=cutoff_hz,
        fs=SAMPLE_RATE_HZ,
        window="hamming",
        pass_zero="lowpass",
        scale=True,
    )

    # Convert floating-point coefficients to Q1.15
    coeff_int = np.rint(
        coeff_float * SCALE
    ).astype(np.int64)

    # Enforce exact unity DC gain after quantization
    center_index = NUM_TAPS // 2
    correction = SCALE - int(np.sum(coeff_int))
    coeff_int[center_index] += correction

    # Verify signed 16-bit range
    min_val = -(1 << (COEFF_WIDTH - 1))
    max_val = (1 << (COEFF_WIDTH - 1)) - 1

    assert np.all(coeff_int >= min_val)
    assert np.all(coeff_int <= max_val)

    # Verify coefficient symmetry and unity DC gain
    assert np.array_equal(coeff_int, coeff_int[::-1])
    assert int(np.sum(coeff_int)) == SCALE

    return coeff_int


# Write coefficients to hexadecimal .mem files
def write_mem_file(coeff_int, output_file):

    mask = (1 << COEFF_WIDTH) - 1
    hex_digits = (COEFF_WIDTH + 3) // 4

    with output_file.open("w", encoding="ascii") as file:
        for coefficient in coeff_int:
            encoded = int(coefficient) & mask
            file.write(f"{encoded:0{hex_digits}X}\n")


# Generate all three filter modes
def main():

    assert NUM_TAPS % 2 == 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(9, 5))

    for mode, cutoff_hz in FILTER_MODES.items():

        coeff_int = generate_coefficients(cutoff_hz)

        output_file = OUTPUT_DIR / f"fir_{mode}_q15.mem"
        write_mem_file(coeff_int, output_file)

        # Convert back to floating-point for analysis
        coeff_quantized = coeff_int / SCALE

        # Calculate the frequency response
        freq, response = freqz(
            coeff_quantized,
            worN=4096,
            fs=SAMPLE_RATE_HZ,
        )

        magnitude_db = 20 * np.log10(
            np.maximum(np.abs(response), 1e-8)
        )

        plt.plot(
            freq,
            magnitude_db,
            label=f"{mode.capitalize()} ({cutoff_hz} Hz)",
        )

        print(f"\nMode: {mode}")
        print(f"Cutoff: {cutoff_hz} Hz")
        print(f"Taps: {NUM_TAPS}")
        print(f"Coefficient sum: {np.sum(coeff_int)}")
        print(f"DC gain: {np.sum(coeff_quantized):.8f}")
        print(f"Center coefficient: {coeff_int[NUM_TAPS // 2]}")
        print(f"Output: {output_file}")

    # Save comparison plot
    plt.title("FIR Low-Pass Frequency Response")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Magnitude (dB)")
    plt.xlim(0, SAMPLE_RATE_HZ / 2)
    plt.ylim(-100, 5)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(
        OUTPUT_DIR.parent / "fir_frequency_response.png",
        dpi=160,
    )

    plt.close()


if __name__ == "__main__":
    main()
