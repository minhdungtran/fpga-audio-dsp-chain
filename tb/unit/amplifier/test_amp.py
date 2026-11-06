import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

WIDTH = 24
FRAC_BITS = 14
GAIN_LENGTH = 16

MAX_24 = (1 << (WIDTH - 1)) - 1
MIN_24 = -(1 << (WIDTH - 1))


def int_to_twos(value, width=WIDTH):
    return value & ((1 << width) - 1)


def twos_to_int(value, width=WIDTH):
    value &= (1 << width) - 1
    if value & (1 << (width - 1)):
        value -= 1 << width
    return value


def sat_clip(value):
    return max(MIN_24, min(MAX_24, value))


def amp_model(frames, gain, bypass):
    if bypass:
        return frames

    return [
        (
            sat_clip((ld * gain) >> FRAC_BITS),
            sat_clip((rd * gain) >> FRAC_BITS)
        )
        for ld, rd in frames
    ]


def clock_set_up(dut):
    cocotb.start_soon(Clock(dut.dsp_clk, 10, unit="ns").start())


async def reset(dut, gain, bypass):
    dut.reset.value = 1
    dut.valid_i.value = 0
    dut.ready_i.value = 1
    dut.ld_i.value = 0
    dut.rd_i.value = 0
    dut.g.value = int_to_twos(gain, GAIN_LENGTH)
    dut.bypass.value = int(bypass)

    for _ in range(3):
        await RisingEdge(dut.dsp_clk)

    await FallingEdge(dut.dsp_clk)
    dut.reset.value = 0


async def send_input(dut, ld, rd):
    for _ in range(50):
        await FallingEdge(dut.dsp_clk)

        if int(dut.ready_o.value):
            dut.ld_i.value = int_to_twos(ld)
            dut.rd_i.value = int_to_twos(rd)
            dut.valid_i.value = 1

            await RisingEdge(dut.dsp_clk)
            await FallingEdge(dut.dsp_clk)
            dut.valid_i.value = 0
            return

    raise AssertionError("Timeout waiting for ready_o")


async def receive_output(dut):
    for _ in range(50):
        if int(dut.valid_o.value):
            return (
                twos_to_int(int(dut.ld_o.value)),
                twos_to_int(int(dut.rd_o.value))
            )

        await FallingEdge(dut.dsp_clk)

    raise AssertionError("Timeout waiting for valid_o")


async def test_with_configuration(dut, gain, bypass, frames):
    await reset(dut, gain, bypass)

    expected = amp_model(frames, gain, bypass)
    actual = []

    for ld, rd in frames:
        await send_input(dut, ld, rd)
        actual.append(await receive_output(dut))

    for i, (got, exp) in enumerate(zip(actual, expected)):
        assert got == exp, (
            f"Frame {i}, gain={gain}, bypass={bypass}: "
            f"expected={exp}, actual={got}"
        )

@cocotb.test()
async def test_gain(dut):
    clock_set_up(dut)

    frames = [
        (1000, -1000),
        (-1, 1),
        (MAX_24, MIN_24),
        (5000000, -5000000),
        (0, 0)
    ]

    for gain in [0, 8192, 16384, 32767, -16384, -32768]:
        await test_with_configuration(
            dut, gain=gain, bypass=False, frames=frames
        )

@cocotb.test()
async def test_bypass(dut):
    clock_set_up(dut)

    frames = [
        (1000, -500),
        (-3000, 1500),
        (MAX_24, MIN_24),
        (0, 0)
    ]

    await test_with_configuration(
        dut, gain=32767, bypass=True, frames=frames
    )


@cocotb.test()
async def test_handshake(dut):
    clock_set_up(dut)

    await reset(dut, gain=16384, bypass=False)

    # Downstream is not ready
    dut.ready_i.value = 0

    await send_input(dut, 1000, -500)
    output = await receive_output(dut)

    assert output == (1000, -500)

    # Output must remain valid and stable
    for _ in range(10):
        await FallingEdge(dut.dsp_clk)

        assert int(dut.valid_o.value) == 1
        assert int(dut.ready_o.value) == 0

        current = (
            twos_to_int(int(dut.ld_o.value)),
            twos_to_int(int(dut.rd_o.value))
        )

        assert current == output

    # Allow downstream to receive the output
    dut.ready_i.value = 1

    await RisingEdge(dut.dsp_clk)
    await FallingEdge(dut.dsp_clk)

    assert int(dut.valid_o.value) == 0
    assert int(dut.ready_o.value) == 1
