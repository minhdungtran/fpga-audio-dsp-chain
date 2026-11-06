import os
import random as pyrandom

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge


WIDTH = 24
FRAC_BITS = 14
UNITY = 1 << FRAC_BITS
MAX_24 = (1 << (WIDTH - 1)) - 1
MIN_24 = -(1 << (WIDTH - 1))

ALL_PASS_ID = int(os.environ.get("TEST_ALL_PASS_ID", "0"))
DELAYS = (240, 82) 
assert ALL_PASS_ID in (0, 1), "TEST_ALL_PASS_ID must be 0 or 1"
DELAY_SAMPLES = DELAYS[ALL_PASS_ID]


def mask(width):
    return (1 << width) - 1


def two_complement_to_int(sample, width=WIDTH):
    sample &= mask(width)
    if sample & (1 << (width - 1)):
        sample -= 1 << width
    return sample


def int_to_two_complement(value, width=WIDTH):
    return value & mask(width)


def sat_clip(value):
    return max(MIN_24, min(MAX_24, int(value)))


def convert_014(diffusion):
    assert 0 <= diffusion < 1
    return min(UNITY - 1, round(diffusion * UNITY))


def all_pass_model(frames, delay_samples, diffusion_q14):
    assert delay_samples > 0
    assert 0 <= diffusion_q14 < UNITY

    buffer_left = [0] * delay_samples
    buffer_right = [0] * delay_samples
    output = []

    for n, (ld, rd) in enumerate(frames):
        ptr = n % delay_samples
        old_left = buffer_left[ptr]
        old_right = buffer_right[ptr]

        feedback_left = (old_left * diffusion_q14) >> FRAC_BITS
        feedback_right = (old_right * diffusion_q14) >> FRAC_BITS
        new_left = sat_clip(ld + feedback_left)
        new_right = sat_clip(rd + feedback_right)

        feedforward_left = (new_left * diffusion_q14) >> FRAC_BITS
        feedforward_right = (new_right * diffusion_q14) >> FRAC_BITS
        out_left = sat_clip(old_left - feedforward_left)
        out_right = sat_clip(old_right - feedforward_right)

        buffer_left[ptr] = new_left
        buffer_right[ptr] = new_right
        output.append((out_left, out_right))

    return output

def assertion_frames(actual_frames, expected_frames):
    assert len(actual_frames) == len(expected_frames), (
        f"Expected {len(expected_frames)} frames, received {len(actual_frames)}"
    )
    for frame_number, (actual, expected) in enumerate(
        zip(actual_frames, expected_frames)
    ):
        assert actual == expected, (
            f"ALL_PASS_ID={ALL_PASS_ID}, frame {frame_number}: "
            f"expected={expected}, actual={actual}"
        )


def clock_set_up(dut, period_ns=10):
    cocotb.start_soon(Clock(dut.dsp_clk, period_ns, units="ns").start())


async def reset(dut, diffusion_q14):
    await FallingEdge(dut.dsp_clk)
    dut.reset.value = 1
    dut.diffusion_i.value = diffusion_q14
    dut.ld_i.value = 0
    dut.rd_i.value = 0
    dut.valid_i.value = 0
    dut.ready_i.value = 1

    for _ in range(3):
        await RisingEdge(dut.dsp_clk)

    await FallingEdge(dut.dsp_clk)
    dut.reset.value = 0

    for _ in range(DELAY_SAMPLES + 10):
        await FallingEdge(dut.dsp_clk)
        if int(dut.ready_o.value):
            assert int(dut.valid_o.value) == 0
            return
        assert int(dut.valid_o.value) == 0

    raise AssertionError("Timeout: all-pass BRAM clearing did not finish")


async def send_input(ld, rd, dut):
    for _ in range(50):
        await FallingEdge(dut.dsp_clk)
        if int(dut.ready_o.value):
            dut.ld_i.value = int_to_two_complement(ld)
            dut.rd_i.value = int_to_two_complement(rd)
            dut.valid_i.value = 1

            # Transfer occurs at the following rising clock edge.
            await RisingEdge(dut.dsp_clk)
            await FallingEdge(dut.dsp_clk)
            dut.valid_i.value = 0
            return

    raise AssertionError("Timeout waiting for ready_o")


async def receive_output(dut):
    for _ in range(50):
        await FallingEdge(dut.dsp_clk)
        if int(dut.valid_o.value):
            ld = two_complement_to_int(int(dut.ld_o.value))
            rd = two_complement_to_int(int(dut.rd_o.value))
            return ld, rd

    raise AssertionError("Timeout waiting for valid_o")


async def run_frames(dut, frames):
    actual_frames = []
    for ld, rd in frames:
        await send_input(ld, rd, dut)
        actual_frames.append(await receive_output(dut))
    return actual_frames


