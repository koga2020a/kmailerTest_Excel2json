#!/usr/bin/env python3
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum, auto
import csv
import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path

# 基本的な型定義
class CellType(Enum):
    ARRAY = auto()
    OBJECT = auto()
    PRIMITIVE = auto()
    LAYOUT_MARKER = auto()
    EMPTY = auto()

@dataclass
class Position:
    row: int
    col: int

    def right(self) -> 'Position':
        return Position(self.row, self.col + 1)
    
    def down(self) -> 'Position':
        return Position(self.row + 1, self.col)

# データホルダー関連のクラス
class DataHolder(ABC):
    """データを保持する基底クラス"""
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def accept_data(self, data: str) -> None:
        pass

class PrimitiveHolder(DataHolder):
    """プリミティブな値を保持するクラス"""
    def __init__(self, name: str):
        super().__init__(name)
        self.value = None
    
    def accept_data(self, data: str) -> None:
        if not data or data.isspace():
            self.value = None
            return

        data = data.strip()
        if data.startswith('*'):
            data = data[1:]

        if data.lower() == 'true':
            self.value = True
        elif data.lower() == 'false':
            self.value = False
        elif data.replace('.', '').isdigit():
            self.value = float(data) if '.' in data else int(data)
        else:
            self.value = data
    
    def to_dict(self) -> Any:
        return self.value

class ArrayHolder(DataHolder):
    """配列を保持するクラス"""
    def __init__(self, name: str, element_type: 'StructureElement'):
        super().__init__(name)
        self.element_type = element_type
        self.elements: List[DataHolder] = []
        self.current_element: Optional[DataHolder] = None
    
    def accept_data(self, data: str) -> None:
        if not self.current_element or data.startswith('*'):
            self.current_element = self.element_type.create_data_holder()
            self.elements.append(self.current_element)
        self.current_element.accept_data(data)
    
    def to_dict(self) -> List[Dict[str, Any]]:
        return [element.to_dict() for element in self.elements]

class ObjectHolder(DataHolder):
    """オブジェクトを保持するクラス"""
    def __init__(self, name: str, field_types: Dict[str, 'StructureElement']):
        super().__init__(name)
        self.fields: Dict[str, DataHolder] = {
            name: field_type.create_data_holder()
            for name, field_type in field_types.items()
        }
        self.current_field = None
    
    def accept_data(self, data: str) -> None:
        if self.current_field and self.current_field in self.fields:
            self.fields[self.current_field].accept_data(data)
    
    def set_current_field(self, field_name: str) -> None:
        self.current_field = field_name
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            name: holder.to_dict()
            for name, holder in self.fields.items()
        }

# 構造要素関連のクラス
class StructureElement(ABC):
    """構造を表現する基底クラス"""
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def create_data_holder(self):
        pass

class PrimitiveElement(StructureElement):
    """プリミティブな値を表現する構造要素"""
    def create_data_holder(self):
        return PrimitiveHolder(self.name)

class ArrayElement(StructureElement):
    """配列を表現する構造要素"""
    def __init__(self, name: str, element_type: StructureElement):
        super().__init__(name)
        self.element_type = element_type
    
    def create_data_holder(self):
        return ArrayHolder(self.name, self.element_type)

class ObjectElement(StructureElement):
    """オブジェクトを表現する構造要素"""
    def __init__(self, name: str, fields: Dict[str, StructureElement]):
        super().__init__(name)
        self.fields = fields
    
    def create_data_holder(self):
        return ObjectHolder(self.name, self.fields)

