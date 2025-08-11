#!/usr/bin/env python3
"""
Simplified script to gather FRC-PTP-GUI project files for Grok 4 website prompts.
This version creates a more concise format that's easier to paste into Grok 4.
"""

import json
from pathlib import Path

def read_file_content(file_path):
    """Read file content and return as string."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def gather_project_files():
    """Gather all relevant project files."""
    project_files = {}
    project_root = Path(".")
    
    # Python files
    for py_file in project_root.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            relative_path = py_file.relative_to(project_root)
            content = read_file_content(py_file)
            project_files[f"python:{relative_path}"] = content
    
    # Example project files
    example_dir = Path("example_project")
    if example_dir.exists():
        # Config and README
        for file_name in ["config.json", "README.md"]:
            file_path = example_dir / file_name
            if file_path.exists():
                content = read_file_content(file_path)
                project_files[f"example:{file_name}"] = content
        
        # Path files
        paths_dir = example_dir / "paths"
        if paths_dir.exists():
            for path_file in paths_dir.glob("*.json"):
                relative_path = path_file.relative_to(example_dir)
                content = read_file_content(path_file)
                project_files[f"example:{relative_path}"] = content
    
    return project_files

def create_simple_prompt():
    """Create a simplified prompt for Grok 4 website."""
    
    project_files = gather_project_files()
    
    prompt = """# FRC-PTP-GUI Project Analysis

## Project Description
This is a Python GUI application for FRC (FIRST Robotics Competition) path planning and trajectory optimization using PySide6.

## Project Structure
- main.py - Application entry point
- ui/ - User interface components (main_window.py, sidebar.py, canvas.py, config_dialog.py)
- models/ - Data models (path_model.py)
- utils/ - Utilities (project_manager.py)
- example_project/ - Example configuration and path files

## Files to Analyze

"""
    
    # Add file contents in a more compact format
    for file_key, content in project_files.items():
        file_type, file_path = file_key.split(":", 1)
        prompt += f"### {file_path}\n"
        prompt += f"```\n{content}\n```\n\n"
    
    prompt += """## Analysis Request
Please analyze this FRC robotics path planning GUI application and provide:
1. Code architecture overview
2. Key components and their roles
3. Data flow analysis
4. UI structure analysis
5. Path management approach
6. Improvement suggestions
7. Dependencies and usage instructions

Provide a comprehensive analysis suitable for understanding and improving this application.
"""
    
    return prompt

def main():
    """Generate and save the simplified prompt."""
    print("🔍 Creating simplified Grok 4 prompt...")
    
    prompt = create_simple_prompt()
    
    # Save simplified prompt
    try:
        with open("grok_simple.txt", 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"✅ Simplified prompt saved to grok_simple.txt")
        print(f"📝 Length: {len(prompt)} characters")
        
        # Show file sizes for reference
        project_files = gather_project_files()
        print(f"📁 Total files gathered: {len(project_files)}")
        
        # Create a summary file
        summary = {
            "project": "FRC-PTP-GUI",
            "description": "Python GUI for FRC path planning",
            "files": list(project_files.keys()),
            "total_files": len(project_files)
        }
        
        with open("grok_summary.json", 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        print("📋 Summary saved to grok_summary.json")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
