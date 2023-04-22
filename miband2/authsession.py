import pyaes
import logging
import enum
from dataclasses import dataclass
import threading
import dbus
from dbus.mainloop import glib
from gi.repository import GLib

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

BUS = dbus.SystemBus(mainloop=glib.DBusGMainLoop())

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
    def __init__(self, device, key: Key, callback) -> None:
        self.auth_char = device.get_char("00000009-0000-3512-2118-0009af100700")
        self.callback = callback
        
        self.key = key.key
        self.reset = key.reset
        self.mac = device.mac
        self.next_handler = None

    def start(self):
        self.auth_char.start_notify(self.handle)

        if self.reset:
            self._send_key()
            self.next_handler = self.handle_init_reply
        else:
            self._req_secret()
            self.next_handler = self.handle_secret_reply

    def stop(self):
        self.auth_char.stop_notify()
        self.next_handler = None

    def parse_msg(self, msg):
        return bytes(msg[:3]), msg[3:]

    def handle(self, msg):
        code, msg = self.parse_msg(msg)
        self._log(f"code={code}, msg={msg}")
        try:
            done = self.next_handler(code, msg)
        except Exception:
            done = True

        if done:
            self.stop()
            self.report_status(code)
        
    def handle_init_reply(self, code, msg):
        self.verify_reply(AuthReply.KEY_ACCEPTED, code)
        self._log("key accepted")

        self._req_secret()
        self.next_handler = self.handle_secret_reply

    def handle_secret_reply(self, code, msg):
        self.verify_reply(AuthReply.RAND_MSG_RECEIVED, code)
        self._log("secret received")

        self._send_enc_msg(msg)
        self.next_handler = self.handle_done

    def handle_done(self, code, _):
        self.verify_reply(AuthReply.AUTH_OK, code)
        self._log("auth complete")

        return True

    def _req_secret(self):
        self._log("requesting a secret", issent=True)
        self.auth_char.send([2,0])
        
    def _send_key(self):
        self._log("sending a key", issent=True)
        self.auth_char.send([1,0] + list(self.key))

    def _send_enc_msg(self, msg):
        self._log("sending an encrypted secret", issent=True)
        aes = pyaes.AESModeOfOperationECB(self.key)
        msg = list(aes.encrypt(bytes(msg)))
        self.auth_char.send([3,0] + msg)

    def verify_reply(self, exp_code, act_code):
        if exp_code.value != act_code:
            raise Exception(f"unexpected reply. Exp: {exp_code}, act: {act_code}")
    
    def _log(self, msg, issent=False):
        dirlabel = "<-" if issent else "->"
        logger.debug("%s %s host : %s", self.mac, dirlabel, msg)

    def report_status(self, code):
        status = next(filter(lambda s: s.value == code, AuthReply), Exception(f"unknown code: {code}"))
        self.callback(status)


class Device:
    def __init__(self, mac) -> None:
        self.bus = BUS
        self.mac = mac
        self.dev_path = "/org/bluez/hci0/dev_" + mac.replace(":", "_")
        self.char_path_resolver = CharPathResolver(self.dev_path)
    
    def get_char(self, char_uuid):
        char_path = self.char_path_resolver.resolve(char_uuid)
        return Char(self.bus, char_path)


class CharPathResolver:
    CHAR_PATH_TEMPLATE = '{dev_path}/{rel_char_path}'
    UUID_TO_BUSPATH = {
        "00000009-0000-3512-2118-0009af100700": "service0052/char0053"
    }

    def __init__(self, dev_path) -> None:
        self.dev_path = dev_path

    def resolve(self, char_uuid):
        char_path = self.UUID_TO_BUSPATH.get(char_uuid)
        return self.CHAR_PATH_TEMPLATE.format(dev_path=self.dev_path, rel_char_path=char_path)

class Char:
    def __init__(self, bus, char_path) -> None:
        self.proxy = bus.get_object('org.bluez', char_path)
        self.char_obj = dbus.Interface(self.proxy, 'org.bluez.GattCharacteristic1')

    def start_notify(self, callback):
        self.upd_callback = callback
        self.signal = self.proxy.connect_to_signal("PropertiesChanged", self.cb)
        self.char_obj.StartNotify()

    def stop_notify(self):
        self.char_obj.StopNotify()
        self.signal.remove()

    def send(self, data):
        self.char_obj.WriteValue(data, {})

    def cb(self, iface, props, _):
        if "Notifying" in props:
            return
        self.upd_callback(props["Value"])


def _loop_init():
    
    loop_t = threading.Thread(target=lambda: GLib.MainLoop().run(), daemon=True)
    loop_t.start()

    global loop_initializer
    loop_initializer = _nop_loop_init

def _nop_loop_init():
    pass

loop_initializer = _loop_init

def auth(dev_mac, key, cb):
    loop_initializer()

    dev = Device(dev_mac)
    s = Session(dev, key, cb)
    s.start()