# レイアウト解析関連のクラス
class LayoutCell:
    """レイアウトのセルを表現するクラス"""
    def __init__(self, value: str, position: Position, layout_grid: 'LayoutGrid'):
        self.value = value.strip()
        self.position = position
        self.grid = layout_grid
        self.cell_type = self._determine_type()
        self.processed = False
    
    def _determine_type(self) -> CellType:
        if not self.value:
            return CellType.EMPTY
        if self.value == '<':
            return CellType.LAYOUT_MARKER
        if self.value.endswith('[]'):
            return CellType.ARRAY
        if self.value in {'LAYOUT', 'DATA'}:
            return CellType.EMPTY
        return CellType.PRIMITIVE

    def get_right_cell(self) -> Optional['LayoutCell']:
        return self.grid.get_cell(self.position.right())

    def get_down_cell(self) -> Optional['LayoutCell']:
        return self.grid.get_cell(self.position.down())

    def get_left_cell(self) -> Optional['LayoutCell']:
        return self.grid.get_cell(Position(self.position.row, self.position.col - 1))

    def get_up_cell(self) -> Optional['LayoutCell']:
        return self.grid.get_cell(Position(self.position.row - 1, self.position.col))

    def investigate_structure(self) -> Optional[StructureElement]:
        if self.processed or self.cell_type == CellType.EMPTY:
            return None

        print(f"\n▼ セル「{self.value}」({self.cell_type.name})の解析開始")
        print("  └ 処理済みフラグ: {self.processed}")
        self.processed = True

        if self.cell_type == CellType.ARRAY:
            # Step 1: 配列セルの場合、即座に下方向の解析を実行
            print("  ├ Step 1: 下方向の構造解析")
            down_cell = self.get_down_cell()
            vertical_fields = {}
            
            while down_cell:
                if down_cell.cell_type == CellType.EMPTY:
                    print("  │   └ 空行をスキップ")
                else:
                    print(f"  │   └ フィールドを検出: {down_cell.value} ({down_cell.cell_type.name})")
                    if not down_cell.processed:
                        element = down_cell.investigate_structure()
                        if element:
                            vertical_fields[element.name] = element
                            print(f"  │     └ 要素を追加: {element.name}")
                down_cell = down_cell.get_down_cell()
            
            print("  │   └ 下方向の解析完了")
            
            # Step 2: 横方向の解析
            print("  ├ Step 2: 横方向の解析")
            right_cell = self.get_right_cell()
            
            if right_cell and right_cell.cell_type == CellType.LAYOUT_MARKER:
                return self._investigate_array(right_cell, vertical_fields)
            else:
                print("  │ └ プリミティブ配列として処理")
                return ArrayElement(self.value[:-2], PrimitiveElement(f"{self.value[:-2]}_item"))

        elif self.cell_type == CellType.LAYOUT_MARKER:
            # レイアウトマーカーの処理は変更なし
            print("  ├ Step 1: 左方向に形式定義を探索")
            left_cell = self.get_left_cell()
            while left_cell and left_cell.cell_type == CellType.EMPTY:
                print("  │   └ 空セルをスキップ")
                left_cell = left_cell.get_left_cell()
            
            if left_cell and left_cell.cell_type == CellType.ARRAY:
                print(f"  │   └ 形式定義を発見: {left_cell.value}")
                return left_cell.investigate_structure()
        
        elif self.cell_type == CellType.PRIMITIVE:
            print("  └ プリミティブ要素として処理")
            return PrimitiveElement(self.value)
        
        return None

    def _investigate_array(self, marker_cell: 'LayoutCell', vertical_fields: Dict[str, StructureElement]) -> ArrayElement:
        base_name = self.value[:-2]
        print("  │ └ 右セルがレイアウトマーカー(<)のため、同じキーとして処理")
        
        # 連続するマーカーを数える
        marker_count = 1
        current_marker = marker_cell
        next_cell = current_marker.get_right_cell()
        
        while next_cell and next_cell.cell_type == CellType.LAYOUT_MARKER:
            marker_count += 1
            current_marker = next_cell
            next_cell = current_marker.get_right_cell()
            print(f"  │   └ {marker_count}個目のレイアウトマーカーを検出")
        
        print(f"  │   └ 合計{marker_count}個のレイアウトマーカーでネスト")
        
        # 横方向のフィールドを追加
        fields = vertical_fields.copy()  # 縦方向で見つかったフィールドを基にする
        current_cell = current_marker.get_right_cell()
        
        while current_cell and not current_cell.processed:
            if current_cell.cell_type != CellType.EMPTY:
                print(f"    └ 配列内フィールド検出: {current_cell.value}")
                element = current_cell.investigate_structure()
                if element:
                    fields[element.name] = element
            current_cell = current_cell.get_right_cell()
        
        return ArrayElement(base_name, ObjectElement(f"{base_name}_item", fields))

class LayoutGrid:
    """レイアウトグリッド全体を管理するクラス"""
    def __init__(self, layout_rows: List[List[str]]):
        self.grid: List[List[LayoutCell]] = []
        self._build_grid(layout_rows)

    def _build_grid(self, layout_rows: List[List[str]]):
        for row_idx, row in enumerate(layout_rows):
            grid_row = []
            for col_idx, value in enumerate(row):
                pos = Position(row_idx, col_idx)
                cell = LayoutCell(value, pos, self)
                grid_row.append(cell)
            self.grid.append(grid_row)

    def get_cell(self, pos: Position) -> Optional[LayoutCell]:
        if 0 <= pos.row < len(self.grid) and 0 <= pos.col < len(self.grid[0]):
            return self.grid[pos.row][pos.col]
        return None

    def analyze_structure(self) -> StructureElement:
        fields = {}
        start_col = 2
        current_cell = self.get_cell(Position(0, start_col))
        
        while current_cell:
            if current_cell.cell_type != CellType.EMPTY:
                element = current_cell.investigate_structure()
                if element:
                    fields[element.name] = element
            current_cell = current_cell.get_right_cell()
        
        return ObjectElement("root", fields)

