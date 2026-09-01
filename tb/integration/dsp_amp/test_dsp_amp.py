"""
Frame latency note:
The DSP amplifier output appears some number of I2S frames after the input.
Find this latency by capturing extra output frames until the expected sequence
appears, then use that value as `LATENCY` for exact comparisons.
"""
import cocotb
import random
import random as pyrandom
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

SCK_PERIOD_NS = 10
WIDTH = 24
SLOT_WIDTH = 32
LATENCY = 1

FRAC_BITS = 14
GAIN_LENGTH = 16
MAX_24 = (1 << (WIDTH - 1)) - 1   #  8388607
MIN_24 = -(1 << (WIDTH - 1))      # -8388608

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

def unsigned_to_signed_gain(sample, gain):
    return int_to_two_compliment(
        amp_model(two__compliment_to_int(sample, WIDTH), gain, FRAC_BITS, WIDTH), WIDTH)



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
async def basic(dut):

    cocotb.start_soon(Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(generated_WS(dut))
    
    await reset(dut)

    input_frames = [
    (0x000000, 0x000000),  # silence
    (0xFFFFFF, 0xFFFFFF),  # all ones
    (0xAAAAAA, 0x555555),  # alternating bits
    (0x555555, 0xAAAAAA),  # opposite alternating bits
    (0x800000, 0x7FFFFF),  # signed boundary
    (0x000001, 0x000001),  # LSB only
    ]

    G = 8192
    dut.shared_G.value = int_to_two_compliment(G, GAIN_LENGTH)
     
    expected_frames = []
    for left, right in input_frames:
        expected_left_bit = unsigned_to_signed_gain(left, G)
        expected_right_bit = unsigned_to_signed_gain(right, G)
        expected_frames.append((expected_left_bit,expected_right_bit))


    await FallingEdge(dut.shared_WS) # frame synchronization
    send = cocotb.start_soon(send_frames(dut, input_frames))
    receive = cocotb.start_soon(receive_frames(dut, len(input_frames) + LATENCY))

    await send
    output_frames = await receive
    actual_frames = output_frames[LATENCY : LATENCY + len(input_frames)]
    expected_index = 0
    
    
    assert actual_frames == expected_frames, (
      f"\nFrame comparison failed\n"
      f"Matched: {expected_index}/{len(expected_frames)} sequential frames\n\n"
      f"{format_frame_list('Expected:', expected_frames)}\n\n"
      f"{format_frame_list('Captured:', actual_frames)}"
)
    
@cocotb.test()
async def multiple_random(dut):

    cocotb.start_soon(Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(generated_WS(dut))
    
    await reset(dut)
    
    input_frames = []
    for _ in range(100):
        left = int_to_two_compliment(pyrandom.randint(MIN_24,MAX_24), WIDTH)
        right = int_to_two_compliment(pyrandom.randint(MIN_24,MAX_24), WIDTH)
        input_frames.append((left,right))

    G = 9000
    dut.shared_G.value = int_to_two_compliment(G, GAIN_LENGTH)

    expected_frames = []
    for left, right in input_frames:
        expected_left_bit = unsigned_to_signed_gain(left, G)
        expected_right_bit = unsigned_to_signed_gain(right, G)
        expected_frames.append((expected_left_bit,expected_right_bit))

    await FallingEdge(dut.shared_WS) # frame synchronization
    send = cocotb.start_soon(send_frames(dut, input_frames))
    receive = cocotb.start_soon(receive_frames(dut, len(input_frames)+LATENCY))

    await send
    output_frames = await receive
    actual_frame = output_frames[LATENCY: LATENCY + len(input_frames)]
    expected_index = 0
    
    for out_left, out_right in output_frames:
        if expected_index < len(input_frames):
          if expected_frames[expected_index] == (out_left, out_right):
            expected_index +=1
    
    assert actual_frame == expected_frames, (
      f"\nFrame comparison failed\n"
      f"Matched: {expected_index}/{len(expected_frames)} sequential frames\n\n"
      f"{format_frame_list('Expected:', expected_frames)}\n\n"
      f"{format_frame_list('Captured:', output_frames)}"
)
    
        
@cocotb.test()
async def g_change_between_frames(dut):

    cocotb.start_soon(Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(generated_WS(dut))
    
    await reset(dut)

    input_frames = [
        (0x000210, 0x000123, 8196),
        (0x000323, 0x000886, 10000),
        (0x000555, 0x000777, 16384),
        (0x001000, 0xFFF000, -16384),
        (0x400000, 0xC00000, 32767),
 ]
        
    expected_frames = []

    await FallingEdge(dut.shared_WS)

    async def send_frames_with_different_gains():
        for left, right, gain in input_frames:

            left_exp = unsigned_to_signed_gain(left, gain)
            right_exp = unsigned_to_signed_gain(right, gain)
            expected_frames.append((left_exp,right_exp))

            await send_i2s_frame(dut, left, right)
            dut.shared_G.value = int_to_two_compliment(gain, GAIN_LENGTH)

    
    send = cocotb.start_soon(send_frames_with_different_gains())
    receive = cocotb.start_soon(receive_frames(dut, len(input_frames) + LATENCY))

    await send
    output_frames = await receive
    actual_frames = output_frames[LATENCY: len(input_frames)+LATENCY]

    assert actual_frames == expected_frames, (
        f"\nGain-change frame comparison failed\n"
        f"{format_frame_list('Expected:', expected_frames)}\n\n"
        f"{format_frame_list('Captured:', actual_frames)}"
    )
    

    














  



