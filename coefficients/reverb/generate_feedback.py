import argparse
from pathlib import Path

OUTPUT_DIR = Path("mem")


def calculate_feedback(D, decay_cfg, fs=48000):
    if not 0 <= decay_cfg <= 50:
        raise ValueError("decay_cfg must be between 0 and 50")

    if D <= 0 or fs <= 0:
        raise ValueError("D and fs must be positive")

    if decay_cfg == 0:
        return 0

    T60 = decay_cfg / 10.0

    g = 10 ** (-3 * D / (fs * T60))

    SCALE = 1 << 14
    G = round(g * SCALE)

    # Saturate to 14-bit unsigned range
    G = max(0, min(G, SCALE - 1))

    return G

DELAYS = [
    [1070, 1426, 1783],  # Comb 0: Small, Medium, Large
    [1336, 1781, 2227],  # Comb 1
    [1480, 1973, 2467],  # Comb 2
    [1574, 2098, 2623],  # Comb 3
]

MAX_DECAY_CFG = 50

def generate_coefficients(comb_id):
    coefficients = []

    for room_size in range(3):
        D = DELAYS[comb_id][room_size]

        for decay_cfg in range(51):
            G = calculate_feedback(D, decay_cfg)
            coefficients.append(G)

    return coefficients

def generate_mem(comb_id): 
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = OUTPUT_DIR / f"comb_{comb_id}_g.mem"

    coefficients = generate_coefficients(comb_id)

    with open(filename, "w") as f:
        for G in coefficients:
            f.write(f"{G:04X}\n")\

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comb_id", 
                        type=int, 
                        required=True, 
                        choices=range(4), 
                        help="Possible Comb ID: 0, 1 ,2 ,3" )
    args = parser.parse_args()
    comb_id = args.comb_id

    generate_mem(comb_id)

if __name__ == "__main__":
    main()



