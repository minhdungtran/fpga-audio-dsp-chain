import random as pyrandom

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

DSP_CLK = 20
I2S_CLK = 325.52
BIT_SLOT = 32
WIDTH = 24
FRAC_BITS = 14
UNITY = 1 << FRAC_BITS
FS = 48_000
MAX_DECAY = 50
MAX_24 = (1 << (WIDTH - 1)) - 1
MIN_24 = -(1 << (WIDTH - 1))

LATENCY = 2

DELAYS = [
    [1070, 1426, 1783],
    [1336, 1781, 2227],
    [1480, 1973, 2467],
    [1574, 2098, 2623],
]
ALL_PASS_DELAYS = (240, 82)


def mask(width):
    return (1 << width) - 1


def two_complement_to_int(sample, width=WIDTH):
    sample = int(sample) & mask(width)
    if sample & (1 << (width - 1)):
        sample -= 1 << width
    return sample


def int_to_two_complement(value, width=WIDTH):
    return int(value) & mask(width)


def sat_clip(value):
    return max(MIN_24, min(MAX_24, int(value)))


def convert_u014(value):
    assert 0.0 <= value <= 1.0
    return min(UNITY - 1, max(0, round(value * UNITY)))


def feedback_coefficient(comb_id, room_size, decay_cfg):
    """Independent model of the coefficient generator's RT60 formula."""
    assert 0 <= comb_id < 4
    assert 0 <= room_size < 3
    assert 0 <= decay_cfg <= MAX_DECAY

    if decay_cfg == 0:
        return 0

    delay_samples = DELAYS[comb_id][room_size]
    t60_seconds = decay_cfg / 10.0
    feedback = 10.0 ** (-3.0 * delay_samples / (FS * t60_seconds))
    return convert_u014(feedback)


def comb_filter_model(frames, comb_id, room_size, decay_cfg):
    delay = DELAYS[comb_id][room_size]
    g = feedback_coefficient(comb_id, room_size, decay_cfg)

    mem_left = [0] * delay
    mem_right = [0] * delay
    output = []

    for n, (left, right) in enumerate(frames):
        ptr = n % delay
        old_left = mem_left[ptr]
        old_right = mem_right[ptr]

        mem_left[ptr] = sat_clip(left + ((old_left * g) >> FRAC_BITS))
        mem_right[ptr] = sat_clip(right + ((old_right * g) >> FRAC_BITS))

        output.append((old_left, old_right))

    return output


def normalize_comb_outputs(comb_outputs):
    """Arithmetic 26-bit signed sum of four 24-bit values, then >>> 2."""
    assert len(comb_outputs) == 4
    count = len(comb_outputs[0])
    assert all(len(stream) == count for stream in comb_outputs)

    result = []
    for n in range(count):
        sum_left = sum(stream[n][0] for stream in comb_outputs)
        sum_right = sum(stream[n][1] for stream in comb_outputs)
        # Python >> rounds toward negative infinity, matching signed SV >>>.
        result.append((sum_left >> 2, sum_right >> 2))

    return result


def all_pass_model(frames, delay, diffusion_u014):
    """Mirror all_pass_filter.sv including clipping v BEFORE feedforward.

        r[n] = RAM[ptr]
        v[n] = sat(x[n] + ((a*r[n]) >> 14))
        y[n] = sat(r[n] - ((a*v[n]) >> 14))
        RAM[ptr] = v[n]
    """
    assert 0 <= diffusion_u014 < UNITY
    assert delay > 0

    mem_left = [0] * delay
    mem_right = [0] * delay
    output = []

    for n, (left, right) in enumerate(frames):
        ptr = n % delay
        old_left = mem_left[ptr]
        old_right = mem_right[ptr]

        new_left = sat_clip(left + ((old_left * diffusion_u014) >> FRAC_BITS))
        new_right = sat_clip(right + ((old_right * diffusion_u014) >> FRAC_BITS))

        out_left = sat_clip(old_left - ((new_left * diffusion_u014) >> FRAC_BITS))
        out_right = sat_clip(old_right - ((new_right * diffusion_u014) >> FRAC_BITS))

        mem_left[ptr] = new_left
        mem_right[ptr] = new_right
        output.append((out_left, out_right))

    return output


def wet_dry_model(dry_frames, wet_frames, wet_u014):
    assert len(dry_frames) == len(wet_frames)
    result = []

    for (dry_left, dry_right), (wet_left, wet_right) in zip(dry_frames, wet_frames):
        out_left = sat_clip(
            dry_left + (((wet_left - dry_left) * wet_u014) >> FRAC_BITS)
        )
        out_right = sat_clip(
            dry_right + (((wet_right - dry_right) * wet_u014) >> FRAC_BITS)
        )
        result.append((out_left, out_right))

    return result


