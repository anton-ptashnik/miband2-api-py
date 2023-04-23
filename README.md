# MiBand2 Python API based on bleak

The library provides convenient APIs to control and read data of MiBand2.

## Supported features

- sending notifications
- date/time setup and reading
- onetime alarm setup
- reading battery level

## Usage

```
import asyncio
import bleak
from miband2 import Band2, Key, NotificationType as NT
from datetime import datetime

KEY = Key(
    key=b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x05',
    reset=True # note *
)

async def main():
    located_band = await scan_bands(timeout=15)
    client = bleak.BleakClient(located_band, timeout=15)
    
    async with Band2(client) as band:
        auth_status = await band.auth(KEY)
        print(f"auth status: {auth_status}")

        battery_level = await band.get_battery()
        print(f"battery: {battery_level}")

        await band.ring(NT.SINGLE)
        
        now = datetime.now()
        await band.set_datetime(now)

async def scan_bands(timeout):
    def bands_only(dev, adv):
        return "MI Band" in dev.name
    return await bleak.BleakScanner.find_device_by_filter(timeout=timeout, filterfunc=bands_only)

asyncio.run(main())
```
_Note: key reset is required for the first time only. Later, one can auth with the same key setting the `reset=False`_

## Why?

This project initially helped me to learn BLE.
My old Band2 got its second life when I started to learn BLE and became curious if I can communicate with the device using a Linux machine. This Band2 device acted as an oracle visually confirming if I craft packets correctly. The fact of a visual feedback in a form of a notification or displaying a newly set time provided some incentive to me and made learning funnier than it could be if relying solely on reading books.