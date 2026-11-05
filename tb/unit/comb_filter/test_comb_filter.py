
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

WIDTH = 24
FRAC_BITS = 14
UNITY = 1 << FRAC_BITS
FS = 48000
MAX_DECAY = 50

MAX_24 = (1 << (WIDTH - 1)) - 1
MIN_24 = -(1 << (WIDTH - 1))

# Must match the COMB_ID parameter used to compile the DUT.
COMB_ID = int(os.environ.get("TEST_COMB_ID", "0"))

DELAYS = [
    [1070, 1426, 1783],  # Comb 0: Small, Medium, Large
    [1336, 1781, 2227],  # Comb 1
    [1480, 1973, 2467],  # Comb 2
    [1574, 2098, 2623],  # Comb 3
]

assert 0 <= COMB_ID < 4

def mask(width):
    return (1 << width) - 1


def twos_complement_to_int(value, width=WIDTH):
    value &= mask(width)

    if value & (1 << (width - 1)):
        value -= 1 << width

    return value


def int_to_twos_complement(value, width=WIDTH):
    return value & mask(width)


def sat_clip(value):
    return max(MIN_24, min(MAX_24, int(value)))


def calculate_feedback(D, decay_cfg):
    """
    Calculate the feedback coefficient in U0.14 format.

    D: Delay length in samples.
    decay_cfg: Integer 0-50, representing 0-5 seconds.
    """

    assert D > 0
    assert 0 <= decay_cfg <= MAX_DECAY

    if decay_cfg == 0:
        return 0

    T60 = decay_cfg / 10.0

    g = 10 ** (-3 * D / (FS * T60))

    G = round(g * UNITY)

    return max(0, min(G, UNITY - 1))

def comb_filter_model(frames, comb_id, room_size, decay_cfg):

    D = DELAYS[comb_id][room_size]
    G = calculate_feedback(D, decay_cfg)

    buffer_left = [0] * D
    buffer_right = [0] * D

    output = []
    ptr = 0

    for ld, rd in frames:

        old_left = buffer_left[ptr]
        old_right = buffer_right[ptr]

        feedback_left = (old_left * G) >> FRAC_BITS
        feedback_right = (old_right * G) >> FRAC_BITS

        buffer_left[ptr] = sat_clip(ld + feedback_left)
        buffer_right[ptr] = sat_clip(rd + feedback_right)

        output.append((old_left, old_right))

        ptr = (ptr + 1) % D

    return output


def assertion_frames(actual_frames, expected_frames):

    assert len(actual_frames) == len(expected_frames), (
        f"Frame count mismatch: "
        f"actual={len(actual_frames)}, "
        f"expected={len(expected_frames)}"
    )

    for n, (actual, expected) in enumerate(
        zip(actual_frames, expected_frames)
    ):
        assert actual == expected, (
            f"Comb {COMB_ID}, frame {n}: "
            f"expected={expected}, actual={actual}"
        )

def clock_set_up(dut):
    cocotb.start_soon(
        Clock(dut.dsp_clk, 10, units="ns").start()
    )

async def reset_dut(dut, room_size, decay_cfg):

    await FallingEdge(dut.dsp_clk)

    dut.reset.value = 1
    dut.valid_i.value = 0
    dut.ready_i.value = 1

    dut.ld_i.value = 0
    dut.rd_i.value = 0

    dut.room_i.value = room_size
    dut.decay_60.value = decay_cfg

    for _ in range(3):
        await RisingEdge(dut.dsp_clk)

    await FallingEdge(dut.dsp_clk)
    dut.reset.value = 0

    max_depth = DELAYS[COMB_ID][2]

    for _ in range(max_depth + 10):
        await FallingEdge(dut.dsp_clk)

        if int(dut.ready_o.value):
            return

    raise AssertionError("Comb filter did not finish BRAM clearing")


async def send_input(dut, ld, rd):

    for _ in range(50):
        await FallingEdge(dut.dsp_clk)

        if int(dut.ready_o.value):

            dut.ld_i.value = int_to_twos_complement(ld)
            dut.rd_i.value = int_to_twos_complement(rd)
            dut.valid_i.value = 1

            await RisingEdge(dut.dsp_clk)

            await FallingEdge(dut.dsp_clk)
            dut.valid_i.value = 0

            return

    raise AssertionError("Timeout waiting for ready_o")


async def receive_output(dut):

    for _ in range(50):
        await FallingEdge(dut.dsp_clk)

        if int(dut.valid_o.value):

            ld = twos_complement_to_int(
                int(dut.ld_o.value)
            )

            rd = twos_complement_to_int(
                int(dut.rd_o.value)
            )

            return (ld, rd)

    raise AssertionError("Timeout waiting for valid_o")


async def run_frames(dut, frames):

    actual_output = []

    for ld, rd in frames:
        await send_input(dut, ld, rd)

        result = await receive_output(dut)
        actual_output.append(result)

    return actual_output


