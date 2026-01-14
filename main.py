import wx
import wx.adv
import socket
import threading
import time
from datetime import datetime
from queue import Queue

USERNAME = "GABRIEL"
DISCOVERY_PORT = 6711
MESSAGE_PORT = 6713
BROADCAST_ADDR = "<broadcast>"
ANNOUNCE_INTERVAL = 3

event_queue = Queue()
known_users = {}  # ip -> username


def make_payload(username: str) -> bytes:
    return f";{username}".encode("ascii").ljust(16, b"\x00")


# ---------------- Networking ----------------

def discovery_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", DISCOVERY_PORT))

    payload = make_payload(USERNAME)
    last_announce = 0

    while True:
        now = time.time()

        if now - last_announce >= ANNOUNCE_INTERVAL:
            sock.sendto(payload, (BROADCAST_ADDR, DISCOVERY_PORT))
            last_announce = now

        sock.settimeout(0.5)
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue

        name = data.rstrip(b"\x00").decode("ascii", errors="ignore")
        if name and addr[0] not in known_users:
            known_users[addr[0]] = name
            event_queue.put(("discovered", addr[0], name))


def message_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("", MESSAGE_PORT))
    sock.listen()

    while True:
        conn, addr = sock.accept()
        conn.settimeout(1.0)
        data = b""

        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass

        conn.close()

        if data:
            text = data.decode("cp1252", errors="ignore")
            event_queue.put(("message", addr[0], text))


def send_message(ip: str, message: str):
    # ensure at least 4 lines
    message = f'''{USERNAME}\n{datetime.now().strftime('%d/%m, %H:%M')}\n---------------------------\n''' + message

    while message.count("\n") < 3:
        message += "\n"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((ip, MESSAGE_PORT))
        s.sendall(message.encode("cp1252", "ignore"))


# ---------------- UI ----------------

class Tray(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        self.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION)), USERNAME)

        self.Bind(wx.adv.EVT_TASKBAR_RIGHT_UP, self.on_menu)

    def on_menu(self, event):
        menu = wx.Menu()

        send_item = menu.Append(-1, "Send message")
        exit_item = menu.Append(-1, "Exit")

        self.Bind(wx.EVT_MENU, self.on_send, send_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def on_send(self, event):
        if not known_users:
            wx.MessageBox("No users discovered.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        dlg = wx.SingleChoiceDialog(
            None,
            "Choose recipient",
            "Send message",
            [f"{v} ({k})" for k, v in known_users.items()]
        )

        if dlg.ShowModal() == wx.ID_OK:
            ip = list(known_users.keys())[dlg.GetSelection()]
            dlg.Destroy()

            msg = wx.TextEntryDialog(None, "Message:", "Send message")
            if msg.ShowModal() == wx.ID_OK:
                send_message(ip, msg.GetValue())
            msg.Destroy()
        else:
            dlg.Destroy()

    def on_exit(self, event):
        wx.GetApp().ExitMainLoop()


class App(wx.App):
    def OnInit(self):
        self.frame = wx.Frame(None)
        self.frame.Hide()

        self.tray = Tray(self.frame)

        wx.CallLater(200, self.poll_events)
        return True

    def poll_events(self):
        while not event_queue.empty():
            evt = event_queue.get()

            if evt[0] == "discovered":
                _, ip, name = evt
                # Displays message showing a discovered user
                # wx.MessageBox(
                #     f"{name} @ {ip}",
                #     "User discovered",
                #     wx.OK | wx.ICON_INFORMATION
                # )

            elif evt[0] == "message":
                _, ip, text = evt
                wx.MessageBox(
                    text,
                    f"Message from {known_users.get(ip, ip)}",
                    wx.OK | wx.ICON_INFORMATION
                )

        wx.CallLater(200, self.poll_events)


# ---------------- Main ----------------

if __name__ == "__main__":
    threading.Thread(target=discovery_loop, daemon=True).start()
    threading.Thread(target=message_server, daemon=True).start()

    app = App(False)
    app.MainLoop()