def reverb_model(frames, *, bypass, room_size, decay_cfg, diffusion, wet):
    if bypass:
        return list(frames)

    a = convert_u014(diffusion)
    w = convert_u014(wet)

    four_combs = [
        comb_filter_model(frames, comb_id, room_size, decay_cfg)
        for comb_id in range(4)
    ]
    normalized = normalize_comb_outputs(four_combs)
    ap0 = all_pass_model(normalized, ALL_PASS_DELAYS[0], a)
    ap1 = all_pass_model(ap0, ALL_PASS_DELAYS[1], a)
    return wet_dry_model(frames, ap1, w)


def assertion_frames(actual_frames, expected_frames):
    assert len(actual_frames) == len(expected_frames), (
        f"Frame count: expected={len(expected_frames)}, actual={len(actual_frames)}"
    )

    for n, (actual, expected) in enumerate(zip(actual_frames, expected_frames)):
        assert actual == expected, (
            f"Frame {n}: expected L/R={expected}, actual L/R={actual}"
        )


def clock_start(dut, dsp_period=DSP_CLK, i2s_period=I2S_CLK):
    cocotb.start_soon(Clock(dut.dsp_clk, dsp_period, unit="ns").start())
    cocotb.start_soon(Clock(dut.i2s_clk, i2s_period, unit="ns").start())
    cocotb.start_soon(generate_ws(dut))


async def generate_ws(dut):
    while True:
        dut.ws.value = 1
        for _ in range(BIT_SLOT):
            await FallingEdge(dut.i2s_clk)
        dut.ws.value = 0
        for _ in range(BIT_SLOT):
            await FallingEdge(dut.i2s_clk)


async def configuration(dut, *, bypass, room_size, decay_cfg, diffusion, wet):
    dut.bypass.value = int(bypass)
    dut.room_i.value = int(room_size)
    dut.decay_60.value = int(decay_cfg)
    dut.diffusion_i.value = convert_u014(diffusion)
    dut.w_i.value = convert_u014(wet)


async def reset(dut):
    await FallingEdge(dut.i2s_clk)
    dut.i2s_reset.value = 1
    await FallingEdge(dut.dsp_clk)
    dut.dsp_reset.value = 1
    dut.sd_i.value = 0

    for _ in range(10):
        await RisingEdge(dut.i2s_clk)

    await FallingEdge(dut.i2s_clk)
    dut.i2s_reset.value = 0
    await FallingEdge(dut.dsp_clk)
    dut.dsp_reset.value = 0

    # Largest comb clears 2623 addresses, at one address / DSP cycle.
    for _ in range(4000):
        await FallingEdge(dut.dsp_clk)
        if int(dut.chain_ready_o.value):
            break
    else:
        raise AssertionError("Timeout waiting for chain_ready_o")

    while int(dut.rx_ready_o.value) == 0:
        await FallingEdge(dut.i2s_clk)

    await FallingEdge(dut.ws)
    await FallingEdge(dut.ws)

    for _ in range(8):
        await RisingEdge(dut.i2s_clk)

    assert int(dut.rx_ready_o.value) == 1, (
        "RX side was not enabled after chain initialization"
    )


async def send_i2s_word(dut, audio, width=WIDTH):
    await RisingEdge(dut.i2s_clk)
    audio = int_to_two_complement(audio, width)
    for bit_index in range(width - 1, -1, -1):
        await FallingEdge(dut.i2s_clk)
        dut.sd_i.value = (audio >> bit_index) & 1


async def send_i2s_frame(dut, left_audio, right_audio):
    await FallingEdge(dut.ws)
    await send_i2s_word(dut, left_audio)
    await RisingEdge(dut.ws)
    await send_i2s_word(dut, right_audio)


async def send_frames(dut, input_frames):
    for left, right in input_frames:
        await send_i2s_frame(dut, left, right)


async def receive_i2s_word(dut, width=WIDTH):
    await FallingEdge(dut.i2s_clk)
    await FallingEdge(dut.i2s_clk)

    result = 0
    for bit_index in range(width - 1, -1, -1):
        await RisingEdge(dut.i2s_clk)
        result |= int(dut.sd_o.value) << bit_index
    return result


async def receive_i2s_frame(dut):
    await FallingEdge(dut.ws)
    left = await receive_i2s_word(dut)
    await RisingEdge(dut.ws)
    right = await receive_i2s_word(dut)
    return (
        two_complement_to_int(left),
        two_complement_to_int(right),
    )


async def receive_frames(dut, number_of_frames):
    received = []
    for _ in range(number_of_frames):
        received.append(await receive_i2s_frame(dut))
    return received


