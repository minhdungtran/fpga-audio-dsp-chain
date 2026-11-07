import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge


WIDTH = 24
COEFF_WIDTH = 16
FRAC_BITS = 15
NUM_TAPS = 63

DSP_CLK = 10  # ns

MAX_24 = (1 << (WIDTH - 1)) - 1
MIN_24 = -(1 << (WIDTH - 1))

COEFF_DIR = Path("coefficients/fir/mem")

MODES = {
    0: "fir_bright_q15.mem",
    1: "fir_warm_q15.mem",
    2: "fir_dark_q15.mem",
    3: "fir_warm_q15.mem",  # Reserved -> Warm
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
    # Matches the RTL ROUND state: nearest, ties away from zero
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
        return [
            (twos_to_int(left), twos_to_int(right))
            for left, right in input_frames
        ]

    expected_output = []

    for n in range(len(input_frames)):
        left_accumulator = 0
        right_accumulator = 0

        for k in range(NUM_TAPS):
            if n - k >= 0:
                left_sample = twos_to_int(
                    input_frames[n - k][0]
                )
                right_sample = twos_to_int(
                    input_frames[n - k][1]
                )

                left_accumulator += left_sample * coefficients[k]
                right_accumulator += right_sample * coefficients[k]

        expected_output.append(
            (
                processing(left_accumulator),
                processing(right_accumulator),
            )
        )

    return expected_output


async def clock_start(dut):
    cocotb.start_soon(
        Clock(dut.dsp_clk, DSP_CLK, unit="ns").start()
    )


async def reset(dut, mode=0, bypass=False):
    await FallingEdge(dut.dsp_clk)

    dut.reset.value = 1
    dut.valid_i.value = 0
    dut.ready_i.value = 1
    dut.ld_i.value = 0
    dut.rd_i.value = 0

    # Configuration captured during reset
    dut.mode_i.value = mode
    dut.bypass.value = int(bypass)

    for _ in range(3):
        await RisingEdge(dut.dsp_clk)

    await FallingEdge(dut.dsp_clk)
    dut.reset.value = 0

    # Wait for FIR circular RAM clearing to finish
    for _ in range(NUM_TAPS + 10):
        await FallingEdge(dut.dsp_clk)
        if int(dut.ready_o.value):
            return

    raise AssertionError("FIR initialization timeout")


async def send_input(dut, left, right):
    for _ in range(300):
        await FallingEdge(dut.dsp_clk)

        if int(dut.ready_o.value):
            dut.ld_i.value = int_to_twos(left)
            dut.rd_i.value = int_to_twos(right)
            dut.valid_i.value = 1

            # Frame accepted at rising edge
            await RisingEdge(dut.dsp_clk)
            await FallingEdge(dut.dsp_clk)

            dut.valid_i.value = 0
            return

    raise AssertionError("Timeout waiting for FIR ready_o")


async def receive_output(dut):
    for _ in range(300):
        if int(dut.valid_o.value):
            return (
                twos_to_int(int(dut.ld_o.value)),
                twos_to_int(int(dut.rd_o.value)),
            )

        await FallingEdge(dut.dsp_clk)

    raise AssertionError("Timeout waiting for FIR valid_o")


async def run_frames(dut, frames):
    output = []

    for left, right in frames:
        await send_input(dut, left, right)
        output.append(await receive_output(dut))

    return output


async def test_with_configuration(
    dut, frames, mode=0, bypass=False
):
    await reset(dut, mode, bypass)

    coefficients = load_coefficients(mode)

    expected = fir_model(
        frames, coefficients, bypass
    )

    actual = await run_frames(dut, frames)

    for i, (got, exp) in enumerate(zip(actual, expected)):
        assert got == exp, (
            f"Frame {i} failed\n"
            f"mode={mode}, bypass={bypass}\n"
            f"input={frames[i]}\n"
            f"expected={exp}\n"
            f"actual={got}"
        )


@cocotb.test()
async def test_impulse(dut):
    await clock_start(dut)

    frames = [
        (MAX_24, 0),
        (0, MAX_24),
    ] + [(0, 0)] * (NUM_TAPS + 3)

    for mode in range(3):
        await test_with_configuration(
            dut,
            frames=frames,
            mode=mode,
        )


@cocotb.test()
async def test_random_frames(dut):
    await clock_start(dut)

    rng = random.Random(42)

    frames = [
        (
            rng.randint(MIN_24, MAX_24),
            rng.randint(MIN_24, MAX_24),
        )
        for _ in range(100)
    ]

    for mode in range(3):
        await test_with_configuration(
            dut,
            frames=frames,
            mode=mode,
        )


@cocotb.test()
async def test_bypass(dut):
    await clock_start(dut)

    frames = [
        (0, 0),
        (1000, -1000),
        (MAX_24, MIN_24),
        (-1, 1),
        (500000, -500000),
    ]

    await test_with_configuration(
        dut,
        frames=frames,
        mode=2,
        bypass=True,
    )


@cocotb.test()
async def test_saturation(dut):
    await clock_start(dut)

    mode = 1
    coefficients = load_coefficients(mode)

    # Construct samples aligned with coefficient signs
    # to produce a large convolution magnitude.
    frames = []

    for i in range(NUM_TAPS):
        coeff = coefficients[NUM_TAPS - 1 - i]

        if coeff >= 0:
            frames.append((MAX_24, MIN_24))
        else:
            frames.append((MIN_24, MAX_24))

    frames += [(0, 0)] * 5

    await test_with_configuration(
        dut,
        frames=frames,
        mode=mode,
    )


@cocotb.test()
async def test_output_handshake(dut):
    await clock_start(dut)
    await reset(dut, mode=1)

    await FallingEdge(dut.dsp_clk)
    dut.ready_i.value = 0

    await send_input(dut, 100000, -100000)

    expected = fir_model(
        [(100000, -100000)],
        load_coefficients(1),
    )[0]

    result = await receive_output(dut)

    assert result == expected

    # Output must remain valid while downstream is busy
    for _ in range(10):
        await FallingEdge(dut.dsp_clk)

        assert int(dut.valid_o.value) == 1
        assert int(dut.ready_o.value) == 0

        current = (
            twos_to_int(int(dut.ld_o.value)),
            twos_to_int(int(dut.rd_o.value)),
        )

        assert current == result

    # Release downstream
    dut.ready_i.value = 1

    await RisingEdge(dut.dsp_clk)
    await FallingEdge(dut.dsp_clk)

    assert int(dut.valid_o.value) == 0
    assert int(dut.ready_o.value) == 1


@cocotb.test()
async def test_reset_mid_stream(dut):
    await clock_start(dut)

    await reset(dut, mode=0)

    previous_frames = [
        (100000, -50000),
        (200000, 100000),
        (MAX_24, MIN_24),
    ]

    await run_frames(dut, previous_frames)

    # Reset should clear the previous FIR sample history
    new_frames = [
        (500000, -500000),
        (0, 0),
    ] + [(0, 0)] * (NUM_TAPS + 2)

    await test_with_configuration(
        dut,
        frames=new_frames,
        mode=2,
    )


@cocotb.test()
async def test_reserved_mode(dut):
    await clock_start(dut)

    frames = [
        (MAX_24, 0),
        (0, MIN_24),
        (1000, -2000),
    ] + [(0, 0)] * 5

    await test_with_configuration(
        dut,
        frames=frames,
        mode=3,
    )

    


            
