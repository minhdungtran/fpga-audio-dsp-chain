import random
from pathlib import Path
from functools import lru_cache

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

WIDTH = 24
BIT_SLOT = 32
NUM_TAPS = 63

FRAC_BITS = 14
FIR_FRAC_BITS = 15
COEFF_WIDTH = 16

SAMPLE_RATE_HZ = 48000
MAX_DELAY_MS = 500

DSP_CLK = 20        # 50 MHz
I2S_CLK = 325.52    # ~3.072 MHz

MAX_24 = (1 << 23) - 1
MIN_24 = -(1 << 23)
UNITY = 1 << FRAC_BITS

LATENCY = 2
BYPASS_LATENCY = 1
MAX_INIT_CYCLES = 80000

MEM_ROOT = Path(__file__).resolve().parent / "coefficients"

FIR_FILES = {
    0: "fir_bright_q15.mem",
    1: "fir_warm_q15.mem",
    2: "fir_dark_q15.mem",
    3: "fir_warm_q15.mem",
}

# [comb_id][room_size]
DELAYS = [
    [1070, 1426, 1783],
    [1336, 1781, 2227],
    [1480, 1973, 2467],
    [1574, 2098, 2623],
]

ALL_PASS_DELAYS = [240, 82]


def int_to_twos(value, width=WIDTH):
    return value & ((1 << width) - 1)


def twos_to_int(value, width=WIDTH):
    value &= (1 << width) - 1

    if value & (1 << (width - 1)):
        value -= 1 << width

    return value


def sat_clip(value):
    return max(MIN_24, min(MAX_24, int(value)))


def convert_u014(value):
    return max(0, min(UNITY - 1, round(value * UNITY)))


def fir_processing(accumulator):
    offset = 1 << (FIR_FRAC_BITS - 1)

    if accumulator >= 0:
        rounded = (accumulator + offset) >> FIR_FRAC_BITS
    else:
        rounded = (accumulator + offset - 1) >> FIR_FRAC_BITS

    return sat_clip(rounded)


@lru_cache(maxsize=None)
def load_fir_coefficients(mode):
    filename = FIR_FILES[mode]
    path = MEM_ROOT / "fir" / "mem" / filename

    with path.open("r") as file:
        coefficients = [
            twos_to_int(int(line.strip(), 16), COEFF_WIDTH)
            for line in file
            if line.strip()
        ]

    assert len(coefficients) == NUM_TAPS
    return coefficients


@lru_cache(maxsize=None)
def load_comb_coefficients(comb_id):
    path = (
        MEM_ROOT / "reverb" / "mem"
        / f"comb_{comb_id}_g.mem"
    )

    with path.open("r") as file:
        coefficients = [
            int(line.strip(), 16)
            for line in file
            if line.strip()
        ]

    assert len(coefficients) >= 3 * 51
    return coefficients


def feedback_coefficient(comb_id, room_size, decay_cfg):
    # Matches the 3 room modes x 51 decay settings ROM.
    address = room_size * 51 + decay_cfg
    return load_comb_coefficients(comb_id)[address]


def amp_model(frames, gain, bypass):
    if bypass:
        return list(frames)

    return [
        (
            sat_clip((ld * gain) >> FRAC_BITS),
            sat_clip((rd * gain) >> FRAC_BITS),
        )
        for ld, rd in frames
    ]


def fir_model(frames, coefficients, bypass=False):
    if bypass:
        return list(frames)

    expected_output = []

    for n in range(len(frames)):
        left_accumulator = 0
        right_accumulator = 0

        for k in range(NUM_TAPS):
            if n - k >= 0:
                left_sample, right_sample = frames[n - k]

                left_accumulator += left_sample * coefficients[k]
                right_accumulator += right_sample * coefficients[k]

        expected_output.append(
            (
                fir_processing(left_accumulator),
                fir_processing(right_accumulator),
            )
        )

    return expected_output


