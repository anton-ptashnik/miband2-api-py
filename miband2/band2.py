import bleak
import struct
import enum
from datetime import datetime
from . import authsession

class NotificationType(enum.Enum):
    SINGLE = 1
    CONTINUOS = 2
    INVISIBLE = 3
    LIKE = 0xfe

class Band2:
    def __init__(self, dev: bleak.BleakClient) -> None:
        self.device = dev

    async def connect(self):
        await self.device.connect()

    async def disconnect(self):
        await self.device.disconnect()

    async def __aenter__(self):
        await self.device.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.device.__aexit__(exc_type, exc_val, exc_tb)

    async def ring(self, ring: NotificationType):
        await self.device.write_gatt_char("00002a06-0000-1000-8000-00805f9b34fb", bytes([ring.value]))

    async def set_datetime(self, dt: datetime):
        data = _pack_datetime(dt)
        await self.device.write_gatt_char("00002a2b-0000-1000-8000-00805f9b34fb", data)

    async def get_datetime(self):
        raw_data = await self.device.read_gatt_char("00002a2b-0000-1000-8000-00805f9b34fb")
        data = struct.unpack('hbbbbbbxxx', raw_data)
        return datetime(*data)

    async def get_battery(self):
        data = await self.device.read_gatt_char("00000006-0000-3512-2118-0009af100700")
        level = data[1]
        status = 'normal' if data[2] == 0 else "charging"

        last_charge = struct.unpack("hbbxxx", data[11:18])
        last_off = struct.unpack("hbbxxx", data[3:10])

        return {
            'level': int(level),
            'status': status,
            'last_off': datetime(*last_off),
            'last_charge': datetime(*last_charge)
        }
    
    async def request_heartbeat(self, callback):
        async def cb(char, data):
            print(f"hb received from: {char}")
            await self.device.stop_notify("00002a37-0000-1000-8000-00805f9b34fb")
            callback(data[1])

        await self.device.start_notify("00002a37-0000-1000-8000-00805f9b34fb", cb)
        await self.device.write_gatt_char("00002a39-0000-1000-8000-00805f9b34fb", b'\x15\x02\x00')
        await self.device.write_gatt_char("00002a39-0000-1000-8000-00805f9b34fb", b'\x15\x02\x01')

    # todo sniff a call with different 
    async def set_onetime_alarm(self, slot, h, m):
        # byte[] alarmMessage = new byte[]{
        #         (byte) 0x2, // TODO what is this?
        #         (byte) (actionMask | alarm.getPosition()), // action mask + alarm slot
        #         (byte) calendar.get(Calendar.HOUR_OF_DAY),
        #         (byte) calendar.get(Calendar.MINUTE),
        #         (byte) daysMask,
        # };
        # return new Alarm(-1, -1, index, true, smartWakeup, snooze, Alarm.ALARM_ONCE, calendar.get(Calendar.HOUR_OF_DAY), calendar.get(Calendar.MINUTE), false, GBApplication.getContext().getString(R.string.quick_alarm), GBApplication.getContext().getString(R.string.quick_alarm_description));
        actionMask = 0x80 | 0x40
        daysMask = 128

        data = bytes([2, actionMask | slot, h, m, daysMask])
        await self.device.write_gatt_char("00000003-0000-3512-2118-0009af100700", data)

    async def unset_alarm(self, slot):
        daysMask = 0
        h = m = 0

        data = bytes([0x2, slot, h, m, daysMask])
        await self.device.write_gatt_char("00000003-0000-3512-2118-0009af100700", data)

    # async def get_alarms(self):
    #     return await self.device.write_gatt_char("00000003-0000-3512-2118-0009af100700", 0x0d, response=True)
    
    async def auth(self, key):
        s = authsession.Session(self.device, key)
        return await s.start()
    
def _unpack_datetime(raw_data):
    data = struct.unpack('hbbbbbbxxx', raw_data)
    return datetime(*data)

def _pack_datetime(datetime_obj):
    dt = datetime_obj
    return struct.pack('hbbbbbbxxx', dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.weekday())