async def test_with_configuration(
    dut, room_size, decay_cfg, frames
):
    await reset_dut(dut, room_size, decay_cfg)

    expected = comb_filter_model(
        frames,
        COMB_ID,
        room_size,
        decay_cfg,
    )

    actual = await run_frames(dut, frames)

    assertion_frames(actual, expected)

@cocotb.test()
async def test_zero_feedback(dut):

    clock_set_up(dut)

    for room_size in range(3):

        D = DELAYS[COMB_ID][room_size]

        frames = [(12000, 0)] + [(0, 0)] * (D + 5)

        await test_with_configuration(
            dut,
            room_size=room_size,
            decay_cfg=0,
            frames=frames,
        )

@cocotb.test()
async def test_feedback_decay(dut):

    clock_set_up(dut)

    room_size = 1
    decay_cfg = 25  # RT60 = 2.5 seconds

    D = DELAYS[COMB_ID][room_size]

    # Long enough for at least three echoes.
    frames = [(16000, 0)] + [(0, 0)] * (3 * D + 5)

    await test_with_configuration(
        dut,
        room_size,
        decay_cfg,
        frames,
    )

@cocotb.test()
async def test_stereo_independence(dut):

    clock_set_up(dut)

    room_size = 0
    decay_cfg = 30

    D = DELAYS[COMB_ID][room_size]

    frames = [
        (12000, 0),
        (0, 0),
        (0, -8000),
    ] + [(0, 0)] * (2 * D + 5)

    await test_with_configuration(
        dut,
        room_size,
        decay_cfg,
        frames,
    )

@cocotb.test()
async def test_negative_samples(dut):

    clock_set_up(dut)

    room_size = 0
    decay_cfg = 20

    D = DELAYS[COMB_ID][room_size]

    frames = [
        (-1, 1),
        (-3, 3),
        (-101, 101),
        (-1001, 1001),
    ] + [(0, 0)] * (2 * D + 5)

    await test_with_configuration(
        dut,
        room_size,
        decay_cfg,
        frames,
    )

@cocotb.test()
async def test_saturation(dut):

    clock_set_up(dut)

    room_size = 0
    decay_cfg = 50  # Maximum RT60

    D = DELAYS[COMB_ID][room_size]

    frames = (
        [(MAX_24, MIN_24)] * (D + 50)
        + [(0, 0)] * 50
    )

    await test_with_configuration(
        dut,
        room_size,
        decay_cfg,
        frames,
    )

@cocotb.test()
async def test_random_frames(dut):

    clock_set_up(dut)

    room_size = 1
    decay_cfg = 35

    D = DELAYS[COMB_ID][room_size]

    rng = random.Random(42)

    frames = [
        (
            rng.randint(-100000, 100000),
            rng.randint(-100000, 100000),
        )
        for _ in range(2 * D + 100)
    ]

    await test_with_configuration(
        dut,
        room_size,
        decay_cfg,
        frames,
    )

@cocotb.test()
async def test_handshake(dut):

    clock_set_up(dut)

    room_size = 0
    decay_cfg = 0

    await reset_dut(dut, room_size, decay_cfg)

    D = DELAYS[COMB_ID][room_size]

    for _ in range(D):
        await send_input(dut, 1234, -5678)
        await receive_output(dut)

    await RisingEdge(dut.dsp_clk)
    await FallingEdge(dut.dsp_clk)

    assert int(dut.ready_o.value) == 1

    dut.ready_i.value = 0

    await send_input(dut, 0, 0)

    output = await receive_output(dut)

    assert output == (1234, -5678)

    # valid_o and output data must remain stable.
    for _ in range(10):

        await FallingEdge(dut.dsp_clk)

        assert int(dut.valid_o.value) == 1
        assert int(dut.ready_o.value) == 0

        current_output = (
            twos_complement_to_int(int(dut.ld_o.value)),
            twos_complement_to_int(int(dut.rd_o.value)),
        )

        assert current_output == output

    # Allow downstream consumption.
    dut.ready_i.value = 1

    await RisingEdge(dut.dsp_clk)
    await FallingEdge(dut.dsp_clk)

    assert int(dut.valid_o.value) == 0
    assert int(dut.ready_o.value) == 1

@cocotb.test()
async def test_reset_mid_stream(dut):

    clock_set_up(dut)

    room_size = 0
    decay_cfg = 25

    D = DELAYS[COMB_ID][room_size]

    await reset_dut(dut, room_size, decay_cfg)

    before_reset = (
        [(20000, -10000)]
        + [(0, 0)] * (D + 10)
    )

    await run_frames(dut, before_reset)

    # Reset should clear all previous comb history.
    await reset_dut(dut, room_size, decay_cfg)

    after_reset = [(0, 0)] * (D + 10)

    actual = await run_frames(dut, after_reset)

    assert all(frame == (0, 0) for frame in actual), (
        "Previous feedback history survived reset"
    )
