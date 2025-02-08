import csv
import json
import sys
import string
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple


class CsvPreprocessor:
    """CSVの前処理を行うクラス"""
    def __init__(self, csv_filename: str):
        self.filename = csv_filename
        self.raw_data: List[List[str]] = []
        self.layout_ranges: List[Tuple[int, int]] = []  # [(開始行, 終了行), ...]

    def load_csv(self) -> None:
        """CSVファイルを読み込む"""
        with open(self.filename, newline='', encoding='utf-8') as f:
            self.raw_data = list(csv.reader(f))

    def extract_layout_sections(self) -> None:
        """LAYOUTセクションの範囲を特定"""
        current_start = None
        
        for i, row in enumerate(self.raw_data):
            if not row:  # 空行をスキップ
                continue
                
            is_layout = row[0].strip().upper() == "LAYOUT"
            
            if is_layout and current_start is None:
                current_start = i
            elif not is_layout and current_start is not None:
                self.layout_ranges.append((current_start, i - 1))
                current_start = None
        
        # 最後のセクションが終了マークなしで終わっている場合
        if current_start is not None:
            self.layout_ranges.append((current_start, len(self.raw_data) - 1))

    def get_processed_data(self) -> List[List[List[str]]]:
        """各LAYOUTセクションのデータを1列目を除いて取得"""
        processed_sections = []
        
        for start, end in self.layout_ranges:
            # 範囲内の行を取得し、1列目を除去
            section_data = [
                row[1:] for row in self.raw_data[start:end + 1]
                if row and len(row) > 1  # 少なくとも2列あることを確認
            ]
            if section_data:  # 空でないセクションのみ追加
                processed_sections.append(section_data)
        
        return processed_sections


@dataclass
class Position:
    """セルの位置を表すクラス"""
    row: int
    col: int

    def to_excel_label(self) -> str:
        """行・列をA1のような表記に変換"""
        col_label = string.ascii_uppercase[self.col]
        return f"{col_label}{self.row + 1}"

    def get_below(self) -> 'Position':
        """下のセルの位置を取得"""
        return Position(self.row + 1, self.col)

    def get_right(self) -> 'Position':
        """右のセルの位置を取得"""
        return Position(self.row, self.col + 1)


class CellGroup:
    """セルのグループを表すクラス"""
    def __init__(self, group_id: int, name: str):
        self.id = group_id
        self.name = name
        self.parent: Optional['CellGroup'] = None
        self.children: List['CellGroup'] = []
        self.cells: List['Cell'] = []

    def add_cell(self, cell: 'Cell') -> None:
        """セルをグループに追加"""
        self.cells.append(cell)
        cell.set_group(self)

    def set_parent(self, parent: 'CellGroup') -> None:
        """親グループを設定"""
        if self.parent is None and parent.id != self.id:
            self.parent = parent
            if self not in parent.children:
                parent.children.append(self)

    def to_dict(self) -> dict:
        """JSON変換用の辞書を返す"""
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent.id if self.parent else None,
            "parent_name": self.parent.name if self.parent else None,
            "children": [child.id for child in self.children]
        }


class Cell:
    """CSVの各セルを表すクラス"""
    def __init__(self, position: Position, value: str):
        self.position = position
        self.value = value.strip() if value else None
        self.group: Optional[CellGroup] = None

    def set_group(self, group: CellGroup) -> None:
        """グループを設定"""
        self.group = group

    def is_empty(self) -> bool:
        """セルが空かどうかを判定"""
        return self.value is None or self.value == ""

    def is_extension(self) -> bool:
        """セルが前のグループの延長（<）かどうかを判定"""
        return self.value == "<"

    def to_dict(self) -> dict:
        """JSON変換用の辞書を返す"""
        return {
            "position": self.position.to_excel_label(),
            "value": self.value,
            "group_id": self.group.id if self.group else None,
            "group_name": self.group.name if self.group else None,
            "parent_id": self.group.parent.id if self.group and self.group.parent else None,
            "parent_name": self.group.parent.name if self.group and self.group.parent else None
        }


