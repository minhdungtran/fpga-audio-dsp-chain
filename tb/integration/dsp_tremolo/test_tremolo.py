import random
import math
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

SCK_PERIOD_NS = 10
WIDTH = 24
SLOT_WIDTH = 32
FRAC_BITS = 14
GAIN_LENGTH = 16
MAX_24 = (1 << (WIDTH - 1)) - 1   #  8388607
MIN_24 = -(1 << (WIDTH - 1))      # -8388608
LATENCY = 2

async def reset(dut):
    
    dut.shared_reset.value = 1
    dut.shared_SD.value = 0

    for _ in range(3):
        await RisingEdge(dut.shared_sck)

    dut.shared_reset.value = 0
    await RisingEdge(dut.shared_sck)


async def generated_WS(dut):

    while True:
        dut.shared_WS.value = 1
        for _ in range(SLOT_WIDTH):
            await FallingEdge(dut.shared_sck)

        dut.shared_WS.value = 0
        for _ in range(SLOT_WIDTH):
            await FallingEdge(dut.shared_sck)

async def send_i2s_word(dut, audio, width = WIDTH): 

    await RisingEdge(dut.shared_sck) # 1 clock delay

    for i in range(width-1,-1,-1):
        await FallingEdge(dut.shared_sck)
        bit = (audio >> i) & 1
        dut.shared_SD.value = bit

async def send_i2s_frame(dut, left_audio, right_audio):
    await FallingEdge(dut.shared_WS)
    await send_i2s_word(dut, left_audio, WIDTH)
    await RisingEdge(dut.shared_WS)
    await send_i2s_word(dut, right_audio, WIDTH)

async def send_frames(dut, input_frames):
    for left, right in input_frames:
        await send_i2s_frame(dut, left, right)

async def receive_i2s_word(dut, width = WIDTH):  

    await FallingEdge(dut.shared_sck) # 1 cycle delay
    await FallingEdge(dut.shared_sck)

    output = 0

    for i in range(width-1,-1,-1):
        await RisingEdge(dut.shared_sck)
        bit = int(dut.output_SD.value)
        output = output | (bit << i)
        
    return output

async def receive_i2s_frame(dut):
    await FallingEdge(dut.shared_WS)
    left = await receive_i2s_word(dut, WIDTH)
    await RisingEdge(dut.shared_WS)
    right = await receive_i2s_word(dut, WIDTH)
    return left, right

async def receive_frames(dut, nbr_of_frames):
    output_frames = []

    for _ in range (nbr_of_frames):
        left_out, right_out = await receive_i2s_frame(dut)
        output_frames.append((left_out, right_out))

    return output_frames

def two__compliment_to_int(sample, width):
    sample &= ((1<<width) - 1)
    # check signed bit
    if sample & (1 << (width-1) ):
        sample = sample - (1<<width)
    return sample

def int_to_two_compliment(value, width):
    return value & (((1 << width) - 1))

def unsigned_to_signed_gain(sample, gain):
    return int_to_two_compliment(
        amp_model(two__compliment_to_int(sample, WIDTH), gain, FRAC_BITS, WIDTH), WIDTH)

def tremolo_config(dut, control_rate, control_depth):
    dut.shared_control_rate.value = control_rate
    dut.shared_control_depth.value = control_depth 

def lfo_rom_value(address):
   to_rad = address*2*math.pi/256
   uni_polar = (math.sin(to_rad)+1)/2
   u014 = round(((1<<14)) * uni_polar)

   if u014 == 16384: 
      u014 = 16383
   return u014

def expected_gain(gain, address):
   mask = (1<<16) - 1
   G = (1<<14)- ((gain*int(lfo_rom_value(address)))>>14)
   return G & mask

def next_accumulator(current, control_rate):
    return (current + int(control_rate)) & 0xFFFF

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

def format_frame(frame, index=None):
    left, right = frame
    prefix = f"[{index:03d}] " if index is not None else ""
    return (
        f"{prefix}"
        f"L=0x{left & 0xFFFFFF:06X} ({two__compliment_to_int(left, WIDTH):9d})  "
        f"R=0x{right & 0xFFFFFF:06X} ({two__compliment_to_int(right, WIDTH):9d})"
    )


def format_frame_list(title, frames):
    lines = [title]
    lines.extend(format_frame(frame, i) for i, frame in enumerate(frames))
    return "\n".join(lines)


@cocotb.test()
async def multiple_random(dut):

    cocotb.start_soon(Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(generated_WS(dut))

    tremolo_rate = 7
    tremolo_depth = 8192
    tremolo_config(dut, tremolo_rate, tremolo_depth)
    expected_accumulator = 0
 

    await reset(dut)

    random.seed(1)
    input_frames = []

    for _ in range(1000):
        left = random.getrandbits(24)
        right = random.getrandbits(24)

        # Calculate the gain for each frame
        current = (expected_accumulator >> 8) & 0xFF
        expected_accumulator = next_accumulator(expected_accumulator, dut.shared_control_rate.value)
        gain = expected_gain(tremolo_depth, current)

        input_frames.append((left,right,gain))
    
    expected_frames=[]

    async def send_frames_with_different_gains():
        for left, right, gain in input_frames:

            left_exp = unsigned_to_signed_gain(left, gain)
            right_exp = unsigned_to_signed_gain(right, gain)
            expected_frames.append((left_exp,right_exp))

            await send_i2s_frame(dut, left, right)

    await FallingEdge(dut.shared_WS) # frame synchronization
    send = cocotb.start_soon(send_frames_with_different_gains())
    receive = cocotb.start_soon(receive_frames(dut, len(input_frames) + LATENCY))

    await send
    output_frames = await receive
    
    actual_frames = output_frames[LATENCY: len(input_frames)+LATENCY]

    assert actual_frames == expected_frames, (
        f"{format_frame_list('Expected:', expected_frames)}\n\n"
        f"{format_frame_list('Captured:', actual_frames)}"
    )
    
    