def delay_model(frames, delay_ms, w, g, bypass):
    assert 0 <= w < UNITY
    assert 0 <= g < UNITY

    delay_ms = min(delay_ms, MAX_DELAY_MS)

    buffer_size = delay_ms * SAMPLE_RATE_HZ // 1000

    if bypass or buffer_size == 0:
        return list(frames)

    buffer_left = [0] * buffer_size
    buffer_right = [0] * buffer_size

    output = []

    for i, (ld, rd) in enumerate(frames):
        ptr = i % buffer_size

        old_left = buffer_left[ptr]
        old_right = buffer_right[ptr]

        buffer_left[ptr] = sat_clip(
            ld + ((old_left * g) >> FRAC_BITS)
        )
        buffer_right[ptr] = sat_clip(
            rd + ((old_right * g) >> FRAC_BITS)
        )

        out_left = sat_clip(
            ld + ((w * (old_left - ld)) >> FRAC_BITS)
        )
        out_right = sat_clip(
            rd + ((w * (old_right - rd)) >> FRAC_BITS)
        )

        output.append((out_left, out_right))

    return output


def comb_filter_model(frames, comb_id, room_size, decay_cfg):
    delay = DELAYS[comb_id][room_size]

    g = feedback_coefficient(
        comb_id, room_size, decay_cfg
    )

    mem_left = [0] * delay
    mem_right = [0] * delay

    output = []

    for n, (left, right) in enumerate(frames):
        ptr = n % delay

        old_left = mem_left[ptr]
        old_right = mem_right[ptr]

        mem_left[ptr] = sat_clip(
            left + ((old_left * g) >> FRAC_BITS)
        )
        mem_right[ptr] = sat_clip(
            right + ((old_right * g) >> FRAC_BITS)
        )

        output.append((old_left, old_right))

    return output


def normalize_comb_outputs(comb_outputs):
    result = []

    for frames in zip(*comb_outputs):
        sum_left = sum(frame[0] for frame in frames)
        sum_right = sum(frame[1] for frame in frames)

        result.append(
            (sum_left >> 2, sum_right >> 2)
        )

    return result


def all_pass_model(frames, delay, diffusion_u014):
    mem_left = [0] * delay
    mem_right = [0] * delay

    output = []

    for n, (left, right) in enumerate(frames):
        ptr = n % delay

        old_left = mem_left[ptr]
        old_right = mem_right[ptr]

        new_left = sat_clip(
            left + (
                (old_left * diffusion_u014) >> FRAC_BITS
            )
        )
        new_right = sat_clip(
            right + (
                (old_right * diffusion_u014) >> FRAC_BITS
            )
        )

        out_left = sat_clip(
            old_left - (
                (new_left * diffusion_u014) >> FRAC_BITS
            )
        )
        out_right = sat_clip(
            old_right - (
                (new_right * diffusion_u014) >> FRAC_BITS
            )
        )

        mem_left[ptr] = new_left
        mem_right[ptr] = new_right

        output.append((out_left, out_right))

    return output


def wet_dry_model(dry_frames, wet_frames, wet):
    output = []

    for (dl, dr), (wl, wr) in zip(dry_frames, wet_frames):
        output.append(
            (
                sat_clip(dl + (((wl - dl) * wet) >> FRAC_BITS)),
                sat_clip(dr + (((wr - dr) * wet) >> FRAC_BITS)),
            )
        )

    return output


def reverb_model(
    frames,
    *,
    bypass,
    room_size,
    decay_cfg,
    diffusion,
    wet,
):
    if bypass:
        return list(frames)

    comb_outputs = [
        comb_filter_model(
            frames, comb_id, room_size, decay_cfg
        )
        for comb_id in range(4)
    ]

    normalized = normalize_comb_outputs(comb_outputs)

    ap0 = all_pass_model(
        normalized,
        ALL_PASS_DELAYS[0],
        diffusion,
    )

    ap1 = all_pass_model(
        ap0,
        ALL_PASS_DELAYS[1],
        diffusion,
    )

    return wet_dry_model(frames, ap1, wet)


