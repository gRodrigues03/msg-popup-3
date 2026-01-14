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
known_users = {}       # ip -> username
received_messages = {} # ip -> list of message strings


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
            name = data.rstrip(b"\x00").decode("ascii", errors="ignore").strip(";")
            if name and addr[0] != "127.0.0.1" and name != USERNAME:
                if addr[0] not in known_users:
                    known_users[addr[0]] = name
                    event_queue.put(("discovered", addr[0], name))
                else:
                    known_users[addr[0]] = name
        except socket.timeout:
            continue


def message_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("", MESSAGE_PORT))
    sock.listen(5)

    while True:
        conn, addr = sock.accept()
        conn.settimeout(2.0)
        data = b""

        try:
            while True:
                chunk = conn.recv(8192)
                if not chunk: break
                data += chunk
        except:
            pass

        conn.close()

        if data:
            try:
                text = data.decode("cp1252", errors="ignore")
                event_queue.put(("message", addr[0], text))
            except:
                pass


def send_message(ip: str, message: str):
    if not message.strip():
        return

    header = f"{USERNAME}\n{datetime.now().strftime('%d/%m, %H:%M')}\n---------------------------\n"
    full_msg = header + message +'\n'

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(4)
            s.connect((ip, MESSAGE_PORT))
            s.sendall(full_msg.encode("cp1252", "ignore"))
    except Exception as e:
        print(f"Send failed to {ip}: {e}")


# ---------------- UI ----------------

