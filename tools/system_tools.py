import os
import subprocess
from typing import List, Optional

def execute_command(command: str) -> str:
    """
    Execute a shell command in the terminal and return the output.
    :param command: The shell command to execute.
    """
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout or "Command executed successfully (no output)."
        else:
            return f"Error ({result.returncode}): {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error: {str(e)}"

def list_files(directory: str = ".") -> str:
    """
    List files and directories in the specified path.
    :param directory: The directory to list.
    """
    try:
        files = os.listdir(directory)
        return "\n".join(files)
    except Exception as e:
        return f"Error: {str(e)}"

def read_file_content(file_path: str) -> str:
    """
    Read the content of a file.
    :param file_path: The path to the file.
    """
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"

def write_to_file(file_path: str, content: str) -> str:
    """
    Write content to a file.
    :param file_path: The path to the file.
    :param content: The content to write.
    """
    try:
        with open(file_path, "w") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error: {str(e)}"
