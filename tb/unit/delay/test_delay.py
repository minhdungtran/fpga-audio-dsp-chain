import random as pyrandom
import numpy as np
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

WIDTH = 24
FRAC_BITS = 14
UNITY = 1 << FRAC_BITS
SAMPLE_F = 48000
MAX_DELAY_MS = 500
C_BUFFER_SIZE = MAX_DELAY_MS * SAMPLE_F//1000
MAX_24 = (1 << (WIDTH - 1)) - 1   #  8388607
MIN_24 = -(1 << (WIDTH - 1))      # -8388608

def mask(width):
    return (1<<width) -1

def two__compliment_to_int(sample, width):
    sample &= mask(width)
    # check signed bit
    if sample & (1 << (width-1) ):
        sample = sample - (1<<width)
    return sample

def int_to_two_compliment(value, width):
    return value & mask(width)

def sat_clip(value, width=WIDTH):
    if value > MAX_24:
        return MAX_24
    if value < MIN_24:
        return MIN_24
    return value

def convert_014(wet, feedback):
    return (round(wet*UNITY), round(feedback*UNITY))

def delay_model(frames, delay_ms, w, g, bypass):
    assert 0 <= w < (1 << FRAC_BITS)
    assert 0 <= g < (1 << FRAC_BITS)

    delay_ms = min(delay_ms, MAX_DELAY_MS)
    buffer_size = delay_ms * SAMPLE_F//1000
    buffer_left = np.zeros(buffer_size, dtype=np.int64)
    buffer_right = np.zeros(buffer_size, dtype=np.int64)
    output = []

    if bypass or buffer_size == 0:
        return frames

    for i in range(len(frames)):
        ld, rd = frames[i]
        ptr = i % buffer_size
        old_sample_left = buffer_left[ptr]
        old_sample_right = buffer_right[ptr]

        buffer_left[ptr] = sat_clip(ld + ((old_sample_left*g)>>FRAC_BITS), WIDTH)
        buffer_right[ptr] = sat_clip(rd + ((old_sample_right*g)>>FRAC_BITS), WIDTH)

        output_left = sat_clip(((UNITY-w)*ld + w*old_sample_left)>>FRAC_BITS, WIDTH)
        output_right = sat_clip(((UNITY-w)*rd + w*old_sample_right)>>FRAC_BITS, WIDTH)
        output.append((output_left,output_right))

    return output

def assertion_frames(actual_frames, expected_frames):
    assert len(actual_frames) == len(expected_frames)

    for frame_number, (actual_frame, expected_frame) in enumerate(
        zip(actual_frames, expected_frames)
    ):
        assert actual_frame == expected_frame, (
            f"Frame {frame_number}: "
            f"expected={expected_frame}, actual={actual_frame}"
        )

async def reset(dut):
    await RisingEdge(dut.dsp_clk)
    dut.reset.value = 1

    await RisingEdge(dut.dsp_clk)
    await FallingEdge(dut.dsp_clk)
    dut.reset.value = 0

    while int(dut.ready_o.value) == 0:
        await RisingEdge(dut.dsp_clk)

async def configuration(dut, bypass, wet, feedback, delay):
    dut.bypass.value = int(bypass)
    dut.delay_i.value = delay
    dut.fb_i.value = feedback
    dut.w_i.value = wet

def clock_set_up(dut, time): 
    cocotb.start_soon(Clock(dut.dsp_clk, time, units="ns").start())

async def send_input(ld,rd,dut):
    await FallingEdge(dut.dsp_clk)

    dut.ld_i.value = int_to_two_compliment(ld, WIDTH)
    dut.rd_i.value = int_to_two_compliment(rd, WIDTH)
    dut.valid_i.value = 1
    
    while True:
        ready = int(dut.ready_o.value)
        await RisingEdge(dut.dsp_clk)
        if ready:
            break
    await FallingEdge(dut.dsp_clk)
    dut.valid_i.value = 0

async def receive_output(dut):
    while True:
        if int(dut.valid_o.value):
            out_ld = two__compliment_to_int(int(dut.ld_o.value), WIDTH)
            out_rd = two__compliment_to_int(int(dut.rd_o.value), WIDTH) 
            return(out_ld, out_rd)
        await FallingEdge(dut.dsp_clk)