async def test_input(dut, input_frames, *, bypass, room_size, decay_cfg,
                     diffusion, wet):
    expected = reverb_model(
        input_frames,
        bypass=bypass,
        room_size=room_size,
        decay_cfg=decay_cfg,
        diffusion=diffusion,
        wet=wet,
    )
    LATENCY = 1 if bypass else 2
    sender = cocotb.start_soon(send_frames(dut, input_frames))
    receiver = cocotb.start_soon(
        receive_frames(dut, len(input_frames) + LATENCY + 6)
    )

    await sender
    actual_stream = await receiver

    for frame_index, expected_frame in enumerate(expected):
        actual_frame = actual_stream[LATENCY + frame_index]
        assert actual_frame == expected_frame, (
            f"Frame {frame_index} (captured index {LATENCY + frame_index}): "
            f"expected L/R={expected_frame}, actual L/R={actual_frame}; "
            f"first captured frames={actual_stream[:min(5, len(actual_stream))]}"
        )

    assert int(dut.rx_fifo_overflow.value) == 0, "RX FIFO overflow detected"


async def run_config(dut, input_frames, *, bypass=False, room_size=0,
                     decay_cfg=25, diffusion=0.5, wet=0.5):
    config = dict(
        bypass=bypass, room_size=room_size, decay_cfg=decay_cfg,
        diffusion=diffusion, wet=wet,
    )
    await configuration(dut, **config)
    clock_start(dut)
    await reset(dut)
    await test_input(dut, input_frames, **config)


@cocotb.test()
async def test_bypass(dut):
    frames = [
        (1000, -500), (2000, -1000), (-3000, 1500), (0, 0),
        (MAX_24, MIN_24), (-1, 1),
    ] * 3
    await run_config(
        dut, frames, bypass=True, room_size=2, decay_cfg=50,
        diffusion=0.75, wet=0.75,
    )


@cocotb.test()
async def test_dry_only(dut):
    rng = pyrandom.Random(1)
    frames = [
        (rng.randint(MIN_24, MAX_24), rng.randint(MIN_24, MAX_24))
        for _ in range(240)
    ]
    await run_config(
        dut, frames, room_size=1, decay_cfg=25, diffusion=0.5, wet=0.0,
    )


@cocotb.test()
async def test_impulse_reverb_tail(dut):
    frames = [(160000, -64000)] + [(0, 0)] * 2550
    await run_config(
        dut, frames, room_size=0, decay_cfg=25, diffusion=0.5, wet=0.75,
    )


@cocotb.test()
async def test_random_frames(dut):
    rng = pyrandom.Random(42)
    frames = [
        (rng.randint(-100000, 100000), rng.randint(-100000, 100000))
        for _ in range(1600)
    ]
    await run_config(
        dut, frames, room_size=1, decay_cfg=35, diffusion=0.5, wet=0.65,
    )


@cocotb.test()
async def test_saturation(dut):
    frames = [(MAX_24, MIN_24)] * 1650
    await run_config(
        dut, frames, room_size=0, decay_cfg=50, diffusion=0.75, wet=0.75,
    )


@cocotb.test()
async def test_chain_ready(dut):
    config = dict(
        bypass=False, room_size=0, decay_cfg=25,
        diffusion=0.5, wet=0.5,
    )
    await configuration(dut, **config)
    clock_start(dut)

    await FallingEdge(dut.i2s_clk)
    dut.i2s_reset.value = 1
    await FallingEdge(dut.dsp_clk)
    dut.dsp_reset.value = 1
    dut.sd_i.value = 0
    for _ in range(10):
        await RisingEdge(dut.i2s_clk)
    await FallingEdge(dut.i2s_clk)
    dut.i2s_reset.value = 0
    await FallingEdge(dut.dsp_clk)
    dut.dsp_reset.value = 0

    invalid_sender = cocotb.start_soon(send_frames(dut, [(1234, -5678)]))
    while not invalid_sender.done():
        await FallingEdge(dut.i2s_clk)
        assert int(dut.rx_ready_o.value) == 0, (
            "I2S RX was enabled before reverb initialization finished"
        )
        assert int(dut.fifo1_wr_en.value) == 0, (
            "RX FIFO accepted audio before chain was ready"
        )
    await invalid_sender

    for _ in range(4000):
        await FallingEdge(dut.dsp_clk)
        if int(dut.chain_ready_o.value):
            break
    else:
        raise AssertionError("chain_ready_o never asserted")

    for _ in range(8):
        await RisingEdge(dut.i2s_clk)
    assert int(dut.rx_ready_o.value) == 1

    frames = [(i + 100, -(i + 300)) for i in range(40)]
    await test_input(dut, frames, **config)


@cocotb.test()
async def test_reset_mid_stream(dut):
    config = dict(
        bypass=False, room_size=0, decay_cfg=25,
        diffusion=0.5, wet=0.75,
    )
    await configuration(dut, **config)
    clock_start(dut)
    await reset(dut)

    # Start an active I2S stream, reset while it is still running.
    before = [(200000, -200000)] + [(i, -i) for i in range(1, 100)]
    sending = cocotb.start_soon(send_frames(dut, before))
    for _ in range(18):
        await FallingEdge(dut.ws)
    sending.kill()

    await reset(dut)

    after = [(80000, -40000)] + [(0, 0)] * 1450
    await test_input(dut, after, **config)
