from dataclasses import dataclass
import pyaes
import logging
import enum
import asyncio
import bleak

logging.basicConfig()
logger = logging.getLogger(__name__)

class AuthReply(enum.Enum):
    KEY_ACCEPTED = b'\x10\x01\x01'
    RAND_MSG_RECEIVED = b'\x10\x02\x01'
    AUTH_OK = b'\x10\x03\x01'
    KEY_MISMATCH = b'\x10\x03\x04'
    KEY_ABORTED = b'\x10\x01\x02'

@dataclass
class Key:
    key: bytes
    reset: bool = False

class Session:
    def __init__(self, dev: bleak.BleakClient, key: Key) -> None:
        self.dev = dev
        self.key = key.key
        self.reset = key.reset
        self.mac = dev.address

    async def _send_auth_msg(self, data):
        await self.dev.write_gatt_char("00000009-0000-3512-2118-0009af100700", bytes(data))

    async def start_replies_collection(self):
        q = asyncio.Queue()
        async def signal_accumulator(_, data):
            await q.put(data)

        await self.dev.start_notify("00000009-0000-3512-2118-0009af100700", signal_accumulator)
        return q
    
    async def stop_replies_collection(self):
        await self.dev.stop_notify("00000009-0000-3512-2118-0009af100700")

    async def start(self):
        init_func, handlers = self.make_handlers_chain()
        auth_replies_queue = await self.start_replies_collection()
        await init_func()
        while handlers:
            data = await auth_replies_queue.get()
            code, msg = self._parse_msg(data)
            exp_code, handler = handlers.pop(0)
            if code != exp_code.value:
                break
            await handler(msg)
        await self.stop_replies_collection()
        return self._parse_status(code)

    def _parse_msg(self, msg):
        return bytes(msg[:3]), msg[3:]
    
    def make_handlers_chain(self):
        handlers = []
        auth_init_func = None
        if self.reset:
            auth_init_func = self._send_key
            handlers.append((AuthReply.KEY_ACCEPTED, self.handle_key_accepted))
        else:
            auth_init_func = self._req_secret
        
        handlers.append((AuthReply.RAND_MSG_RECEIVED, self._send_enc_msg))
        handlers.append((AuthReply.AUTH_OK, self.handle_done))

        return (auth_init_func, handlers)

    async def handle_done(self, _):
        self._log("auth complete")
    
    async def handle_key_accepted(self, _):
        self._log("key accepted")
        await self._req_secret()

    async def _req_secret(self):
        self._log("requesting a secret", issent=True)
        await self._send_auth_msg([2,0])
        
    async def _send_key(self):
        self._log("sending a key", issent=True)
        await self._send_auth_msg([1,0] + list(self.key))

    async def _send_enc_msg(self, msg):
        self._log("secret received")
        self._log("sending an encrypted secret", issent=True)
        aes = pyaes.AESModeOfOperationECB(self.key)
        msg = list(aes.encrypt(bytes(msg)))
        await self._send_auth_msg([3,0] + msg)

    def _log(self, msg, issent=False):
        dirlabel = "<-" if issent else "->"
        logger.debug("%s %s host : %s", self.mac, dirlabel, msg)

    def _parse_status(self, code):
        return next(filter(lambda s: s.value == code, AuthReply), Exception(f"unknown status code: {code}"))