async def test_with_configuration(dut, bypass, wet, feedback, delay, frames):
    u014_wet, u014_feedback = convert_014(wet, feedback)
    clock_set_up(dut, 10)
    await configuration(dut, bypass, u014_wet, u014_feedback, delay)
    await reset(dut)
    dut.ready_i.value = 1 # For these tests, we assume the next component is ready to receive data
    actual_output = []
    for frame in frames:
        ld, rd = frame
        await send_input(ld,rd,dut)
        output_frame = await receive_output(dut)
        actual_output.append(output_frame)
    expected_output = delay_model(frames, delay, u014_wet, u014_feedback, bypass)
    assertion_frames(actual_output, expected_output)

        
@cocotb.test()
async def test_bypass_on(dut):
    frames = [
        (1000, -500),
        (2000, -1000),
        (-3000, 1500),
        (0, 0),
        (MAX_24, MIN_24),
    ]
    await test_with_configuration(dut, bypass=True, wet=0.5, feedback=0.5, delay=100, frames=frames)


@cocotb.test()
async def test_zero_delay(dut):
    frames = [
        (1000, -500),
        (-2000, 3000),
        (MAX_24, MIN_24),
        (0, 0),
    ]

    await test_with_configuration(dut, bypass=False, wet=0.5, feedback=0.5, delay=0, frames=frames)

@cocotb.test()
async def test_dry_only(dut):
    frames = [
        (1000, -1000),
        (2000, -2000),
        (3000, -3000),
        (0, 0),
    ] * 30

    await test_with_configuration(dut, bypass=False, wet=0.0, feedback=0.5, delay=2, frames=frames)


# TEST 4: Single delayed echo, no feedback
@cocotb.test()
async def test_single_echo(dut):
    frames = [(12000, 0)] + [(0, 0)] * 250

    await test_with_configuration(dut, bypass=False, wet=0.5, feedback=0.0, delay=2, frames=frames)

@cocotb.test()
async def test_feedback_decay(dut):
    frames = [(16000, 0)] + [(0, 0)] * 400

    await test_with_configuration(dut, bypass=False, wet=0.5, feedback=0.5, delay=2, frames=frames)


@cocotb.test()
async def test_stereo_independence(dut):
    frames = [
        (12000, -8000),
    ] + [(0, 0)] * 300

    await test_with_configuration(dut, bypass=False, wet=0.5, feedback=0.5, delay=2, frames=frames)


@cocotb.test()
async def test_negative_samples(dut):
    frames = [
        (-1, 1),
        (-3, 3),
        (-101, 101),
        (-1001, 1001),
    ] + [(0, 0)] * 200

    await test_with_configuration(dut, bypass=False, wet=0.25, feedback=0.5, delay=2, frames=frames)

@cocotb.test()
async def test_saturation(dut):
    frames = [(MAX_24, MIN_24)] * 300

    await test_with_configuration(dut, bypass=False, wet=0.5, feedback=0.99, delay=2, frames=frames)

@cocotb.test()
async def test_max_delay(dut):
    frames = [(16000, -16000)] + [(0, 0)] * 24010

    await test_with_configuration(dut, bypass=False, wet=0.5, feedback=0.5, delay=700, frames=frames)

@cocotb.test()
async def test_handshake(dut):
    wet, feedback = 0.5, 0.5
    delay = 100
    u014_wet, u014_feedback = convert_014(wet, feedback)
    
    clock_set_up(dut, 10)
    await configuration(dut, bypass=False, wet=u014_wet, feedback=u014_feedback, delay=delay)

    await reset(dut)
    dut.ready_i.value = 0 # we assume now the next component is not ready to receive samples
    dut.valid_i.value = 0

    await send_input(0, 10, dut)

    output = await receive_output(dut)

    assert int(dut.valid_o.value) == 1, "When output is ready, the valid signal should be high"

    for _ in range(10):
        await FallingEdge(dut.dsp_clk)
        assert int(dut.valid_o.value) == 1, "When output is ready, the valid signal should be high"
        assert (
            two__compliment_to_int(int(dut.ld_o.value), WIDTH),
            two__compliment_to_int(int(dut.rd_o.value), WIDTH)
        ) == output

    dut.ready_i.value = 1 # Now allow for sample to flow
    await RisingEdge(dut.dsp_clk) 
    await RisingEdge(dut.dsp_clk)
    assert int(dut.valid_o.value) == 0, "After the current data is sent, the valid signal should be low"




    
  
    
        


        




