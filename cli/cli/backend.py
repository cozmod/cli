import subprocess
import json
import threading
import os
import re
from flask import Flask, render_template, request
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler
import gevent

# --- Global Process Management ---
# یک دیکشنری برای نگهداری پروسه‌های در حال اجرای gemini-cli برای هر کلاینت
cli_processes = {}

# --- Flask App Initialization ---
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = 'a-stateful-interactive-secret-key'

# --- WebSocket Logic ---

def send_to_frontend(ws, message_type, payload):
    """تابع کمکی برای فرمت‌بندی و ارسال پیام به فرانت‌اند."""
    if ws.closed:
        return
    try:
        message = json.dumps({"type": message_type, "payload": payload})
        ws.send(message)
    except Exception as e:
        print(f"Could not send message to frontend: {e}")

def stream_output(ws, stream):
    """
    در یک ترد جداگانه، خروجی یک استریم (stdout/stderr) را به صورت زنده می‌خواند
    و به فرانت‌اند ارسال می‌کند.
    """
    try:
        # الگوهای regex برای تشخیص خروجی‌های خاص
        tool_pattern = re.compile(r'\[TOOL\](.*?)\[/TOOL\]', re.DOTALL)
        thinking_pattern = re.compile(r'\[THINKING\](.*?)\[/THINKING\]', re.DOTALL)
        
        buffer = ""
        for line in iter(stream.readline, ''):
            buffer += line
            
            # بررسی الگوهای خاص در بافر
            tool_match = tool_pattern.search(buffer)
            thinking_match = thinking_pattern.search(buffer)
            
            if tool_match:
                # ارسال اطلاعات ابزار به فرانت‌اند
                tool_content = tool_match.group(1).strip()
                send_to_frontend(ws, 'tool_output', {'content': tool_content})
                # حذف محتوای ابزار از بافر
                buffer = buffer.replace(tool_match.group(0), '')
            
            if thinking_match:
                # ارسال اطلاعات تفکر به فرانت‌اند
                thinking_content = thinking_match.group(1).strip()
                send_to_frontend(ws, 'thinking_output', {'content': thinking_content})
                # حذف محتوای تفکر از بافر
                buffer = buffer.replace(thinking_match.group(0), '')
            
            # ارسال باقی‌مانده بافر به عنوان خروجی عادی
            if buffer.strip():
                send_to_frontend(ws, 'gemini_output', {'content': buffer})
                buffer = ""
                
        stream.close()
    except Exception as e:
        print(f"Error while streaming output: {e}")

