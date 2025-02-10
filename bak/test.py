import yaml
import json
from typing import Any, Optional, Tuple, List

class LiteralString(str): pass

def literal_presenter(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

yaml.add_representer(LiteralString, literal_presenter)

def merge_yaml_arrays(yaml_str1: str, yaml_str2: str) -> str:
    """
    Merge two YAML strings by combining arrays at the deepest level.
    
    Args:
        yaml_str1 (str): First YAML string
        yaml_str2 (str): Second YAML string
        
    Returns:
        str: Merged YAML string
    
    Raises:
        yaml.YAMLError: If YAML parsing fails
        ValueError: If structure doesn't match expected format
    """
    try:
        # Parse YAML strings
        data1 = yaml.full_load(yaml_str1)
        print(yaml_str1)
        print(data1)
        print(yaml.dump(data1, allow_unicode=True))
        print(json.dumps(data1, indent=2))
        data2 = yaml.safe_load(yaml_str2)
        
        def find_deepest_array(data: Any, path: Optional[List] = None) -> Optional[Tuple[List, List]]:
            """
            Find the path to the deepest array in the YAML structure.
            
            Args:
                data: Current YAML data structure
                path: Current path in the structure
                
            Returns:
                Optional[Tuple[List, List]]: (path to deepest array, the array itself) or None
            """
            if path is None:
                path = []
                
            if isinstance(data, dict):
                for key, value in data.items():
                    new_path = path + [key]
                    result = find_deepest_array(value, new_path)
                    if result is not None:
                        return result
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    new_path = path + [i]
                    if isinstance(item, (dict, list)):
                        result = find_deepest_array(item, new_path)
                        if result is not None:
                            return result
                if any(isinstance(x, (dict, list)) for x in data):
                    return None
                return path, data
            return None
            
        def get_nested_value(data: Any, path: List) -> Any:
            """
            Get value at the specified nested path.
            
            Args:
                data: YAML data structure
                path: Path to the desired value
                
            Returns:
                Any: The value at the specified path
            """
            current = data
            for p in path:
                if isinstance(current, dict):
                    current = current[p]
                elif isinstance(current, list):
                    current = current[p]
            return current
            
        def set_nested_value(data: Any, path: List, value: Any) -> None:
            """
            Set value at the specified nested path.
            
            Args:
                data: YAML data structure
                path: Path where to set the value
                value: Value to set
            """
            current = data
            for p in path[:-1]:
                if isinstance(current, dict):
                    current = current[p]
                elif isinstance(current, list):
                    current = current[p]
            
            last = path[-1]
            if isinstance(current, dict):
                current[last] = value
            elif isinstance(current, list):
                current[last] = value

        def process_multiline_strings(data: Any) -> Any:
            """
            Process the data structure to handle multiline strings properly.
            
            Args:
                data: YAML data structure
                
            Returns:
                Processed YAML data structure
            """
            if isinstance(data, dict):
                return {k: process_multiline_strings(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [process_multiline_strings(item) for item in data]
            elif isinstance(data, str) and '\n' in data:
                return LiteralString(data.rstrip())

            return data

        # Find the deepest arrays in both structures
        result1 = find_deepest_array(data1)
        result2 = find_deepest_array(data2)
        
        if result1 is None or result2 is None:
            raise ValueError("Could not find arrays to merge in the YAML structure")
            
        path1, array1 = result1
        path2, array2 = result2
            
        # Get the arrays to merge
        target_array1 = get_nested_value(data1, path1)
        target_array2 = get_nested_value(data2, path2)

        # Merge arrays
        merged_array = []
        for item in target_array1:
            if isinstance(item, str) and '\n' in item:
                merged_array.append(LiteralString(item.rstrip()))
            else:
                merged_array.append(item)
        
        for item in target_array2:
            if isinstance(item, str) and '\n' in item:
                merged_array.append(LiteralString(item.rstrip()))
            else:
                merged_array.append(item)
        
        # Create new structure with merged array
        result = data1.copy()
        set_nested_value(result, path1, merged_array)
        
        # Process all multiline strings in the result
        result = process_multiline_strings(result)
        
        # Convert back to YAML string with proper formatting
        return yaml.dump(result, allow_unicode=True, sort_keys=False, indent=2, default_flow_style=False)
        
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error parsing YAML: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error merging YAML: {str(e)}")

# Example usage
if __name__ == "__main__":
    yaml_str1 = """
a:
- a1:
  - a2:
      - typ:aaa
        blu:bbb
      - typ:ccc
        blu:ddd
"""

    yaml_str2 = """
a:
- a1:
  - a2:
      - typ:TTT
        blu:RRR
"""

    try:
        result = merge_yaml_arrays(yaml_str1, yaml_str2)
        print("Merged YAML:")
        print(result)
    except Exception as e:
        print(f"Error: {str(e)}")