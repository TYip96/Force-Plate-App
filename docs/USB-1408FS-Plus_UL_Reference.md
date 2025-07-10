# USB-1408FS-Plus Universal Library Reference

This document contains the official Universal Library (UL) documentation for the USB-1208FS-Plus and USB-1408FS-Plus devices.

## Device Overview

The USB-1208FS-Plus and USB-1408FS-Plus support the following UL and UL for .NET features. Unless otherwise indicated, OEM versions support the same features as the equivalent standard versions.

## Analog Input

### Functions
- **UL**: `cbAIn()`, `cbAInScan()`, `cbALoadQueue()`, `cbFileAInScan()`, `cbATrig()`
- **UL for .NET**: `AIn()`, `AInScan()`, `ALoadQueue()`, `FileAInScan()`, `ATrig()`

### Options
`BACKGROUND`, `BLOCKIO`, `CONTINUOUS`, `EXTCLOCK`, `EXTTRIGGER`, `HIGHRESRATE`, `NOCALIBRATEDATA`, `RETRIGMODE*`, `SCALEDATA`, `SINGLEIO`

*Note: `RETRIGMODE` can only be used with `cbAInScan()`/`AInScan()`.*

### Mode
- Single-ended and differential

### Channel Configuration
- **HighChan**: 
  - 0 to 7 in single-ended mode
  - 0 to 3 in differential mode
- **Count**: Must be an integer multiple of the number of channels in the scan

### Packet Size
Rate dependent. The default packet size is 32 samples. At higher rates, the packet size increases by a multiple of 32.

### Sample Rate
- **USB-1208FS**: 0.014 Hz to 51.993 kHz for BLOCKIO mode
- **USB-1408FS**: 0.14 Hz to 48 kHz maximum for BLOCKIO mode

The throughput depends on the system being used. Most systems can achieve 40 kHz aggregate.

When using `cbAInScan()`/`AInScan()`, the minimum sample rate is 1 Hz.

### Voltage Ranges
**Single-ended**:
- `BIP10VOLTS` (±10 volts)

**Differential**:
- `BIP20VOLTS` (±20 volts)
- `BIP10VOLTS` (±10 volts)
- `BIP5VOLTS` (±5 volts)
- `BIP4VOLTS` (±4 volts)
- `BIP2PT5VOLTS` (±2.5 volts)
- `BIP2VOLTS` (±2 volts)
- `BIP1PT25VOLTS` (±1.25 volts)
- `BIP1VOLTS` (±1 volts)

### Pacing
- **Hardware pacing, internal clock supported**
- External clock supported via the SYNC pin

## Triggering

### Functions
- **UL**: `cbSetTrigger()`
- **UL for .NET**: `SetTrigger()`

### TrigType
`TRIGPOSEDGE`, `TRIGNEGEDGE`, `TRIGHIGH`, `TRIGLOW`

Both devices support external digital (TTL) hardware triggering. Use the TRIG_IN input for the external trigger signal.

## Analog Output

### Functions
- **UL**: `cbAOut()`, `cbVOut()`, `cbAOutScan()`
- **UL for .NET**: `AOut()`, `VOut()`, `AOutScan()`

### Options
`BACKGROUND`, `CONTINUOUS`

### Configuration
- **HighChan**: 0 to 1
- **Count**: Must be an integer multiple of the number of channels in the scan
- **Rate**: 50 kHz max per channel
- **Range**: `UNI5VOLTS` (0 to 5 volts)
- **DataValue**: 0 to 4,095

## Digital I/O

### Configuration Functions
- **UL**: `cbDConfigPort()`
- **UL for .NET**: `DConfigPort()`
- **PortNum**: `FIRSTPORTA`, `FIRSTPORTB`

### Port I/O Functions
- **UL**: `cbDIn()`, `cbDOut()`
- **UL for .NET**: `DIn()`, `DOut()`
- **DataValue**: 0 to 255 for FIRSTPORTA or FIRSTPORTB

### Bit I/O Functions
- **UL**: `cbDBitIn()`, `cbDBitOut()`
- **UL for .NET**: `DBitIn()`, `DBitOut()`
- **PortType**: `FIRSTPORTA`
- **BitNum**: 0 to 15 for FIRSTPORTA

## Counter I/O

### Functions
- **UL**: `cbCIn()`*, `cbCIn32()`, `cbCLoad()`**, `cbCLoad32()`**
- **UL for .NET**: `CIn()`*, `CIn32()`, `CLoad()`**, `CLoad32()`**

*Although `cbCIn()`/`CIn()` are valid for use with this counter, `cbCIn32()`/`CIn32()` may be more appropriate for values greater than 32,767.

**`cbCLoad()`, `cbCLoad32()`, `CLoad()` and `CLoad32()` only accept Count=0 and are used to reset the counter.

### Configuration
- **CounterNum**: 1
- **Count**: 2³²-1 when reading, 0 when loading (reset only)

## Event Notification

### Functions
- **UL**: `cbEnableEvent()`, `cbDisableEvent()`
- **UL for .NET**: `EnableEvent()`, `DisableEvent()`

### Event Types
`ON_SCAN_ERROR` (analog input and analog output), `ON_DATA_AVAILABLE`, `ON_END_OF_INPUT_SCAN`, `ON_END_OF_OUTPUT_SCAN`

## Hardware Considerations

### Channel-gain Queue
The channel-gain queue is limited to 8 elements in single-ended mode, and 4 elements in differential mode. The channels specified must be unique and listed in increasing order.

### Acquisition Rate
Most systems can sustain rates of 40 kS/s aggregate in BLOCKIO mode, and 1 kS/s aggregate in SINGLEIO mode.

### HIGHRESRATE
When specified, the rate at which samples are acquired is in "samples per 1000 seconds per channel".

### EXTCLOCK
By default, the SYNC pin is configured for pacer output. To configure for pacer input, use the EXTCLOCK option.

### Scaling Data
Results using SCALEDATA may be slightly different from results using `cbToEngUnits()` near range limits.

### Resolution
In single-ended mode, resolution is 11 bits but mapped to 12-bit values. Data contains only even numbers between 0 and 4,094 when NOCALIBRATEDATA is used.

### Continuous Scans
When using `cbAInScan()`/`AInScan()` with CONTINUOUS, set count to be an integer multiple of the number of channels to maintain proper data alignment.

### Analog Output
When including both analog output channels in `cbAOutScan()`/`AOutScan()`, the two channels are updated simultaneously.

## Important Notes for Force Plate Application

1. **Hardware Pacing**: The device uses hardware pacing with internal clock, ensuring precise sample timing regardless of USB transfer timing.

2. **Packet Size Behavior**: Default packet size is 32 samples, increasing in multiples of 32 at higher rates. This explains apparent "jitter" in USB data delivery.

3. **TIMED Option**: Not listed in supported options for this device, which explains inconsistent test results when attempting to use it.

4. **Current Configuration**: Using `BACKGROUND | CONTINUOUS | SCALEDATA` is the correct approach for real-time data acquisition.

## Additional Resources

- **mcculw Python Library**: https://github.com/mccdaq/mcculw
  - Official MCC Universal Library Python API for Windows
  - MIT Licensed
  - Provides Python bindings for all UL functions
  
- **Measurement Computing Documentation**: https://www.mccdaq.com/support.aspx
  - Complete device specifications
  - Application notes and technical references
  - Software downloads and updates