class Tray(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        super().__init__(wx.adv.TBI_DEFAULT_TYPE)
        self.frame = frame

        icon = wx.Icon(wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_OTHER, (32, 32)))
        self.SetIcon(icon, tooltip=f"MessagePopup II - {USERNAME}")

        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_click)
        self.Bind(wx.adv.EVT_TASKBAR_RIGHT_UP, self.on_right_click)

    def on_left_click(self, evt):
        self.frame.Show()
        self.frame.Restore()
        self.frame.Raise()

    def on_right_click(self, evt):
        menu = wx.Menu()
        show_item = menu.Append(wx.ID_ANY, "Open", "Show window")
        exit_item = menu.Append(wx.ID_ANY, "Exit", "Close the program")

        self.Bind(wx.EVT_MENU, self.on_menu_show, show_item)
        self.Bind(wx.EVT_MENU, self.on_menu_exit, exit_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def on_menu_show(self, evt):
        self.frame.Show()
        self.frame.Restore()

    def on_menu_exit(self, evt):
        wx.GetApp().ExitMainLoop()


# ── Main Window ─────────────────────────────────────────────────────────────
class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=f"MessagePopup II  –  {USERNAME}", size=(720, 520),
                         style=wx.DEFAULT_FRAME_STYLE | wx.MINIMIZE_BOX)

        self.SetBackgroundColour(wx.Colour(240, 240, 240))
        self.current_recipient_ip = None

        self.tray_icon = Tray(self)

        self._init_ui()

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_ICONIZE, self.on_minimize)

        wx.CallLater(300, self.poll_events)

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # LEFT - Users list
        left_panel = wx.Panel(self)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(left_panel, label="  Users Online", style=wx.ALIGN_LEFT)
        title.SetFont(wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        title.SetBackgroundColour(wx.Colour(80, 100, 160))
        title.SetForegroundColour(wx.WHITE)
        left_sizer.Add(title, flag=wx.EXPAND)

        self.user_list = wx.ListBox(left_panel, style=wx.LB_SINGLE | wx.BORDER_SIMPLE)
        self.user_list.SetBackgroundColour(wx.Colour(245, 245, 230))
        self.user_list.Bind(wx.EVT_LISTBOX, self.on_select_user)
        left_sizer.Add(self.user_list, 1, wx.EXPAND | wx.ALL, 4)

        left_panel.SetSizer(left_sizer)
        main_sizer.Add(left_panel, 1, wx.EXPAND | wx.ALL, 3)

        # RIGHT - Chat area
        right_panel = wx.Panel(self)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        self.chat_text = wx.TextCtrl(right_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SIMPLE)
        self.chat_text.SetBackgroundColour(wx.WHITE)
        self.chat_text.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL, faceName="Lucida Console"))
        right_sizer.Add(self.chat_text, 1, wx.EXPAND | wx.ALL, 4)

        # Input + Send
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.msg_input = wx.TextCtrl(right_panel, style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER)
        self.msg_input.SetMinSize((-1, 80))
        self.msg_input.Bind(wx.EVT_TEXT_ENTER, self.on_send_message)
        input_sizer.Add(self.msg_input, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        send_btn = wx.Button(right_panel, label="Send", size=(80, -1))
        send_btn.Bind(wx.EVT_BUTTON, self.on_send_message)
        input_sizer.Add(send_btn, 0, wx.RIGHT | wx.BOTTOM, 8)

        right_sizer.Add(input_sizer, 0, wx.EXPAND)
        right_panel.SetSizer(right_sizer)
        main_sizer.Add(right_panel, 2, wx.EXPAND | wx.ALL, 3)

        self.SetSizer(main_sizer)
        self.Layout()

    def on_select_user(self, evt):
        sel = self.user_list.GetSelection()
        if sel == wx.NOT_FOUND:
            self.current_recipient_ip = None
            self.chat_text.Clear()
            self.chat_text.AppendText("← Select a user")
            return

        ip = list(known_users.keys())[sel]
        self.current_recipient_ip = ip
        self.chat_text.Clear()

        if ip in received_messages:
            for msg in received_messages[ip]:
                self.chat_text.AppendText(msg + "\n")

        self.chat_text.AppendText(f"\n--- Chat with {known_users[ip]} ({ip}) ---\n")
        self.msg_input.SetFocus()

    def on_send_message(self, evt):
        if not self.current_recipient_ip:
            wx.MessageBox("Select a destination first!", "Attention", wx.OK|wx.ICON_WARNING)
            return

        text = self.msg_input.GetValue().strip()
        if not text:
            return

        send_message(self.current_recipient_ip, text)

        time_str = datetime.now().strftime("%H:%M")
        line = f"[{time_str}] {USERNAME}: {text}\n"
        self.chat_text.AppendText(line)
        received_messages.setdefault(self.current_recipient_ip, []).append(line)

        self.msg_input.Clear()
        self.msg_input.SetFocus()

    def poll_events(self):
        while not event_queue.empty():
            typ, ip, data = event_queue.get()

            if typ == "discovered":
                name = data
                display_str = f"{name}  ({ip})"

                found = False
                for i in range(self.user_list.GetCount()):
                    if ip in self.user_list.GetString(i):
                        self.user_list.SetString(i, display_str)
                        found = True
                        break

                if not found:
                    self.user_list.Append(display_str)

                items = []
                for i in range(self.user_list.GetCount()):
                    items.append(self.user_list.GetString(i))

                items.sort(key=lambda x: x.lower())

                self.user_list.Clear()
                for item in items:
                    self.user_list.Append(item)

            elif typ == "message":
                if ip not in known_users:
                    known_users[ip] = f"??? ({ip})"

                sender = known_users[ip]
                lines = data.splitlines()

                display = f"[{datetime.now().strftime('%H:%M')}] {sender}:\n"
                display += "\n".join(lines[3:]) if len(lines) > 3 else data
                display += "\n" + "─"*60 + "\n"

                received_messages.setdefault(ip, []).append(display)

                if self.current_recipient_ip == ip:
                    self.chat_text.AppendText(display)
                else:
                    self.SetTitle(f"★ New message from {sender}")

        if not self.IsShown() and "★ New message" in self.GetTitle():
            wx.CallLater(6000, lambda: self.SetTitle(f"MessagePopup II  –  {USERNAME}"))

        wx.CallLater(250, self.poll_events)

    def on_minimize(self, evt):
        evt.Skip()
        self.Hide()

    def on_close(self, evt):
        if self.tray_icon.IsIconInstalled():
            evt.Veto()
            self.Hide()
        else:
            evt.Skip()


if __name__ == "__main__":
    threading.Thread(target=discovery_loop, daemon=True).start()
    threading.Thread(target=message_server, daemon=True).start()

    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    frame.Centre()
    app.MainLoop()