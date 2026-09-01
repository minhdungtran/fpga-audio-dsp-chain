import cocotb
import random
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

SCK_PERIOD_NS = 10
WIDTH = 24
SLOT_WIDTH = 32

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

    for _ in range (len(nbr_of_frames)+8):
        left_out, right_out = await receive_i2s_frame(dut)
        output_frames.append((left_out, right_out))

    return output_frames

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

    await FallingEdge(dut.shared_WS) # frame synchronization
    send = cocotb.start_soon(send_frames(dut, input_frames))
    receive = cocotb.start_soon(receive_frames(dut, input_frames))

    await send
    output_frames = await receive
    expected_index = 0
    
    for out_left, out_right in output_frames:
        if expected_index < len(input_frames):
          if input_frames[expected_index] == (out_left, out_right):
            expected_index +=1
    
    assert expected_index == len(input_frames), (
        f"Only matched {expected_index}/{len(input_frames)} sequential frames.\n"
        f"Captured: {[tuple(hex(x) for x in frame) for frame in output_frames]}"
)
    
@cocotb.test()
async def multiple_random(dut):

    cocotb.start_soon(Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(generated_WS(dut))
    
    await reset(dut)
    
    random.seed(1)
    input_frames = []
    for _ in range(100):
        left = random.getrandbits(24)
        right = random.getrandbits(24)
        input_frames.append((left,right))

    await FallingEdge(dut.shared_WS) # frame synchronization
    send = cocotb.start_soon(send_frames(dut, input_frames))
    receive = cocotb.start_soon(receive_frames(dut, input_frames))

    await send
    output_frames = await receive
    expected_index = 0
    
    for out_left, out_right in output_frames:
        if expected_index < len(input_frames):
          if input_frames[expected_index] == (out_left, out_right):
            expected_index +=1
    
    assert expected_index == len(input_frames), (
        f"Only matched {expected_index}/{len(input_frames)} sequential frames.\n"
        f"Captured: {[tuple(hex(x) for x in frame) for frame in output_frames]}"
    )
    
@cocotb.test()
async def output_after_reset(dut):

    cocotb.start_soon(Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(generated_WS(dut))
    
    await reset(dut)

    for _ in range(100):
        await FallingEdge(dut.shared_sck)
        assert dut.output_SD.value == 0,(
        f"Ouputs should be zero after reset\n"
        f"Expected: 0. Got {dut.output_SD.value}"
    )

@cocotb.test()
async def reset_mid_stream(dut):
    

    cocotb.start_soon(Clock(dut.shared_sck, SCK_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(generated_WS(dut))
    
    await reset(dut)

    initial_frames = [
        (0x000210, 0x000123),
        (0x000323, 0x000886),
        (0x000555, 0x000777),
        (0x001000, 0xFFF000),
    ]
    
    second_frames = [
        (0x000555, 0x000777),
        (0x001000, 0xFFF000),
        (0x400000, 0xC00000),
    ]

    await FallingEdge(dut.shared_WS) 
    init_send = cocotb.start_soon(send_frames(dut, initial_frames))

    #reset in the middle of a frame
    await RisingEdge(dut.shared_WS)
    await reset(dut)
    init_send.kill()
    
    await FallingEdge(dut.shared_WS)
    send = cocotb.start_soon(send_frames(dut, second_frames))
    receive = cocotb.start_soon(receive_frames(dut, second_frames))

    await send
    output_frames = await receive
    expected_index = 0
    
    for out_left, out_right in output_frames:
        if expected_index < len(second_frames):
          if second_frames[expected_index] == (out_left, out_right):
            expected_index +=1
    
    assert expected_index == len(second_frames), (
        f"Only matched {expected_index}/{len(second_frames)} sequential frames.\n"
        f"Captured: {[tuple(hex(x) for x in frame) for frame in output_frames]}"
    )













  