# データ処理関連のクラス
class DataRowCell:
    """データ行のセルを表現するクラス"""
    def __init__(self, value: str, position: Position, data_grid: 'DataGrid'):
        self.value = value.strip()
        self.position = position
        self.grid = data_grid
        self.is_continuation = bool(value.startswith('*'))
    
    def get_right_cell(self) -> Optional['DataRowCell']:
        return self.grid.get_cell(self.position.right())

class DataGrid:
    """データグリッド全体を管理するクラス"""
    def __init__(self, data_rows: List[List[str]], structure: StructureElement):
        self.grid: List[List[DataRowCell]] = []
        self.structure = structure
        self._build_grid(data_rows)
    
    def _build_grid(self, data_rows: List[List[str]]):
        for row_idx, row in enumerate(data_rows):
            grid_row = []
            for col_idx, value in enumerate(row):
                pos = Position(row_idx, col_idx)
                cell = DataRowCell(value, pos, self)
                grid_row.append(cell)
            self.grid.append(grid_row)
    
    def get_cell(self, pos: Position) -> Optional[DataRowCell]:
        if 0 <= pos.row < len(self.grid) and 0 <= pos.col < len(self.grid[0]):
            return self.grid[pos.row][pos.col]
        return None
    
    def parse_data(self) -> List[DataHolder]:
        result = []
        current_holder = None
        
        for row in self.grid:
            if not row[1].value.strip():
                if current_holder:
                    result.append(current_holder)
                current_holder = self.structure.create_data_holder()
                self._process_data_row(current_holder, row)
            else:
                if current_holder:
                    self._process_data_row(current_holder, row)
        
        if current_holder:
            result.append(current_holder)
        
        return result
    
    def _process_data_row(self, holder: DataHolder, row: List[DataRowCell]):
        start_col = 2
        current_cell = row[start_col]
        current_field_idx = 0
        
        def process_holder(h: DataHolder, cell: DataRowCell) -> int:
            nonlocal current_field_idx
            
            if isinstance(h, ObjectHolder):
                fields = list(h.fields.items())
                processed_count = 0
                while current_field_idx < len(fields) and cell:
                    field_name, field_holder = fields[current_field_idx]
                    count = process_holder(field_holder, cell)
                    for _ in range(count):
                        cell = cell.get_right_cell() if cell else None
                    processed_count += count
                    current_field_idx += 1
                return processed_count
            
            elif isinstance(h, ArrayHolder):
                if cell.is_continuation or not h.current_element:
                    h.accept_data(cell.value)
                return 1
            
            else:  # PrimitiveHolder
                h.accept_data(cell.value)
                return 1
        
        while current_cell:
            current_field_idx = 0
            cells_processed = process_holder(holder, current_cell)
            for _ in range(cells_processed):
                current_cell = current_cell.get_right_cell()

def convert_csv_file_to_json(input_path: str, output_path: str) -> None:
    """CSVファイルを読み込んでJSONファイルに変換"""
    # CSVファイルを読み込む
    with open(input_path, 'r', encoding='utf-8') as f:
        csv_content = f.read()
    
    # CSVを解析
    reader = csv.reader(csv_content.splitlines())
    rows = list(reader)
    
    # レイアウト行とデータ行を分離
    layout_rows = [row for row in rows if row[0] == 'LAYOUT']
    data_rows = [row for row in rows if row[0] == 'DATA']
    
    # 構造を解析
    grid = LayoutGrid(layout_rows)
    structure = grid.analyze_structure()
    
    # データを解析
    data_grid = DataGrid(data_rows, structure)
    data_holders = data_grid.parse_data()
    
    # JSON形式に変換して保存
    result = [holder.to_dict() for holder in data_holders]
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

def main():
    """メイン処理"""
    if len(sys.argv) != 3:
        print("Usage: python csv_to_json.py input.csv output.json")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    try:
        convert_csv_file_to_json(input_path, output_path)
        print(f"Successfully converted {input_path} to {output_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()