import random
import math
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

SCK_PERIOD_NS = 10
WIDTH = 24

async def reset(dut):
    dut.reset.value = 1
    dut.data_valid.value = 0
    dut.control_rate.value = 0
    expected_accumulator = 0

    
    await RisingEdge(dut.sck)
    await RisingEdge(dut.sck)
    dut.reset.value = 0

    await RisingEdge(dut.sck)

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

async def pipeline_finish(dut):
   dut.data_valid.value =1
   await RisingEdge(dut.sck)
   dut.data_valid.value = 0
   # Multiplication
   await RisingEdge(dut.sck)
   # Shifting
   await RisingEdge(dut.sck)
   # Subtract
   await RisingEdge(dut.sck)
   # Data ready
   await RisingEdge(dut.sck)
   

@cocotb.test()
async def adding_accumulation(dut):
   
   cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())

   await reset(dut)

   expected_accumulator = 0
   dut.control_rate.value = 255
   dut.data_valid.value = 0
   mask = (1<<16) - 1

   await RisingEdge(dut.sck)
   assert dut.accumulator.value == 0,(
     f"accumulator value should stay the same"
    )
   for _ in range(500):
     dut.data_valid.value = 1
     await RisingEdge(dut.sck)
     dut.data_valid.value = 0
     await RisingEdge(dut.sck)
     expected_accumulator = next_accumulator(expected_accumulator, 255) 
     assert dut.accumulator.value == expected_accumulator,(
       f"Got: {hex(dut.accumulator.value)}. Expected: {hex(expected_accumulator)}"
     )

@cocotb.test()
async def sample_alignment(dut):
   cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())
   expected_accumulator = 0

   dut.in_LD.value = 0x234000
   dut.in_RD.value = 0x000123
   await pipeline_finish(dut)

   assert int(dut.data_ready.value) == 1,(
      f"Data is supposed to be ready\n"
      f"Got: {dut.data_ready.value}"
   )
   assert dut.out_LD.value == dut.in_LD.value, (
      f"LD supposed arrived"
   )
   assert dut.out_RD.value == dut.in_RD.value, (
      f"RD supposed arrived"
   )

@cocotb.test()
async def gain_calculation(dut):
   cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())
   await reset(dut)
   
   expected_accumulator = 0
   dut.control_rate.value = 0x4000
   depth = 0x2000
   dut.control_depth.value = depth

   for _ in range(4):
      current = (expected_accumulator >> 8) & 0xFF
      
      await pipeline_finish(dut)

      expected_accumulator = next_accumulator(expected_accumulator, dut.control_rate.value)

      expected_result = expected_gain(depth, current)

      assert dut.tremolo_gain.value == expected_result, (
         f"Got: {int(dut.tremolo_gain.value)}. Expected: {int(expected_result)}"
      )
   
   await reset(dut)
   expected_accumulator = 0
   dut.control_rate.value = 0x4000
   depth = 0
   dut.control_depth.value = depth

   for _ in range(4):
      current = (expected_accumulator >> 8) & 0xFF
      
      await pipeline_finish(dut)

      expected_accumulator = next_accumulator(expected_accumulator, dut.control_rate.value)

      expected_result = expected_gain(depth, current)

      assert dut.tremolo_gain.value == expected_result, (
         f"Got: {int(dut.tremolo_gain.value)}. Expected: {int(expected_result)}"
      )

   await reset(dut)
   dut.control_rate.value = 0x0032
   depth = 0x2710
   dut.control_depth.value = depth

   for _ in range(4):
      current = (expected_accumulator >> 8) & 0xFF
      
      await pipeline_finish(dut)

      expected_accumulator = next_accumulator(expected_accumulator, dut.control_rate.value)

      expected_result = expected_gain(depth, current)

      assert dut.tremolo_gain.value == expected_result, (
         f"Got: {int(dut.tremolo_gain.value)}. Expected: {int(expected_result)}"
      )
   
      
