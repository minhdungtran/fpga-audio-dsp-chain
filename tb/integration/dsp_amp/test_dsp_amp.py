import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

WIDTH = 24
GAIN_LENGTH = 16
FRAC_BITS = 14
SCK_PERIOD_NS = 10
SLOT_WIDTH = 32

MAX_24 = (1 << (WIDTH - 1)) - 1
MIN_24 = -(1 << (WIDTH - 1))

# Allow a few I2S frames for startup pipeline latency.
EXTRA_FRAMES = 6

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

async def generated_WS(dut):
    while True:
        dut.shared_WS.value = 1

        for _ in range(SLOT_WIDTH):
            await FallingEdge(dut.shared_sck)

        dut.shared_WS.value = 0

        for _ in range(SLOT_WIDTH):
            await FallingEdge(dut.shared_sck)


def clock_start(dut):
    cocotb.start_soon(
        Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start()
    )
    cocotb.start_soon(generated_WS(dut))


async def reset(dut, gain, bypass):
    await FallingEdge(dut.shared_sck)

    dut.shared_reset.value = 1
    dut.shared_SD.value = 0

    # Configuration is sampled by amplifier during reset.
    dut.g.value = int_to_twos(gain, GAIN_LENGTH)
    dut.bypass.value = int(bypass)

    for _ in range(4):
        await RisingEdge(dut.shared_sck)

    await FallingEdge(dut.shared_sck)
    dut.shared_reset.value = 0

    # Establish I2S frame synchronization before sending data.
    await FallingEdge(dut.shared_WS)
    await FallingEdge(dut.shared_WS)


async def send_i2s_word(dut, audio):
    audio = int_to_twos(audio)

    await RisingEdge(dut.shared_sck)

    for i in range(WIDTH - 1, -1, -1):
        await FallingEdge(dut.shared_sck)
        dut.shared_SD.value = (audio >> i) & 1


async def send_i2s_frame(dut, left, right):
    await FallingEdge(dut.shared_WS)
    await send_i2s_word(dut, left)

    await RisingEdge(dut.shared_WS)
    await send_i2s_word(dut, right)


async def send_frames(dut, frames):
    for left, right in frames:
        await send_i2s_frame(dut, left, right)


async def receive_i2s_word(dut):
    await FallingEdge(dut.shared_sck)
    await FallingEdge(dut.shared_sck)

    value = 0

    for i in range(WIDTH - 1, -1, -1):
        await RisingEdge(dut.shared_sck)
        value |= int(dut.output_SD.value) << i

    return twos_to_int(value)


async def receive_i2s_frame(dut):
    await FallingEdge(dut.shared_WS)
    left = await receive_i2s_word(dut)

    await RisingEdge(dut.shared_WS)
    right = await receive_i2s_word(dut)

    return (left, right)


async def receive_frames(dut, count):
    return [
        await receive_i2s_frame(dut)
        for _ in range(count)
    ]


async def test_with_configuration(dut, frames, gain, bypass):
    await reset(dut, gain, bypass)

    expected = amp_model(frames, gain, bypass)

    sender = cocotb.start_soon(send_frames(dut, frames))

    receiver = cocotb.start_soon(
        receive_frames(dut, len(frames) + EXTRA_FRAMES)
    )

    await sender
    captured = await receiver

    # Find a contiguous match, allowing for initial I2S latency.
    matches = [
        offset
        for offset in range(EXTRA_FRAMES + 1)
        if captured[offset:offset + len(expected)] == expected
    ]

    assert matches, (
        f"Amplifier integration mismatch\n"
        f"gain={gain}, bypass={bypass}\n"
        f"expected first frames={expected[:5]}\n"
        f"captured first frames={captured[:10]}"
    )

    dut._log.info(
        f"PASS: gain={gain}, bypass={bypass}, "
        f"matched at I2S frame offset {matches[0]}"
    )


@cocotb.test()
async def test_gain(dut):
    clock_start(dut)

    frames = [
        (1000, -500),
        (-3000, 1500),
        (MAX_24, MIN_24),
        (-1, 1),
        (5000000, -5000000),
    ]

    for gain in [0, 8192, 16384, 32767, -16384, -32768]:
        await test_with_configuration(
            dut,
            frames=frames,
            gain=gain,
            bypass=False,
        )


@cocotb.test()
async def test_random(dut):
    clock_start(dut)

    rng = random.Random(42)

    frames = [
        (
            rng.randint(MIN_24, MAX_24),
            rng.randint(MIN_24, MAX_24),
        )
        for _ in range(200)
    ]

    await test_with_configuration(
        dut,
        frames=frames,
        gain=9000,
        bypass=False,
    )


@cocotb.test()
async def test_bypass(dut):
    clock_start(dut)

    frames = [
        (1000, -500),
        (-3000, 1500),
        (MAX_24, MIN_24),
        (0, 0),
        (-1, 1),
    ]

    await test_with_configuration(
        dut,
        frames=frames,
        gain=32767,
        bypass=True,
    )















  



