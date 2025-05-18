import os
import ollama
import tkinter as tk
from tkinter import ttk
import markdown
from tkhtmlview import HTMLLabel
import json

from tools import get_current_date
from tools import fetch_url_content  # <-- Add this import

CONFIG_FILE = "client_config.json"

ollama_client = ollama.Client(host="http://servery:11434")
# Get available models at startup
try:
    models_response = ollama_client.list()
    models_list = models_response.get("models", [])
    model_names = [m.model for m in models_list]
except Exception as e:
    model_names = []
    print(f"Error fetching models: {e}")

# Set a default model (first in list or fallback)
selected_model = model_names[0] if model_names else None

# --- System message prefix ---
system_prefix = "You are a helpful assistant."  # Default system message prefix

class Chat(ttk.Frame):
    def __init__(self, parent, message, bg="#ffffff", think_content=None, last_json=None, role="assistant", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        import re

        # --- Bubble colors and icons ---
        if role == "user":
            bubble_bg = "#e6f0fa"
            border_color = "#b3d1f2"
            icon = "🧑"
            anchor = "e"
            justify = "right"
        else:
            bubble_bg = "#fffbe6"
            border_color = "#f2e6b3"
            icon = "🤖"
            anchor = "w"
            justify = "left"

        # --- Outer frame for alignment ---
        outer = tk.Frame(self, bg="#ffffff")
        outer.pack(fill="x", expand=True)
        # Add padding to left/right for alignment
        if anchor == "e":
            outer.pack_propagate(False)
            outer.grid_columnconfigure(0, weight=1)
            bubble_col = 1
        else:
            outer.pack_propagate(False)
            outer.grid_columnconfigure(1, weight=1)
            bubble_col = 0

        # --- Bubble frame ---
        bubble = tk.Frame(
            outer,
            bg=bubble_bg,
            highlightbackground=border_color,
            highlightthickness=2,
            bd=0,
        )
        bubble.grid(row=0, column=bubble_col, sticky=anchor, padx=(8, 40) if anchor == "w" else (40, 8), pady=6, ipadx=4, ipady=2)

        # --- Icon/avatar ---
        icon_label = tk.Label(bubble, text=icon, bg=bubble_bg, font=("Segoe UI Emoji", 14))
        icon_label.pack(side="left", padx=(2, 8), pady=2, anchor="n")  # <-- Add anchor="n" for top alignment

        # --- Message text ---
        plain_text = re.sub(r'<[^>]+>', '', markdown.markdown(message, extensions=["tables"]))
        text_widget = tk.Label(
            bubble,
            text=plain_text,
            bg=bubble_bg,
            font=("Segoe UI", 11),
            justify=justify,
            wraplength=420,
            anchor=anchor,
        )
        text_widget.pack(side="left", fill="both", expand=True, padx=(0, 4), pady=2, anchor="n")  # <-- Add anchor="n" for top alignment

        # --- Tooltip for think_content (on mouse over) ---
        if think_content:
            tooltip = None
            def show_tooltip(event=None):
                nonlocal tooltip
                if tooltip is not None:
                    return
                tooltip = tk.Toplevel(self)
                tooltip.wm_overrideredirect(True)
                x = text_widget.winfo_rootx() + 20
                y = text_widget.winfo_rooty() + 20
                tooltip.wm_geometry(f"+{x}+{y}")
                frame = ttk.Frame(tooltip, relief="solid", borderwidth=1)
                frame.pack()
                label = ttk.Label(frame, text=think_content, background="#ffffe0", wraplength=300, justify="left")
                label.pack(padx=8, pady=6)
            def hide_tooltip(event=None):
                nonlocal tooltip
                if tooltip is not None:
                    tooltip.destroy()
                    tooltip = None
            text_widget.bind("<Enter>", show_tooltip)
            text_widget.bind("<Leave>", hide_tooltip)

        # --- Double-click for JSON popup ---
        if last_json is not None:
            def show_json_popup(event=None):
                import json as _json
                def safe(obj):
                    if hasattr(obj, "dict"):
                        return obj.dict()
                    elif hasattr(obj, "to_dict"):
                        return obj.to_dict()
                    elif hasattr(obj, "__dict__"):
                        return vars(obj)
                    else:
                        return str(obj)
                popup = tk.Toplevel(self)
                popup.title("Ollama Request/Response JSON")
                popup.transient(self)
                popup.geometry("600x400")
                self.update_idletasks()
                root = self.winfo_toplevel()
                root.update_idletasks()
                root_x = root.winfo_rootx()
                root_y = root.winfo_rooty()
                root_width = root.winfo_width()
                root_height = root.winfo_height()
                popup_width = 600
                popup_height = 400
                x = root_x + (root_width // 2) - (popup_width // 2)
                y = root_y + (root_height // 2) - (popup_height // 2)
                popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")
                text = tk.Text(popup, wrap="word", font=("Consolas", 10))
                text.pack(fill="both", expand=True)
                try:
                    pretty = _json.dumps(last_json, indent=2, ensure_ascii=False, default=safe)
                except Exception as e:
                    pretty = f"Error displaying JSON: {e}"
                text.insert("1.0", pretty)
                text.config(state="disabled")
                btn = ttk.Button(popup, text="Close", command=popup.destroy)
                btn.pack(pady=6)
            text_widget.bind("<Double-Button-1>", show_json_popup)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

def main():
    global system_prefix  # So we can modify it in the modal

    # Load configuration
    config = load_config()
    system_prefix = config.get("system_prefix", system_prefix)

    # --- Add chat history ---
    chat_history = []  # List of {"role": "user"/"assistant", "content": ...}

    root = tk.Tk()
    root.title("Client Window")

    # --- Restore window geometry if present ---
    geometry = config.get("geometry")
    if geometry:
        root.geometry(geometry)
    else:
        root.geometry("800x600")

    # Main frame
    main_frame = ttk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    # Left panel
    left_panel = ttk.Frame(main_frame, width=200)
    left_panel.pack(side="left", fill="y")

    # --- Model dropdown at top left ---
    model_label = ttk.Label(left_panel, text="Model")
    model_label.pack(padx=10, pady=(10, 2), anchor="nw")

    # Use the list of models from Ollama for the dropdown
    # --- Load selected model from config if present ---
    selected_model_from_config = config.get("selected_model")
    initial_model = selected_model_from_config if selected_model_from_config in model_names else (model_names[0] if model_names else None)
    model_var = tk.StringVar(value=initial_model)
    model_dropdown = ttk.Combobox(left_panel, textvariable=model_var, values=model_names, state="readonly")
    model_dropdown.pack(padx=10, pady=(0, 10), fill="x", anchor="nw")

    # --- Save selected model to config on change ---
    def on_model_change(event=None):
        config["selected_model"] = model_var.get()
        save_config(config)
    model_dropdown.bind("<<ComboboxSelected>>", on_model_change)

    # --- Prefix button ---
    def open_prefix_modal():
        modal = tk.Toplevel(root)
        modal.title("Edit System Message Prefix")
        modal.transient(root)
        modal.grab_set()
        modal.geometry("400x300")

        # Center the modal on the main window
        root.update_idletasks()
        root_x = root.winfo_rootx()
        root_y = root.winfo_rooty()
        root_width = root.winfo_width()
        root_height = root.winfo_height()
        modal_width = 400
        modal_height = 300
        x = root_x + (root_width // 2) - (modal_width // 2)
        y = root_y + (root_height // 2) - (modal_height // 2)
        modal.geometry(f"{modal_width}x{modal_height}+{x}+{y}")

        # Use grid instead of pack for proper layout
        modal.grid_rowconfigure(0, weight=1)
        modal.grid_columnconfigure(0, weight=1)

        # Text area for editing the prefix
        text_area = tk.Text(modal, wrap="word", font=("TkDefaultFont", 11))
        text_area.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 0))
        text_area.insert("1.0", system_prefix)  # <-- Pre-fill with current system_prefix

        # Button frame
        btn_frame = ttk.Frame(modal)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(12, 12))

        def on_ok():
            global system_prefix
            system_prefix = text_area.get("1.0", "end-1c")
            # Save to config
            config["system_prefix"] = system_prefix
            save_config(config)
            modal.destroy()

        def on_cancel():
            modal.destroy()

        ok_btn = ttk.Button(btn_frame, text="OK", command=on_ok)
        ok_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="left", expand=True, fill="x")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        modal.wait_window()

    prefix_btn = ttk.Button(left_panel, text="Prefix", command=open_prefix_modal)
    prefix_btn.pack(padx=10, pady=(0, 10), fill="x", anchor="nw")

    # --- Right vertical paned window ---
    right_pane = ttk.PanedWindow(main_frame, orient="vertical")
    right_pane.pack(side="left", fill="both", expand=True)

    # --- Chat area with scrollable chat_container ---
    chat_area_frame = ttk.Frame(right_pane)
    right_pane.add(chat_area_frame, weight=4)

    # Canvas + scrollbar for chat_container
    chat_canvas = tk.Canvas(chat_area_frame, borderwidth=0, highlightthickness=0, bg="white")  # Set bg to white
    chat_scrollbar = ttk.Scrollbar(chat_area_frame, orient="vertical", command=chat_canvas.yview)
    chat_canvas.configure(yscrollcommand=chat_scrollbar.set)
    chat_scrollbar.pack(side="right", fill="y")
    chat_canvas.pack(side="left", fill="both", expand=True)

    # Frame inside canvas to hold chat components
    chat_container = tk.Frame(chat_canvas, bg="white")
    chat_container_id = chat_canvas.create_window((0, 0), window=chat_container, anchor="nw")

    def on_frame_configure(event):
        chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
    chat_container.bind("<Configure>", on_frame_configure)

    def resize_chat_container(event):
        chat_canvas.itemconfig(chat_container_id, width=event.width)
    chat_canvas.bind("<Configure>", resize_chat_container)

    # --- Now define the Chat History Panel and its functions ---
    # --- Chat History Panel ---
    chat_histories = []  # List of {"title": ..., "history": [...]}
    current_history_idx = [None]  # Use list for mutability in closures

    chat_history_panel = ttk.Frame(left_panel)
    chat_history_panel.pack(padx=10, pady=(0, 10), fill="both", expand=True)

    # --- Add button at the bottom for new chat ---
    def add_new_chat():
        nonlocal chat_history, current_history_idx
        chat_history = []
        chat_histories.append({
            "title": "New chat",
            "history": []
        })
        current_history_idx[0] = len(chat_histories) - 1
        refresh_chat_history_list()
        chat_history_listbox.selection_clear(0, "end")
        chat_history_listbox.selection_set(current_history_idx[0])
        # Clear chat container
        for widget in chat_container.winfo_children():
            widget.destroy()

    add_chat_btn = ttk.Button(chat_history_panel, text="+ New Chat", command=add_new_chat)
    add_chat_btn.pack(side="top", fill="x", pady=(4, 0))

    chat_history_listbox = tk.Listbox(chat_history_panel, activestyle="none")
    chat_history_listbox.pack(side="bottom", fill="both", expand=True)

    def refresh_chat_history_list():
        chat_history_listbox.delete(0, "end")
        for hist in chat_histories:
            chat_history_listbox.insert("end", hist["title"])

    def switch_to_history(idx):
        nonlocal chat_history, current_history_idx
        if idx is None or idx >= len(chat_histories):
            return
        chat_history = list(chat_histories[idx]["history"])
        current_history_idx[0] = idx
        # Clear chat container
        for widget in chat_container.winfo_children():
            widget.destroy()
        # Re-render chat history
        for msg in chat_history:
            bg = "#e6f0fa" if msg["role"] == "user" else "#fffbe6"
            Chat(chat_container, msg["content"], bg=bg, role=msg["role"]).pack(pady=2, padx=5, anchor="w", fill="x", expand=True)  # <-- add fill and expand
        root.after(10, lambda: chat_canvas.yview_moveto(1.0))

    def on_chat_history_select(event):
        idx = chat_history_listbox.curselection()
        if not idx:
            return
        idx = idx[0]
        if idx == len(chat_histories):  # "+ New Chat"
            add_new_chat()
        else:
            switch_to_history(idx)

    chat_history_listbox.bind("<<ListboxSelect>>", on_chat_history_select)


    # --- Initialize with one chat ---
    add_new_chat()

    # --- Command prompt ---
    command_prompt = tk.Text(right_pane, height=3, wrap="word")
    right_pane.add(command_prompt, weight=1)

    def on_command_prompt_enter(event):
        text = command_prompt.get("1.0", "end-1c").strip()
        if text:
            # Add user message to chat (blue tint)
            new_chat = Chat(chat_container, text, bg="#e6f0fa", role="user")
            new_chat.pack(pady=2, padx=5, anchor="w", fill="x", expand=True)  # <-- add fill and expand
            command_prompt.delete("1.0", "end")
            root.after(10, lambda: chat_canvas.yview_moveto(1.0))

            # --- Frame for thinking label only ---
            thinking_frame = ttk.Frame(chat_container, style="White.TFrame")
            thinking_frame.pack(pady=2, padx=5, anchor="w", fill="x")
            thinking_label = ttk.Label(thinking_frame, text="💡", background="#ffffff", font=("Arial", 18))
            thinking_label.pack(side="left", fill="x", padx=4, pady=2)
            root.after(10, lambda: chat_canvas.yview_moveto(1.0))  # <-- Ensure thinking panel is visible

            import math
            def fade_label(label_widget, min_gray=180, max_gray=240, period=1200, delay=40):
                steps = period // delay
                def step(i=0):
                    phase = (i % steps) / steps * 2 * math.pi
                    gray = int((math.sin(phase) * 0.5 + 0.5) * (max_gray - min_gray) + min_gray)
                    color = f"#{gray:02x}{gray:02x}{gray:02x}"
                    try:
                        label_widget.config(foreground=color)
                        if label_widget.winfo_exists():
                            label_widget.after(delay, step, i + 1)
                    except Exception:
                        pass
                step()
            fade_label(thinking_label)

            # --- Append user message to chat_history ---
            chat_history.append({"role": "user", "content": text})

            # --- Update chat_histories ---
            if current_history_idx[0] is not None:
                chat_histories[current_history_idx[0]]["history"] = list(chat_history)
                # Set title to first few words of first user message
                first_user = next((m for m in chat_history if m["role"] == "user"), None)
                if first_user:
                    words = first_user["content"].split()
                    chat_histories[current_history_idx[0]]["title"] = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
                refresh_chat_history_list()

            last_json = {"request": None, "response": None}

            def ollama_query():
                import re
                try:
                    model = model_var.get() or selected_model
                    messages = [
                        {"role": "control", "content": "thinking"}, # For granite models
                        {"role": "system", "content": "Enable deep thinking subroutine."}, # For cogito models
                        {"role": "system", "content": system_prefix},
                    ] + chat_history
                    last_json["request"] = {
                        "model": model,
                        "messages": messages
                    }
                    tools_text = config.get("tools", "").strip()
                    if tools_text:
                        last_json["request"]["tools"] = tools_text
                        # Add both tools to the tools list
                        response = ollama_client.chat(model=model, messages=messages, tools=[get_current_date, fetch_url_content])
                    else:
                        response = ollama_client.chat(model=model, messages=messages)
                    last_json["response"] = response

                    # --- Tool call handling ---
                    tool_calls = response.get("message", {}).get("tool_calls")
                    if tool_calls:
                        tool_results = []
                        for call in tool_calls:
                            tool_name = call.function.name
                            arguments = call.function.arguments

                            # Map tool name to function
                            if tool_name == "get_current_date":
                                result = get_current_date(**arguments) if isinstance(arguments, dict) else get_current_date()
                            elif tool_name == "fetch_url_content":
                                result = fetch_url_content(**arguments) if isinstance(arguments, dict) else fetch_url_content()
                            else:
                                result = f"Unknown tool: {tool_name}"
                            tool_results.append({
                                "role": "tool", 
                                "content": result,
                                'name': tool_name,
                            })
                        # Send tool results back to Ollama
                        messages = messages + [{
                            "role": "system",
                            "tool_calls": [{
                                'function': {
                                    'name': call.function.name,
                                    'arguments': call.function.arguments
                                }
                            } for call in tool_calls],
                        }] + tool_results
                        # print(f"Sending messages back to Ollama: {messages}")
                        print("Sending tool response for {[call.function.name for call in tool_calls]}")
                        tool_response = ollama_client.chat(
                            model=model,
                            messages=messages,
                        )
                        reply = tool_response.get("message", {}).get("content", "No response.")
                        think_match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL | re.IGNORECASE)
                        think_content = think_match.group(1).strip() if think_match else None
                        if think_match:
                            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
                    else:
                        reply = response.get("message", {}).get("content", "No response.")
                        think_match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL | re.IGNORECASE)
                        think_content = think_match.group(1).strip() if think_match else None
                        if think_match:
                            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
                except Exception as e:
                    import traceback
                    reply = f"Error: {e}\n{traceback.format_exc()}"
                    think_content = None

                # --- Append assistant reply to chat_history ---
                chat_history.append({"role": "assistant", "content": reply})

                # --- Update chat_histories ---
                if current_history_idx[0] is not None:
                    chat_histories[current_history_idx[0]]["history"] = list(chat_history)
                    refresh_chat_history_list()

                def update_chat():
                    thinking_frame.destroy()
                    Chat(
                        chat_container,
                        reply,
                        bg="#fffbe6",
                        think_content=think_content,
                        last_json=last_json.copy(),  # Always pass last_json
                        role="assistant"
                    ).pack(pady=2, padx=5, anchor="w", fill="x", expand=True)  # <-- add fill and expand
                root.after(0, update_chat)

            import threading
            threading.Thread(target=ollama_query, daemon=True).start()

        return "break"

    command_prompt.bind("<Return>", on_command_prompt_enter)

    # Enable mouse wheel scrolling for the chat container
    def _on_mousewheel(event):
        # For Windows and MacOS
        chat_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    def _on_mousewheel_linux(event):
        # For Linux (event.num 4=up, 5=down)
        if event.num == 4:
            chat_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            chat_canvas.yview_scroll(1, "units")

    # Bind mouse wheel events for all platforms
    chat_canvas.bind_all("<MouseWheel>", _on_mousewheel)        # Windows/Mac
    chat_canvas.bind_all("<Button-4>", _on_mousewheel_linux)    # Linux scroll up
    chat_canvas.bind_all("<Button-5>", _on_mousewheel_linux)    # Linux scroll down

    # --- At the end, before root.mainloop(), add a handler to save geometry on close ---
    def on_close():
        # Save current geometry (format: "WxH+X+Y")
        config["geometry"] = root.wm_geometry()
        config["system_prefix"] = system_prefix
        config["selected_model"] = model_var.get()  # Save selected model on close
        save_config(config)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    # --- Add this style definition before mainloop ---
    style = ttk.Style()
    style.configure("White.TFrame", background="#ffffff")

    root.mainloop()


if __name__ == "__main__":
    main()

