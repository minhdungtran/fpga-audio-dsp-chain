import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge


WIDTH = 24
NUM_TAPS = 63
FRAC_BITS = 15
COEFF_WIDTH = 16
BIT_SLOT = 32

DSP_CLK = 20          # 50 MHz
I2S_CLK = 325.52  # 3.072 MHz, 48 kHz stereo

MAX_24 = (1 << (WIDTH - 1)) - 1
MIN_24 = -(1 << (WIDTH - 1))

# Same frame-latency convention as dsp_reverb
LATENCY = 2
BYPASS_LATENCY = 1

COEFF_DIR = Path("coefficients/fir/mem")

MODES = {
    0: "fir_bright_q15.mem",
    1: "fir_warm_q15.mem",
    2: "fir_dark_q15.mem",
}

def int_to_twos(value, width=WIDTH):
    return value & ((1 << width) - 1)


def twos_to_int(value, width=WIDTH):
    value &= (1 << width) - 1

    if value & (1 << (width - 1)):
        value -= 1 << width

    return value


def sat_clip(value):
    return max(MIN_24, min(MAX_24, value))


def processing(accumulator):
    offset = 1 << (FRAC_BITS - 1)

    if accumulator >= 0:
        rounded = (accumulator + offset) >> FRAC_BITS
    else:
        rounded = (accumulator + offset - 1) >> FRAC_BITS

    return sat_clip(rounded)


def load_coefficients(mode):
    path = COEFF_DIR / MODES[mode]
    coefficients = []

    with path.open("r") as file:
        for line in file:
            line = line.strip()

            if line:
                coefficients.append(
                    twos_to_int(int(line, 16), COEFF_WIDTH)
                )

    assert len(coefficients) == NUM_TAPS

    return coefficients


def fir_model(input_frames, coefficients, bypass=False):
    if bypass:
        return list(input_frames)

    expected_output = []

    for n in range(len(input_frames)):
        left_accumulator = 0
        right_accumulator = 0

        for k in range(NUM_TAPS):
            if n - k >= 0:
                left_sample, right_sample = input_frames[n - k]

                left_accumulator += left_sample * coefficients[k]
                right_accumulator += right_sample * coefficients[k]

        expected_output.append(
            (
                processing(left_accumulator),
                processing(right_accumulator),
            )
        )

    return expected_output


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
    dut.bypass.value = 0
    dut.mode_i.value = 0

    cocotb.start_soon(
        Clock(dut.dsp_clk, DSP_CLK, unit="ns").start()
    )
    cocotb.start_soon(
        Clock(dut.i2s_clk, I2S_CLK, unit="ns").start()
    )
    cocotb.start_soon(generated_WS(dut))


async def reset(dut, mode=0, bypass=False):
    await FallingEdge(dut.i2s_clk)

    dut.i2s_reset.value = 1
    dut.dsp_reset.value = 1
    dut.sd_i.value = 0
    dut.mode_i.value = mode
    dut.bypass.value = int(bypass)

    # Reset both clock domains
    for _ in range(3):
        await RisingEdge(dut.i2s_clk)

    await FallingEdge(dut.i2s_clk)

    assert int(dut.chain_ready_o.value) == 0, (
        "chain_ready_o should be low during reset"
    )

    dut.i2s_reset.value = 0
    dut.dsp_reset.value = 0

    # FIR must clear its 63 sample-memory locations
    for _ in range(5):
        await FallingEdge(dut.dsp_clk)

        assert int(dut.chain_ready_o.value) == 0, (
            "FIR reported ready before initialization"
        )

    # Wait until the FIR finishes initialization
    for _ in range(NUM_TAPS + 50):
        await FallingEdge(dut.dsp_clk)

        if int(dut.chain_ready_o.value):
            break
    else:
        raise AssertionError("FIR startup initialization timeout")

    # Allow chain readiness to cross into the I2S domain
    # and synchronize to complete I2S frames.
    await FallingEdge(dut.ws)
    await FallingEdge(dut.ws)


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
    frames = []

    for _ in range(count):
        frames.append(await receive_i2s_frame(dut))

    return frames


async def run_frames(dut, input_frames, mode=0, bypass=False):
    coefficients = load_coefficients(mode)

    expected = fir_model(input_frames, coefficients, bypass)

    latency = BYPASS_LATENCY if bypass else LATENCY

    # Start input and output concurrently
    await FallingEdge(dut.ws)

    send = cocotb.start_soon(send_frames(dut, input_frames))

    receive = cocotb.start_soon(
        receive_frames(dut, len(input_frames) + latency)
    )

    await send
    captured = await receive

    actual = captured[latency:latency + len(input_frames)]

    for i, (got, exp) in enumerate(zip(actual, expected)):
        assert got == exp, (
            f"Frame {i} mismatch\n"
            f"Mode: {mode}, Bypass: {bypass}\n"
            f"Input: {input_frames[i]}\n"
            f"Expected: {exp}\n"
            f"Actual: {got}"
        )

    dut._log.info(
        f"PASS: {len(input_frames)} frames, "
        f"mode={mode}, bypass={bypass}"
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
            rng.randint(MIN_24, MAX_24),
            rng.randint(MIN_24, MAX_24),
        )
        for _ in range(100)
    ]

    for mode in [0, 1, 2]:
        await reset(dut, mode=mode, bypass=False)
        await run_frames(dut, frames, mode=mode)


@cocotb.test()
async def test_bypass(dut):
    clock_start(dut)

    frames = [
        (0, 0),
        (1000, -500),
        (-3000, 1500),
        (MAX_24, MIN_24),
        (-1, 1),
        (500000, -500000),
    ]

    await reset(dut, mode=1, bypass=True)

    await run_frames(
        dut,
        frames,
        mode=1,
        bypass=True,
    )


@cocotb.test()
async def test_reset_startup(dut):
    clock_start(dut)

    # Fill the FIR circular buffers with nonzero samples
    await reset(dut, mode=0)

    before_reset = [
        (100000, -100000),
        (500000, 250000),
        (MAX_24, MIN_24),
    ] * 10

    await run_frames(dut, before_reset, mode=0)

    # Reset both clock domains and select a different mode.
    # The old sample history must be cleared.
    await reset(dut, mode=2)

    assert int(dut.chain_ready_o.value) == 1, (
        "FIR should be ready after initialization"
    )

    # Test new input against a fresh zero-history FIR model
    after_reset = [
        (500000, -500000),
        (0, 0),
        (-100000, 100000),
    ] + [(0, 0)] * (NUM_TAPS + 3)

    await run_frames(dut, after_reset, mode=2)


  



