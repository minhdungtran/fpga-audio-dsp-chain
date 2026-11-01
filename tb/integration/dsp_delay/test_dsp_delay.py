import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer
import random as pyrandom
from pathlib import Path

DSP_CLK = 20
I2S_CLK = 325.52

BIT_SLOT = 32
WIDTH = 24
FRAC_BITS = 14

SAMPLE_F = 48
MAX_DELAY_MS = 500
C_BUFFER_SIZE = MAX_DELAY_MS * SAMPLE_F//1000

UNITY = 1 << FRAC_BITS
MAX_24 = (1 << (WIDTH - 1)) - 1   #  8388607
MIN_24 = -(1 << (WIDTH - 1))      # -8388608

LATENCY = 1


async def reset(dut):
    await FallingEdge(dut.i2s_clk)
    dut.i2s_reset.value = 1
    await FallingEdge(dut.dsp_clk)
    dut.dsp_reset.value = 1

    for _ in range(10):
        await RisingEdge(dut.i2s_clk)

    dut.i2s_reset.value = 0
    dut.dsp_reset.value = 0

    while int(dut.chain_ready_o.value) == 0:
        await RisingEdge(dut.dsp_clk)

    assert int(dut.chain_ready_o.value) == 1

async def generated_WS(dut):

    while True:
        dut.ws.value = 1
        for _ in range(BIT_SLOT):
            await FallingEdge(dut.i2s_clk)

        dut.ws.value = 0
        for _ in range(BIT_SLOT):
            await FallingEdge(dut.i2s_clk)

async def clock_start(dut, dsp_period, i2s_period):
  
  cocotb.start_soon(Clock(dut.dsp_clk, dsp_period, unit="ns").start())

  cocotb.start_soon(Clock(dut.i2s_clk, i2s_period, unit="ns").start())

  cocotb.start_soon(generated_WS(dut))

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
    buffer_size = delay_ms * SAMPLE_F
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
        diff_left = old_sample_left - ld
        diff_right = old_sample_right -rd

        output_left = sat_clip(ld + ((w*diff_left)>>FRAC_BITS), WIDTH)
        output_right = sat_clip(rd + ((w*diff_right)>>FRAC_BITS), WIDTH)
        output.append((output_left,output_right))

    return output

async def configuration(dut, bypass, wet, feedback, delay):
    dut.bypass.value = int(bypass)
    dut.delay_i.value = delay
    dut.fb_i.value = feedback
    dut.w_i.value = wet


async def send_i2s_word(dut, audio, width = WIDTH): 

    await RisingEdge(dut.i2s_clk) # 1 clock delay

    for i in range(width-1,-1,-1):
        await FallingEdge(dut.i2s_clk)
        bit = (audio >> i) & 1
        dut.sd_i.value = bit

async def send_i2s_frame(dut, left_audio, right_audio):
    await FallingEdge(dut.ws)
    await send_i2s_word(dut, left_audio, WIDTH)
    await RisingEdge(dut.ws)
    await send_i2s_word(dut, right_audio, WIDTH)

async def send_frames(dut, input_frames):
    for left, right in input_frames:
        await send_i2s_frame(dut, left, right)

async def receive_i2s_word(dut, width = WIDTH):  

    await FallingEdge(dut.i2s_clk) # 1 cycle delay
    await FallingEdge(dut.i2s_clk)

    output = 0

    for i in range(width-1,-1,-1):
        await RisingEdge(dut.i2s_clk)
        bit = int(dut.sd_o.value)
        output = output | (bit << i)
        
    return output

async def receive_i2s_frame(dut):
    await FallingEdge(dut.ws)
    left = await receive_i2s_word(dut, WIDTH)
    await RisingEdge(dut.ws)
    right = await receive_i2s_word(dut, WIDTH)
    return (two__compliment_to_int(left, WIDTH),
            two__compliment_to_int(right, WIDTH)
    )

async def receive_frames(dut, nbr_of_frames):
    output_frames = []

    for _ in range (nbr_of_frames):
        left_out, right_out = await receive_i2s_frame(dut)
        output_frames.append((left_out, right_out))

    return output_frames


