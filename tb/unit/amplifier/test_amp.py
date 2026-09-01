import random as pyrandom
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

WIDTH = 24
FRAC_BITS = 14
GAIN_LENGTH = 16

MAX_24 = (1 << (WIDTH - 1)) - 1   #  8388607
MIN_24 = -(1 << (WIDTH - 1))      # -8388608

async def reset(dut):
    dut.data_valid.value = 0
    dut.in_LD.value = 0
    dut.in_RD.value = 0
    dut.G.value = 0

    await RisingEdge(dut.sck)
    dut.reset.value = 1
    
    for _ in range(3):
        await RisingEdge(dut.sck)

    dut.reset.value = 0

async def pulse_samples(dut):
    dut.data_valid.value = 1
    await RisingEdge(dut.sck)
    dut.data_valid.value = 0

def sat_clip(value, width=24):
    if value > MAX_24:
        return MAX_24
    if value < MIN_24:
        return MIN_24
    return value

def amp_model(sample, gain, frac_bits= FRAC_BITS, width= WIDTH):
    product = sample * gain
    shifted = product >> frac_bits   
    return sat_clip(shifted, width)

def two__compliment_to_int(sample, width):
    sample &= ((1<<width) - 1)
    # check signed bit
    if sample & (1 << (width-1) ):
        sample = sample - (1<<width)
    return sample

def int_to_two_compliment(value, width):
    return value & (((1 << width) - 1))


@cocotb.test()
async def corner_case(dut):

    cocotb.start_soon(Clock(dut.sck, 10, units="ns").start())

    frames = [
    # left, right, gain
    (0, 0, 16384),                         # 1.0x silence
    (1000, 2000, 16384),                   # 1.0x normal positive
    (-1000, -2000, 16384),                 # 1.0x normal negative
    (1000, -1000, 8192),                   # 0.5x
    (MAX_24, MIN_24, 0),                   # mute
    (MAX_24, MIN_24, 16384),               # 1.0x limits
    (MAX_24, 5_000_000, 32767),            # positive saturation
    (MIN_24, -5_000_000, 32767),           # negative saturation
    (1000, -1000, -16384),                 # -1.0x phase inversion
    (MIN_24, -5_000_000, -16384),          # MIN * -1 saturation case
    (MAX_24, 5_000_000, -32768),           # -2.0x negative saturation
    (1, -1, 8192),                         # shift behavior corner case
]
    
    await reset(dut)

    for left, right, gain in frames:

        dut.in_LD.value = int_to_two_compliment(left, WIDTH)
        dut.in_RD.value = int_to_two_compliment(right, WIDTH)
        dut.G.value     = int_to_two_compliment(gain, 16)
        
        await pulse_samples(dut)

        # Amplifier assigned to do the multiplication
        await RisingEdge(dut.sck)
        # Amplifier assigned to do  the shifting
        await RisingEdge(dut.sck)
        # Amplifier assigned to check saturation
        await RisingEdge(dut.sck)
        # Getting result
        await RisingEdge(dut.sck)

        expected_left = amp_model(left, gain)
        expected_right = amp_model(right, gain)

        got_left = two__compliment_to_int(dut.out_LD.value.integer, WIDTH)
        got_right = two__compliment_to_int(dut.out_RD.value.integer, WIDTH)

        assert got_left == expected_left, (
            f"LD failed: in={left}, gain={gain}, got={got_left}, exp={expected_left}"
        )

        assert got_right == expected_right, (
            f"RD failed: in={right}, gain={gain}, got={got_right}, exp={expected_right}"
        )

@cocotb.test()
async def random_test(dut):

    cocotb.start_soon(Clock(dut.sck, 10, units="ns").start())
    
    frames = []

    for _ in range(1000):
        left = pyrandom.randint(MIN_24, MAX_24)
        right = pyrandom.randint(MIN_24, MAX_24)
        gain = pyrandom.randint(-32768, 32767)
        frames.append((left, right, gain))
    
    await reset(dut)

    for left, right, gain in frames:

        dut.in_LD.value = int_to_two_compliment(left, WIDTH)
        dut.in_RD.value = int_to_two_compliment(right, WIDTH)
        dut.G.value     = int_to_two_compliment(gain, GAIN_LENGTH)
        
        await pulse_samples(dut)


        # Amplifier assigned to do the multiplication
        await RisingEdge(dut.sck)
        # Amplifier assigned to do  the shifting
        await RisingEdge(dut.sck)
        # Amplifier assigned to check saturation
        await RisingEdge(dut.sck)
        # Getting result
        await RisingEdge(dut.sck)

        expected_left = amp_model(left, gain)
        expected_right = amp_model(right, gain)

        got_left = two__compliment_to_int(dut.out_LD.value.integer, WIDTH)
        got_right = two__compliment_to_int(dut.out_RD.value.integer, WIDTH)

        assert got_left == expected_left, (
            f"LD failed: in={left}, gain={gain}, got={got_left}, exp={expected_left}"
        )

        assert got_right == expected_right, (
            f"RD failed: in={right}, gain={gain}, got={got_right}, exp={expected_right}"
        )

@cocotb.test()
async def control(dut):
        
    cocotb.start_soon(Clock(dut.sck, 10, units="ns").start())

    await reset(dut)
    await pulse_samples(dut)

    # Amplifier assigned to do the multiplication
    await RisingEdge(dut.sck)
    assert dut.multiplication.value == 1, f"Supposed to be multiplication state"
    # Amplifier assigned to do  the shifting
    await RisingEdge(dut.sck)
    assert dut.shifting.value == 1, f"Supposed to be shifting state"
    # Amplifier assigned to check saturation
    await RisingEdge(dut.sck)
    assert dut.sat_check.value == 1, f"Supposed to be saturation check state"
    await RisingEdge(dut.sck)
    assert dut.data_ready.value == 1, f"Supposed to be ready state"

@cocotb.test()
async def no_valid_no_ready(dut):
    cocotb.start_soon(Clock(dut.sck, 10, units="ns").start())
    await reset(dut)

    dut.data_valid.value = 0

    for _ in range(10):
        await RisingEdge(dut.sck)
        assert dut.data_ready.value == 0, "data_ready should stay low when no input is valid"