def start_gemini_process(ws):
    """
    پروسه gemini-cli را به صورت تعاملی راه‌اندازی کرده و آن را زنده نگه می‌دارد.
    """
    client_id = id(ws)
    if client_id in cli_processes and cli_processes[client_id]:
        send_to_frontend(ws, 'terminal', {'content': 'Engine is already running.', 'type': 'output'})
        return

    try:
        send_to_frontend(ws, 'terminal', {'content': 'Starting gemini-cli engine...', 'type': 'output'})
        
        # تلاش برای یافتن دستور gemini-cli
        gemini_commands = [
            'gemini',                  # دستور اصلی
            'npx @google/gemini-cli',  # استفاده از npx
            'node ' + os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'original-cli', 'gemini-cli', 'packages', 'cli', 'src', 'gemini.tsx'),
            'npx gemini'
        ]
        
        command = None
        for cmd in gemini_commands:
            try:
                # بررسی اینکه آیا دستور قابل اجراست
                if ' ' in cmd:  # اگر دستور شامل فاصله است (مثل npx @google/gemini-cli یا node path/to/file)
                    # استفاده از shell=True برای دستورات پیچیده
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, shell=True)
                else:
                    subprocess.run([cmd, '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                command = cmd
                break
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        
        if not command:
            raise FileNotFoundError("Could not find gemini-cli command")
            
        # اجرای gemini-cli به عنوان یک پروسه دائمی
        if ' ' in command:  # اگر دستور شامل فاصله است
            # استفاده از shell=True برای دستورات پیچیده
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1,  # بافر خطی
                shell=True
            )
        else:
            process = subprocess.Popen(
                [command],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1  # بافر خطی
            )
            
        cli_processes[client_id] = process

        # ایجاد greenlet های gevent برای خواندن خروجی‌ها بدون بلاک کردن
        gevent.spawn(stream_output, ws, process.stdout)
        gevent.spawn(stream_output, ws, process.stderr)

        send_to_frontend(ws, 'engine_started', {})
        send_to_frontend(ws, 'terminal', {'content': f'Engine started successfully using {command}. Ready for commands.', 'type': 'output'})

    except FileNotFoundError:
        error_msg = "Error: 'gemini-cli' command not found. Make sure it is installed and in your system's PATH."
        print(error_msg)
        send_to_frontend(ws, 'terminal', {'content': error_msg, 'type': 'output'})
        send_to_frontend(ws, 'engine_stopped', {'error': True})
    except Exception as e:
        error_msg = f"An unexpected error occurred while starting the engine: {e}"
        print(error_msg)
        send_to_frontend(ws, 'terminal', {'content': error_msg, 'type': 'output'})
        send_to_frontend(ws, 'engine_stopped', {'error': True})


def send_command_to_process(ws, command):
    """
    یک دستور را به پروسه در حال اجرای gemini-cli ارسال می‌کند.
    """
    client_id = id(ws)
    process = cli_processes.get(client_id)

    if not process or process.poll() is not None:
        send_to_frontend(ws, 'terminal', {'content': 'Engine is not running. Please start the engine first.', 'type': 'output'})
        send_to_frontend(ws, 'engine_stopped', {})
        return
    
    try:
        # نمایش دستور در ترمینال فرانت‌اند
        send_to_frontend(ws, 'terminal', {'content': command, 'type': 'command'})
        
        # بررسی دستورات خاص Gemini CLI
        command_type = 'normal'
        if command.startswith('/'):
            command_type = 'slash_command'
            send_to_frontend(ws, 'terminal', {'content': f'Executing slash command: {command}', 'type': 'output'})
        elif command.startswith('@'):
            command_type = 'at_command'
            send_to_frontend(ws, 'terminal', {'content': f'Executing at command: {command}', 'type': 'output'})
        elif command.startswith('!'):
            command_type = 'shell_command'
            send_to_frontend(ws, 'terminal', {'content': f'Executing shell command: {command}', 'type': 'output'})
        
        # ارسال اطلاعات نوع دستور به فرانت‌اند
        send_to_frontend(ws, 'command_type', {'type': command_type, 'command': command})
        
        # ارسال دستور به stdin پروسه
        process.stdin.write(f"{command}\n")
        process.stdin.flush()
    except Exception as e:
        error_msg = f"Error sending command to process: {e}"
        print(error_msg)
        send_to_frontend(ws, 'terminal', {'content': error_msg, 'type': 'output'})

# --- Flask & WebSocket Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ws')
def websocket_route():
    ws = request.environ.get('wsgi.websocket')
    if not ws:
        return "Error: Expected a WebSocket request.", 400
    
    client_id = id(ws)
    print(f"WebSocket client connected: {client_id}")

    while not ws.closed:
        try:
            message = ws.receive()
            if message:
                data = json.loads(message)
                action = data.get('action')

                if action == 'start_engine':
                    start_gemini_process(ws)
                elif action == 'send_command':
                    command = data.get('command')
                    if command:
                        send_command_to_process(ws, command)
        except Exception as e:
            print(f"WebSocket connection for client {client_id} closed or error: {e}")
            break
    
    # --- Cleanup on disconnect ---
    process = cli_processes.pop(client_id, None)
    if process:
        print(f"Terminating gemini-cli process for client {client_id}.")
        process.terminate()
        process.wait()
    
    print(f"WebSocket client disconnected: {client_id}")
    return ''

if __name__ == '__main__':
    host = '127.0.0.1'
    port = 5000
    server = WSGIServer((host, port), app, handler_class=WebSocketHandler)
    print(f"🚀 عامل لینوکسی مرکز تحقیقات (نسخه تعاملی) آماده به کار است!")
    print(f"برای شروع، به آدرس زیر بروید:")
    print(f"http://{host}:{port}")
    server.serve_forever()
