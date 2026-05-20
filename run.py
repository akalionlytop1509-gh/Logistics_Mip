import subprocess
import sys
import os
import time
from threading import Thread

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def print_banner():
    banner = """
    ==================================================
    🚀 PRO HUB - LOGISTICS OPTIMIZER SYSTEM 🚀
    ==================================================
    Backend:  http://127.0.0.1:8000
    Frontend: http://localhost:8501
    ==================================================
    Press Ctrl+C to stop both services.
    """
    print(banner)

def stream_output(process, prefix):
    """Streams output from a process to the console with a prefix."""
    for line in iter(process.stdout.readline, ''):
        if line:
            print(f"[{prefix}] {line.strip()}")
    process.stdout.close()

def main():
    print_banner()

    # Ensure we are in the project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    # 1. Start Backend (FastAPI)
    backend_cmd = [
        sys.executable, "-m", "uvicorn", 
        "backend.app.main:app", 
        "--host", "127.0.0.1", 
        "--port", "8000", 
        "--reload",
        "--reload-dir", "backend"
    ]
    
    # 2. Start Frontend (Streamlit)
    frontend_cmd = [
        sys.executable, "-m", "streamlit", 
        "run", "frontend/app.py",
        "--server.port", "8501"
    ]

    try:
        # Launch processes
        backend_proc = subprocess.Popen(
            backend_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1
        )
        
        frontend_proc = subprocess.Popen(
            frontend_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1
        )

        # Start output streaming threads
        t1 = Thread(target=stream_output, args=(backend_proc, "BACKEND"), daemon=True)
        t2 = Thread(target=stream_output, args=(frontend_proc, "FRONTEND"), daemon=True)
        t1.start()
        t2.start()

        # Keep the main script alive and restart backend if it crashes
        while True:
            time.sleep(2)
            if backend_proc.poll() is not None:
                print("🔄 Backend stopped or reloading... Restarting in 2s...")
                time.sleep(2)
                backend_proc = subprocess.Popen(
                    backend_cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT, 
                    text=True,
                    bufsize=1
                )
                Thread(target=stream_output, args=(backend_proc, "BACKEND"), daemon=True).start()
            
            if frontend_proc.poll() is not None:
                print("❌ Frontend process stopped. Exiting...")
                break

    except KeyboardInterrupt:
        print("\n🛑 Stopping services...")
    finally:
        # Terminate processes on exit
        if 'backend_proc' in locals():
            backend_proc.terminate()
        if 'frontend_proc' in locals():
            frontend_proc.terminate()
        print("✅ Shutdown complete. Goodbye!")

if __name__ == "__main__":
    main()