async def test_with_configuration(dut, diffusion, frames):
    q14 = convert_014(diffusion)
    await reset(dut, q14)

    expected = all_pass_model(frames, DELAY_SAMPLES, q14)
    actual = await run_frames(dut, frames)
    assertion_frames(actual, expected)
    return actual


@cocotb.test()
async def test_zero_diffusion(dut):
    clock_set_up(dut)
    frames = [(12000, -8000)] + [(0, 0)] * (DELAY_SAMPLES + 5)
    actual = await test_with_configuration(dut, 0.0, frames)

    assert actual[0] == (0, 0)
    assert actual[DELAY_SAMPLES] == (12000, -8000)


@cocotb.test()
async def test_impulse_response(dut):
    clock_set_up(dut)
    frames = [(10000, -8000)] + [(0, 0)] * (3 * DELAY_SAMPLES + 5)
    actual = await test_with_configuration(dut, 0.5, frames)

    assert actual[0] == (-5000, 4000)
    assert actual[DELAY_SAMPLES] == (7500, -6000)
    assert actual[2 * DELAY_SAMPLES] == (3750, -3000)
    assert actual[3 * DELAY_SAMPLES] == (1875, -1500)


@cocotb.test()
async def test_stereo_independence(dut):
    clock_set_up(dut)
    frames = [(12000, 0), (0, 0), (0, -9000)]
    frames += [(0, 0)] * (2 * DELAY_SAMPLES + 5)
    await test_with_configuration(dut, 0.5, frames)


@cocotb.test()
async def test_negative_samples(dut):
    clock_set_up(dut)
    frames = [
        (-1, 1), (-3, 3), (-101, 101), (-1001, 1001),
        (7, -7), (-32769, 32769),
    ] + [(0, 0)] * (2 * DELAY_SAMPLES + 5)
    await test_with_configuration(dut, 0.25, frames)


@cocotb.test()
async def test_saturation(dut):
    clock_set_up(dut)
    frames = [(MAX_24, MIN_24)] * (3 * DELAY_SAMPLES + 10)
    frames += [(0, 0)] * (DELAY_SAMPLES + 5)
    await test_with_configuration(dut, 0.95, frames)


@cocotb.test()
async def test_random_frames(dut):
    clock_set_up(dut)
    rng = pyrandom.Random(42)
    frames = [
        (rng.randint(-500000, 500000), rng.randint(-500000, 500000))
        for _ in range(3 * DELAY_SAMPLES + 100)
    ]
    await test_with_configuration(dut, 0.75, frames)


@cocotb.test()
async def test_max_diffusion(dut):
    clock_set_up(dut)
    frames = [(5000, -5000)] + [(0, 0)] * (3 * DELAY_SAMPLES + 5)
    await reset(dut, UNITY - 1)
    expected = all_pass_model(frames, DELAY_SAMPLES, UNITY - 1)
    actual = await run_frames(dut, frames)
    assertion_frames(actual, expected)


@cocotb.test()
async def test_idle_no_input(dut):
    clock_set_up(dut)
    await reset(dut, convert_014(0.5))
    dut.valid_i.value = 0
    for _ in range(20):
        await FallingEdge(dut.dsp_clk)
        assert int(dut.ready_o.value) == 1
        assert int(dut.valid_o.value) == 0


@cocotb.test()
async def test_handshake(dut):
    clock_set_up(dut)
    await reset(dut, convert_014(0.5))

    # Block downstream WHILE the filter is still in LOAD.
    # This avoids trapping a previous transaction in DONE.
    dut.ready_i.value = 0
    await send_input(10000, -8000, dut)
    output = await receive_output(dut)
    assert output == (-5000, 4000)

    for _ in range(10):
        await FallingEdge(dut.dsp_clk)
        assert int(dut.valid_o.value) == 1
        assert int(dut.ready_o.value) == 0
        current = (
            two_complement_to_int(int(dut.ld_o.value)),
            two_complement_to_int(int(dut.rd_o.value)),
        )
        assert current == output, "Output changed during backpressure"

    dut.ready_i.value = 1
    await RisingEdge(dut.dsp_clk)
    await FallingEdge(dut.dsp_clk)
    assert int(dut.valid_o.value) == 0
    assert int(dut.ready_o.value) == 1


@cocotb.test()
async def test_reset_mid_stream(dut):
    clock_set_up(dut)
    await reset(dut, convert_014(0.5))

    before = [(20000, -10000)] + [(0, 0)] * (DELAY_SAMPLES + 10)
    await run_frames(dut, before)

    # Reassert reset and wait until both BRAMs have been cleared.
    await reset(dut, convert_014(0.5))
    after = [(0, 0)] * (2 * DELAY_SAMPLES + 10)
    actual = await run_frames(dut, after)
    assert all(frame == (0, 0) for frame in actual), (
        "Old all-pass feedback history survived reset"
    )