class CsvMatrix:
    """CSV全体の構造を表すクラス"""
    def __init__(self):
        self.cells: Dict[str, Cell] = {}
        self.max_row = 0
        self.max_col = 0

    def add_cell(self, cell: Cell) -> None:
        """セルを追加"""
        self.cells[cell.position.to_excel_label()] = cell

    def get_cell(self, position: Position) -> Optional[Cell]:
        """指定された位置のセルを取得"""
        label = position.to_excel_label()
        return self.cells.get(label)

    def get_cell_below(self, cell: Cell) -> Optional[Cell]:
        """セルの下のセルを取得"""
        below_pos = cell.position.get_below()
        if below_pos.row >= self.max_row:
            return None
        return self.get_cell(below_pos)

    def get_cell_right(self, cell: Cell) -> Optional[Cell]:
        """セルの右のセルを取得"""
        right_pos = cell.position.get_right()
        if right_pos.col >= self.max_col:
            return None
        return self.get_cell(right_pos)


class GroupManager:
    """グループの管理を行うクラス"""
    def __init__(self):
        self.groups: Dict[int, CellGroup] = {}
        self.next_group_id = 1

    def create_group(self, name: str) -> CellGroup:
        """新しいグループを作成"""
        group = CellGroup(self.next_group_id, name)
        self.groups[group.id] = group
        self.next_group_id += 1
        return group

    def get_group(self, group_id: int) -> Optional[CellGroup]:
        """指定されたIDのグループを取得"""
        return self.groups.get(group_id)


class CsvStructure:
    """CSV構造全体を管理するクラス"""
    def __init__(self):
        self.matrix = CsvMatrix()
        self.group_manager = GroupManager()

    def process_csv(self, csv_filename: str) -> List[dict]:
        """CSVファイルを処理し、各LAYOUTセクションの構造を解析"""
        preprocessor = CsvPreprocessor(csv_filename)
        preprocessor.load_csv()
        preprocessor.extract_layout_sections()
        
        sections_data = preprocessor.get_processed_data()
        results = []
        
        for section_data in sections_data:
            self.matrix = CsvMatrix()  # 新しいセクションごとにマトリックスをリセット
            self.group_manager = GroupManager()  # グループマネージャーもリセット
            self._process_section(section_data)
            results.append(self.to_dict())
        
        return results

    def _process_section(self, section_data: List[List[str]]) -> None:
        """セクションデータを処理"""
        self.matrix.max_row = len(section_data)
        self.matrix.max_col = max(len(row) for row in section_data)

        # セルの作成
        for row_idx, row in enumerate(section_data):
            for col_idx, value in enumerate(row):
                position = Position(row_idx, col_idx)
                cell = Cell(position, value)
                self.matrix.add_cell(cell)

        self._group_cells()
        self._set_parents()

    def _group_cells(self) -> None:
        """セルをグループ化"""
        prev_group = None

        for row in range(self.matrix.max_row):
            for col in range(self.matrix.max_col):
                position = Position(row, col)
                cell = self.matrix.get_cell(position)
                
                if not cell or cell.is_empty():
                    continue

                if cell.is_extension() and prev_group:
                    prev_group.add_cell(cell)
                elif not cell.is_extension():
                    prev_group = self.group_manager.create_group(cell.value)
                    prev_group.add_cell(cell)

    def _set_parents(self) -> None:
        """親子関係を設定"""
        sorted_groups = sorted(
            self.group_manager.groups.values(),
            key=lambda g: min(c.position.row for c in g.cells)
        )

        for group in sorted_groups:
            for cell in group.cells:
                current_cell = self.matrix.get_cell_below(cell)
                while current_cell:
                    if current_cell.group and current_cell.group.id != group.id:
                        current_cell.group.set_parent(group)
                        break
                    current_cell = self.matrix.get_cell_below(current_cell)

    def to_dict(self) -> dict:
        """JSON変換用の辞書を返す"""
        return {
            "cells": {
                pos: cell.to_dict()
                for pos, cell in self.matrix.cells.items()
            },
            "groups": {
                group.id: group.to_dict()
                for group in self.group_manager.groups.values()
            }
        }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py csv_filename", file=sys.stderr)
        sys.exit(1)

    filename = sys.argv[1]
    csv_structure = CsvStructure()
    results = csv_structure.process_csv(filename)
    
    # 各セクションの結果を出力
    for i, result in enumerate(results, 1):
        print(f"\nSection {i}:")
        print(json.dumps(result, indent=4, ensure_ascii=False))