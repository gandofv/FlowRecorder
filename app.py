import sys
import threading
import shlex
from pathlib import Path
from queue import Empty, Queue

if sys.platform not in ("win32", "darwin"):
    raise SystemExit("此应用支持 macOS 和 Windows。")

import desktop  # Configure Windows DPI before creating a Tk window.
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import ImageTk
from pynput import keyboard
import engine
import flow


class Studio:
    def __init__(self, root):
        self.root = root
        root.title("步录 · 桌面流程")
        root.geometry("820x540")
        root.minsize(690, 465)
        self.doc = self.empty()
        self.path = None
        self.dirty = False
        self.busy = False
        self.events = Queue()
        self.status = tk.StringVar(value="准备就绪")
        self.title = tk.StringVar(value="未命名流程")
        panel = ttk.Frame(root, padding=18)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, textvariable=self.title, font=("", 20, "bold")).pack(anchor="w")
        tools = ttk.Frame(panel)
        tools.pack(fill="x", pady=12)
        self.actions = []
        for title, cmd in [("录制新流程", lambda:self.start("new")), ("打开", self.open),
                           ("保存", self.save), ("▶ 回放", lambda:self.start("play"))]:
            self.button(tools, title, cmd)
        self.halt = ttk.Button(tools, text="停止  F8", command=lambda:self.stop.set())
        self.halt.pack(side="right")
        self.halt.state(["disabled"])
        self.table = ttk.Treeview(panel, columns=("number","name","delay"), show="headings", selectmode="browse")
        for key, title, width in [("number","步骤",60),("name","操作名称",300),("delay","点击前等待（秒）",130)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor="w", stretch=key=="name")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", lambda _:self.preview())
        bottom = ttk.Frame(panel)
        bottom.pack(fill="x", pady=8)
        self.preview_label = ttk.Label(bottom, text="选择步骤查看定位图", width=22)
        self.preview_label.pack(side="left")
        self.button(bottom, "编辑步骤", self.edit)
        self.button(bottom, "重录此步", lambda:self.start("replace"))
        self.button(bottom, "删除此步", self.delete)
        self.button(bottom, "生成快捷脚本", self.export)
        ttk.Separator(panel).pack(fill="x", pady=5)
        ttk.Label(panel, textvariable=self.status, wraplength=650).pack(anchor="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(70, self.poll)

    def empty(self):
        return dict(version=1, platform=sys.platform, app="", steps=[])

    def button(self, row, title, cmd):
        b = ttk.Button(row, text=title, command=cmd)
        b.pack(side="left", padx=(0, 6))
        self.actions.append(b)

    def refresh(self, pick=None):
        self.title.set((self.path.stem if self.path else "未命名流程")+(" *" if self.dirty else ""))
        self.table.delete(*self.table.get_children())
        for i,s in enumerate(self.doc["steps"]):
            self.table.insert("", "end", iid=str(i), values=(i+1,s["name"],f'{s["delay"]:.2f}'))
        if pick is not None and self.table.exists(str(pick)):
            self.table.selection_set(str(pick))
            self.table.see(str(pick))
        self.preview()

    def preview(self):
        selected = self.table.selection()
        if not selected:
            self.preview_label.configure(image="", text="选择步骤查看定位图")
            return
        pic = flow.patch_of(self.doc["steps"][int(selected[0])])
        self.thumb = ImageTk.PhotoImage(pic)
        self.preview_label.configure(image=self.thumb, text="")

    def index(self):
        selected = self.table.selection()
        if selected:
            return int(selected[0])
        self.status.set("请先选择一步。")

    def discard(self):
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("保存流程", "保存当前修改？")
        return False if ans is None else self.save() if ans else True

    def open(self):
        p = filedialog.askopenfilename(filetypes=[("流程脚本","*.json")])
        if p and self.discard():
            try:
                self.doc = flow.load(p)
                self.path, self.dirty = Path(p), False
                self.refresh()
                self.status.set("已打开，可以回放或修改步骤。")
            except Exception as e:
                messagebox.showerror("无法打开",str(e))

    def save(self):
        if not self.doc["steps"]:
            self.status.set("请先录制至少一步。")
            return False
        p = self.path or filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("流程脚本","*.json")])
        if not p:
            return False
        try:
            flow.save(p, self.doc)
            self.path, self.dirty = Path(p), False
            self.refresh()
            self.status.set("已保存")
            return True
        except Exception as e:
            messagebox.showerror("保存失败",str(e))
            return False

    def export(self):
        if not self.save():
            return
        mac = sys.platform == "darwin"
        ext = ".command" if mac else ".cmd"
        p = filedialog.asksaveasfilename(title="生成双击回放入口", initialfile=self.path.stem+"-回放"+ext,
                                         defaultextension=ext, filetypes=[("快捷脚本","*"+ext)])
        if not p:
            return
        home = Path(__file__).resolve().parent
        dest = Path(p)
        if dest.resolve() in (self.path.resolve(), (home/"Start.cmd").resolve(), (home/"Start.command").resolve()):
            messagebox.showerror("无法生成", "请选择单独的快捷脚本文件名。")
            return
        try:
            if mac:
                cmd = "#!/bin/bash\nexec /bin/bash "+shlex.quote(str(home/"Start.command"))+" --play "+shlex.quote(str(self.path.resolve()))+"\n"
                dest.write_text(cmd, encoding="utf-8")
                dest.chmod(0o755)
            else:
                # Batch files expand percent signs even inside double quotes.
                launcher = str(home/"Start.cmd").replace("%","%%")
                script = str(self.path.resolve()).replace("%","%%")
                cmd = f'@echo off\nchcp 65001 >nul\nsetlocal DisableDelayedExpansion\n"{launcher}" --play "{script}"\n'
                dest.write_text(cmd, encoding="utf-8")
            self.status.set("已生成快捷脚本，双击即可打开回放。")
        except OSError as e:
            messagebox.showerror("无法生成", str(e))

    def edit(self):
        i = self.index()
        if i is None:
            return
        s = self.doc["steps"][i]
        name = simpledialog.askstring("编辑步骤","操作名称",initialvalue=s["name"])
        if not name or not name.strip():
            return
        delay = simpledialog.askfloat("编辑步骤","点击前等待多少秒？",initialvalue=s["delay"],minvalue=0,maxvalue=3600)
        if delay is not None:
            s.update(name=name.strip(),delay=delay)
            self.dirty = True
            self.refresh(i)

    def delete(self):
        i = self.index()
        if i is not None and messagebox.askyesno("删除步骤", "删除选中的步骤？"):
            del self.doc["steps"][i]
            self.dirty = True
            self.refresh()

    def start(self, mode):
        if self.busy:
            return
        i = self.index() if mode=="replace" else None
        if mode=="replace" and i is None:
            return
        if mode=="play" and not self.doc["steps"]:
            self.status.set("请先录制或打开流程。")
            return
        if mode=="new" and not self.discard():
            return
        if not messagebox.askokcancel("准备开始", "请让目标窗口位于主显示器。确定后有 3 秒切换到起始页面。\n听到提示音后开始录制；按 F8 停止（部分 Mac 使用 Fn + F8）。" if mode!="play" else
                                      "请回到录制时的起始页面。确定后有 3 秒切换到目标窗口。按 F8 可中止回放。"):
            return
        self.stop = threading.Event()
        self.mode, self.replace_index = mode, i
        self.pending = self.empty()
        self.problem = ""
        self.busy = True
        for b in self.actions:
            b.state(["disabled"])
        self.halt.state(["!disabled"])
        self.root.iconify()
        def emit(kind,value):
            self.events.put((kind,value))
        def run():
            try:
                with keyboard.Listener(on_press=lambda k:self.stop.set() if k==keyboard.Key.f8 else None):
                    if mode=="play":
                        engine.play(self.doc,self.stop,emit)
                    else:
                        engine.record(self.stop,emit,self.doc["app"] if mode=="replace" else None, mode=="replace")
            except Exception as e:
                emit("error",str(e) or type(e).__name__)
            finally:
                emit("end",None)
        threading.Thread(target=run,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, v = self.events.get_nowait()
                if kind in ("status","ready"):
                    self.status.set(v)
                    if kind=="ready":
                        self.root.bell()
                elif kind=="app":
                    self.pending["app"] = v
                elif kind=="progress":
                    self.table.selection_set(str(v[0]-1))
                    self.status.set(f"正在执行第 {v[0]} 步 · {v[1]}")
                elif kind=="step":
                    self.pending["steps"].append(v)
                elif kind=="error":
                    self.problem = v
                elif kind=="end":
                    self.finish()
        except Empty:
            pass
        self.root.after(70,self.poll)

    def finish(self):
        self.busy = False
        self.root.deiconify()
        self.root.lift()
        for b in self.actions:
            b.state(["!disabled"])
        self.halt.state(["disabled"])
        steps = self.pending["steps"]
        if self.mode=="new" and steps:
            self.doc, self.path, self.dirty = self.pending, None, True
        if self.mode=="replace" and steps:
            old = self.doc["steps"][self.replace_index]
            old.update(image=steps[0]["image"], offset=steps[0]["offset"])
            self.dirty = True
        self.refresh(self.replace_index)
        if self.problem:
            self.status.set(self.problem)
            messagebox.showerror("流程已停止",self.problem)
        elif self.mode=="play":
            self.status.set("已中止回放" if self.stop.is_set() else "回放完成")
        else:
            self.status.set(f"本次记录 {len(steps)} 步")
    def close(self):
        if self.busy:
            self.stop.set()
        elif self.discard():
            self.root.destroy()


if __name__=="__main__":
    root = tk.Tk()
    studio = Studio(root)
    if len(sys.argv)==3 and sys.argv[1]=="--play":
        try:
            studio.doc = flow.load(sys.argv[2])
            studio.path = Path(sys.argv[2])
            studio.refresh()
            root.after(250, lambda:studio.start("play"))
        except Exception as e:
            messagebox.showerror("脚本读取失败", str(e))
    root.mainloop()
