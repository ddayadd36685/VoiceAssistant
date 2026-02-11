from voice_assistant.logger import setup_logger, console
from voice_assistant.state_machine import VoiceAssistant

def main():
    console.print("[bold green]Initializing Voice Assistant...[/bold green]")
    setup_logger() # Initialize global logging config
    
    try:
        app = VoiceAssistant()
        app.run()
    except KeyboardInterrupt:
        console.print("[bold red]Stopped by user.[/bold red]")

if __name__ == "__main__":
    main()
