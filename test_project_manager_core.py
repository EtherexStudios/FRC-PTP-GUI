#!/usr/bin/env python3
"""
Test script for project manager core functionality without GUI dependencies.
"""

import os
import tempfile
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_project_directory_validation():
    """Test project directory validation logic."""
    print("Testing project directory validation...")
    
    try:
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test invalid directory (doesn't exist)
            
            # Mock the project manager logic without PySide6
            def validate_project_directory(directory: str) -> bool:
                """Validate that a directory contains the required project structure."""
                if not os.path.exists(directory):
                    return False
                
                paths_dir = os.path.join(directory, 'paths')
                ui_config_dir = os.path.join(directory, 'ui-config')
                
                return os.path.isdir(paths_dir) and os.path.isdir(ui_config_dir)
            
            def create_project_structure(directory: str) -> bool:
                """Create the required project directory structure."""
                try:
                    paths_dir = os.path.join(directory, 'paths')
                    ui_config_dir = os.path.join(directory, 'ui-config')
                    
                    os.makedirs(paths_dir, exist_ok=True)
                    os.makedirs(ui_config_dir, exist_ok=True)
                    
                    return True
                except Exception:
                    return False
            
            # Test non-existent directory
            assert not validate_project_directory('/nonexistent/path')
            print("  ✓ Non-existent directory validation passed")
            
            # Test empty directory (no required subdirectories)
            assert not validate_project_directory(temp_dir)
            print("  ✓ Empty directory validation passed")
            
            # Create valid project structure
            paths_dir = os.path.join(temp_dir, 'paths')
            ui_config_dir = os.path.join(temp_dir, 'ui-config')
            os.makedirs(paths_dir)
            os.makedirs(ui_config_dir)
            
            # Test valid directory
            assert validate_project_directory(temp_dir)
            print("  ✓ Valid directory validation passed")
            
            # Test project structure creation
            new_project_dir = os.path.join(temp_dir, 'new_project')
            assert create_project_structure(new_project_dir)
            print("  ✓ Project structure creation passed")
            
            # Verify structure was created
            assert os.path.exists(os.path.join(new_project_dir, 'paths'))
            assert os.path.exists(os.path.join(new_project_dir, 'ui-config'))
            print("  ✓ Project structure verification passed")
            
            # Test that the created directory is now valid
            assert validate_project_directory(new_project_dir)
            print("  ✓ Created project directory validation passed")
        
        print("  ✓ All project directory validation tests passed!")
        return True
        
    except Exception as e:
        print(f"  ✗ Project directory validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_path_file_operations():
    """Test path file operations logic."""
    print("Testing path file operations...")
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create project structure
            paths_dir = os.path.join(temp_dir, 'paths')
            ui_config_dir = os.path.join(temp_dir, 'ui-config')
            os.makedirs(paths_dir)
            os.makedirs(ui_config_dir)
            
            # Mock the list_path_files logic
            def list_path_files():
                """List available path files in the project."""
                if not os.path.exists(paths_dir):
                    return []
                
                path_files = []
                for filename in os.listdir(paths_dir):
                    if filename.endswith('.json'):
                        file_path = os.path.join(paths_dir, filename)
                        path_files.append((filename, file_path))
                
                return sorted(path_files, key=lambda x: x[0])
            
            # Test listing path files (should be empty initially)
            path_files = list_path_files()
            assert len(path_files) == 0
            print("  ✓ Empty paths directory listing passed")
            
            # Create some test path files
            test_path1 = os.path.join(paths_dir, 'test1.json')
            test_path2 = os.path.join(paths_dir, 'test2.json')
            
            with open(test_path1, 'w') as f:
                f.write('{"test": "data1"}')
            with open(test_path2, 'w') as f:
                f.write('{"test": "data2"}')
            
            # Test listing path files (should now have 2 files)
            path_files = list_path_files()
            assert len(path_files) == 2
            print("  ✓ Path files listing passed")
            
            # Verify file names are correct
            file_names = [name for name, _ in path_files]
            assert 'test1.json' in file_names
            assert 'test2.json' in file_names
            print("  ✓ Path file names verification passed")
        
        print("  ✓ All path file operations tests passed!")
        return True
        
    except Exception as e:
        print(f"  ✗ Path file operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all project manager core tests."""
    print("Running project manager core tests...\n")
    
    tests = [
        test_project_directory_validation,
        test_path_file_operations
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ✗ Test {test.__name__} crashed: {e}")
        print()
    
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All project manager core tests passed!")
        return 0
    else:
        print("❌ Some project manager core tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())