def chain_reference(input_frames, config):

    amp_output = amp_model(
        input_frames,
        config["g"],
        config["amp_bypass"],
    )

    fir_output = fir_model(
        amp_output,
        load_fir_coefficients(config["mode_i"]),
        config["fir_bypass"],
    )

    delay_output = delay_model(
        fir_output,
        config["delay_i"],
        config["delay_w_i"],
        config["fb_i"],
        config["delay_bypass"],
    )

    reverb_output = reverb_model(
        delay_output,
        bypass=config["reverb_bypass"],
        room_size=config["room_i"],
        decay_cfg=config["decay_60"],
        diffusion=config["diffusion_i"],
        wet=config["reverb_w_i"],
    )

    return reverb_output


def make_config(**overrides):
    config = {
        "amp_bypass": False,
        "g": 20480,  # 1.25x gain

        "fir_bypass": False,
        "mode_i": 1,  # Warm

        "delay_bypass": False,
        "fb_i": convert_u014(0.3),
        "delay_w_i": convert_u014(0.25),
        "delay_i": 5,  # 5 ms: echoes after 240 frames

        "reverb_bypass": False,
        "room_i": 0,       # Small
        "decay_60": 25,    # 2.5 seconds
        "reverb_w_i": convert_u014(0.4),
        "diffusion_i": convert_u014(0.6),
    }

    config.update(overrides)
    return config


def configuration(dut, config):
    dut.amp_bypass.value = int(config["amp_bypass"])
    dut.g.value = int_to_twos(config["g"], 16)

    dut.fir_bypass.value = int(config["fir_bypass"])
    dut.mode_i.value = config["mode_i"]

    dut.delay_bypass.value = int(config["delay_bypass"])
    dut.fb_i.value = config["fb_i"]
    dut.delay_w_i.value = config["delay_w_i"]
    dut.delay_i.value = config["delay_i"]

    dut.reverb_bypass.value = int(config["reverb_bypass"])
    dut.room_i.value = config["room_i"]
    dut.decay_60.value = config["decay_60"]
    dut.reverb_w_i.value = config["reverb_w_i"]
    dut.diffusion_i.value = config["diffusion_i"]


async def generated_WS(dut):
    while True:
        dut.ws.value = 1

        for _ in range(BIT_SLOT):
            await FallingEdge(dut.i2s_clk)

        dut.ws.value = 0

        for _ in range(BIT_SLOT):
            await FallingEdge(dut.i2s_clk)


def clock_start(dut):
    dut.i2s_reset.value = 1
    dut.dsp_reset.value = 1
    dut.sd_i.value = 0
    configuration(dut, make_config())

    cocotb.start_soon(
        Clock(dut.dsp_clk, DSP_CLK, unit="ns").start()
    )
    cocotb.start_soon(
        Clock(dut.i2s_clk, I2S_CLK, unit="ns").start()
    )
    cocotb.start_soon(generated_WS(dut))


async def reset(dut, config):
    await FallingEdge(dut.i2s_clk)

    dut.i2s_reset.value = 1
    dut.dsp_reset.value = 1
    dut.sd_i.value = 0

    # Configurations are captured during reset
    configuration(dut, config)

    for _ in range(4):
        await RisingEdge(dut.i2s_clk)

    await FallingEdge(dut.i2s_clk)

    assert int(dut.chain_ready_o.value) == 0

    dut.i2s_reset.value = 0
    dut.dsp_reset.value = 0

    # FIR, Delay, Reverb must finish clearing their RAMs
    for _ in range(MAX_INIT_CYCLES):
        await FallingEdge(dut.dsp_clk)

        if int(dut.chain_ready_o.value):
            break
    else:
        raise AssertionError(
            "Timeout waiting for chain initialization"
        )

    # Allow the readiness synchronizer and I2S RX
    # to settle on complete frame boundaries.
    await FallingEdge(dut.ws)
    await FallingEdge(dut.ws)

    assert int(dut.chain_ready_o.value) == 1


async def send_i2s_word(dut, audio):
    audio = int_to_twos(audio)

    await RisingEdge(dut.i2s_clk)

    for i in range(WIDTH - 1, -1, -1):
        await FallingEdge(dut.i2s_clk)
        dut.sd_i.value = (audio >> i) & 1