async def test_input(dut, input_frames, delay_ms, w, g, bypass):
    w_014, g_014 = convert_014(w, g)

    send = cocotb.start_soon(send_frames(dut, input_frames))
    receive = cocotb.start_soon(receive_frames(dut, len(input_frames)+22))

    await send
    output_frames = await receive
    expected_output = delay_model(input_frames, delay_ms, w_014, g_014, bypass)
    expected_index = 0
    matches = []

    for output_index, output_frame in enumerate(output_frames):
        if expected_index < len(expected_output):
            if expected_output[expected_index] == output_frame:
                matches.append((expected_index, output_index))
                expected_index += 1
                
    # dut._log.info(f"Matches (expected, captured): {matches}")

    # for i, expected in enumerate(expected_output):
    #    dut._log.info(
    #         f"Expected[{i:02d}] = {expected}"
    #     )

    # for i, actual in enumerate(output_frames):
    #     dut._log.info(
    #         f"Actual[{i:02d}] = {actual}"
    #     )

    assert expected_index == len(input_frames)
    for i, expected in enumerate(expected_output):
        actual = output_frames[LATENCY + i]

        assert actual == expected, (
            f"Frame {i}: expected {expected}, got {actual}"
        )
    
@cocotb.test()
async def multiple_random(dut):

    delay_ms, w, g, bypass = 200, 0.5, 0.5, False
    w_014, g_014 = convert_014(w, g)
    await configuration(dut, bypass, w_014, g_014, delay_ms)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)
    
    await reset(dut)
        
    pyrandom.seed(1)
    input_frames = []
    for _ in range(500):
        left = two__compliment_to_int(pyrandom.getrandbits(24), WIDTH)
        right = two__compliment_to_int(pyrandom.getrandbits(24), WIDTH)
        input_frames.append((left,right))

    await test_input(dut, input_frames, delay_ms, w, g, bypass)
    
@cocotb.test()
async def chain_ready_test(dut):

    invalid_frames = [(i, i+100) for i in range(5)]
    valid_frames = [(i+100, i+300) for i in range(5)]

    delay_ms, w, g, bypass = 200, 0.5, 0.5, False
    w_014, g_014 = convert_014(w, g)
    await configuration(dut, bypass, w_014, g_014, delay_ms)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)

    await FallingEdge(dut.i2s_clk)
    dut.i2s_reset.value = 1
    await FallingEdge(dut.dsp_clk)
    dut.dsp_reset.value = 1

    for _ in range(10):
        await RisingEdge(dut.i2s_clk)

    dut.i2s_reset.value = 0
    dut.dsp_reset.value = 0

    send_invalid = cocotb.start_soon(send_frames(dut, invalid_frames))

    while not send_invalid.done():
        assert int(dut.rx_ready_o.value) == 0
        assert int(dut.fifo1_wr_en.value) == 0, (
            "RX FIFO accepted data before DSP initialization completed"
        )
        await RisingEdge(dut.i2s_clk)  

    while not int(dut.chain_ready_o.value):
        await RisingEdge(dut.dsp_clk)
    
    assert int(dut.chain_ready_o.value) == 1

    await test_input(dut, valid_frames, delay_ms, w, g, bypass)

@cocotb.test()
async def reset_mid_stream(dut):
    before_reset_frames = [(i, i+100) for i in range(100)]
    after_reset_frames = [(i+100, i+300) for i in range(100)]

    delay_ms, w, g, bypass = 200, 0.5, 0.5, False
    w_014, g_014 = convert_014(w, g)
    await configuration(dut, bypass, w_014, g_014, delay_ms)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)

    await reset(dut)

    send_before_reset = cocotb.start_soon(
        send_frames(dut, before_reset_frames)
    )
    for _ in range (200): 
        await RisingEdge(dut.dsp_clk)
    
    send_before_reset.kill()
    await reset(dut)

    await test_input(dut, after_reset_frames, delay_ms, w, g, bypass)



    
    