async def send_i2s_frame(dut, left, right):
    await FallingEdge(dut.ws)
    await send_i2s_word(dut, left)

    await RisingEdge(dut.ws)
    await send_i2s_word(dut, right)


async def send_frames(dut, frames):
    for left, right in frames:
        await send_i2s_frame(dut, left, right)


async def receive_i2s_word(dut):
    await FallingEdge(dut.i2s_clk)
    await FallingEdge(dut.i2s_clk)

    output = 0

    for i in range(WIDTH - 1, -1, -1):
        await RisingEdge(dut.i2s_clk)

        output |= int(dut.sd_o.value) << i

    return twos_to_int(output)


async def receive_i2s_frame(dut):
    await FallingEdge(dut.ws)
    left = await receive_i2s_word(dut)

    await RisingEdge(dut.ws)
    right = await receive_i2s_word(dut)

    return left, right


async def receive_frames(dut, count):
    output = []

    for _ in range(count):
        output.append(await receive_i2s_frame(dut))

    return output


async def run_frames(dut, input_frames, config, label="chain"):

    expected = chain_reference(input_frames, config)

    # Use the measured latency for the corresponding configuration
    all_bypass = all([
        config["amp_bypass"],
        config["fir_bypass"],
        config["delay_bypass"],
        config["reverb_bypass"],
    ])

    latency = BYPASS_LATENCY if all_bypass else LATENCY

    await FallingEdge(dut.ws)

    sender = cocotb.start_soon(
        send_frames(dut, input_frames)
    )

    receiver = cocotb.start_soon(
        receive_frames(dut, len(input_frames) + latency)
    )

    await sender
    captured = await receiver

    actual = captured[latency:latency + len(input_frames)]

    assert actual == expected, (
        f"{label}: Frame comparison failed\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}"
    )

    dut._log.info(
        f"PASS {label}: {len(input_frames)} frames, "
        f"latency={latency}"
    )
    

@cocotb.test()
async def test_multiple_frames(dut):
    clock_start(dut)

    rng = random.Random(42)

    frames = [
        (0, 0),
        (1000, -1000),
        (MAX_24, MIN_24),
        (-1, 1),
    ]

    frames += [
        (
            rng.randint(-2000000, 2000000),
            rng.randint(-2000000, 2000000),
        )
        for _ in range(320)
    ]

    # Test all three FIR modes with all effects enabled
    for mode in [0, 1, 2]:
        config = make_config(mode_i=mode)

        await reset(dut, config)

        await run_frames(
            dut,
            frames,
            config,
            label=f"Full chain, FIR mode {mode}",
        )


@cocotb.test()
async def test_all_bypass(dut):
    clock_start(dut)

    config = make_config(
        amp_bypass=True,
        fir_bypass=True,
        delay_bypass=True,
        reverb_bypass=True,
    )

    frames = [
        (0, 0),
        (1000, -1000),
        (-3000, 1500),
        (MAX_24, MIN_24),
        (-1, 1),
        (500000, -500000),
    ] * 4

    await reset(dut, config)

    await run_frames(
        dut,
        frames,
        config,
        label="All bypass",
    )


@cocotb.test()
async def test_reset_startup(dut):
    clock_start(dut)

    config_before = make_config(
        mode_i=0,
        delay_i=5,
    )

    await reset(dut, config_before)

    # Populate the FIR and delay histories
    before_reset = [
        (100000, -100000),
        (500000, 250000),
        (MAX_24, MIN_24),
    ] * 100

    await run_frames(
        dut,
        before_reset,
        config_before,
        label="Before reset",
    )

    # Reset the whole chain, changing the FIR mode
    config_after = make_config(
        mode_i=2,
        delay_i=5,
        room_i=1,
        decay_60=35,
    )

    await reset(dut, config_after)

    assert int(dut.chain_ready_o.value) == 1

    # The new reference begins with empty audio history.
    # Previous FIR, delay, and reverb samples must not leak.
    after_reset = [
        (500000, -500000),
        (0, 0),
        (-100000, 100000),
    ] + [(0, 0)] * 300

    await run_frames(
        dut,
        after_reset,
        config_after,
        label="After reset",
    )
