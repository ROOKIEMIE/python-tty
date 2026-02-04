import copy
import shutil
from typing import Any, List, Optional, Sequence


class Cell:
    def __init__(self, data):
        self.data = data
        self.data_str = str(self.data)
        self.data_width = len(self.data_str)
        self.padding = ""

    def update_max_width(self, padding_len: int):
        if padding_len > 0:
            self.padding = " " * padding_len

    def __str__(self):
        return "".join([self.data_str, self.padding])


class HeaderCell(Cell):
    def __init__(self, data, seq="-"):
        super().__init__(data)
        self.seq_str = self.data_width * seq
        self.data_str = str(self.data)

    def get_seq_str(self):
        return "".join([self.seq_str, self.padding])


class Table:
    def __init__(self, header: Sequence[Any], data: Sequence[Sequence[Any]], title="",
                 title_indent=0, data_indent=4, data_seq_len=4,
                 title_seq="=", header_seq="-", header_footer=True,
                 wrap: bool = False, wrap_col_idx: Optional[int] = None,
                 wrap_min_width: int = 10, terminal_width: Optional[int] = None,
                 truncate: bool = True):
        """Render a text table for TTY output.

        Args:
            header: Column headers (sequence of values).
            data: Table rows (sequence of rows).
            title: Optional title shown above the table.
            title_indent: Left indent (spaces) for title lines.
            data_indent: Left indent (spaces) for table rows.
            data_seq_len: Spaces between columns.
            title_seq: Underline character for the title.
            header_seq: Underline character for the header separator line.
            header_footer: When True, add leading/trailing blank line.
            wrap: Enable auto wrap for the widest column when table exceeds terminal width.
            wrap_col_idx: Force wrap column index; when None, use the widest column.
            wrap_min_width: Minimum width for wrapped column.
            terminal_width: Override terminal width; when None, auto-detect.
            truncate: When True, truncate rows longer than header; when False, raise.
        """
        self.title = title
        self.title_indent = title_indent
        self.data_indent = data_indent
        self.data_seq_len = data_seq_len
        self.title_seq = title_seq
        self.header_seq = header_seq
        self.header_footer = header_footer
        self.wrap = wrap
        self.wrap_col_idx = wrap_col_idx
        self.wrap_min_width = wrap_min_width
        self.terminal_width = terminal_width
        self.truncate = truncate
        self.header = copy.deepcopy(list(header))
        self.data = copy.deepcopy([list(row) for row in data])
        self._normalize_data()
        self._format_header()

    def _normalize_data(self):
        header_len = len(self.header)
        if header_len == 0 and self.data:
            header_len = max(len(row) for row in self.data)
            self.header = [""] * header_len
        for i in range(len(self.data)):
            row = list(self.data[i])
            if len(row) < header_len:
                row.extend([""] * (header_len - len(row)))
            elif len(row) > header_len:
                if self.truncate:
                    row = row[:header_len]
                else:
                    raise ValueError("Row length exceeds header length")
            self.data[i] = row

    def _format_header(self):
        for i in range(len(self.header)):
            cell = str(self.header[i])
            if cell:
                self.header[i] = cell[0:1].upper() + cell[1:]
            else:
                self.header[i] = cell

    def update(self, header: Optional[Sequence[Any]] = None,
               data: Optional[Sequence[Sequence[Any]]] = None) -> None:
        if header is not None:
            self.header = copy.deepcopy(list(header))
        if data is not None:
            self.data = copy.deepcopy([list(row) for row in data])
        self._normalize_data()
        self._format_header()

    def set_cell(self, row_idx: int, col_idx: int, value: Any) -> None:
        if row_idx < 0 or col_idx < 0:
            raise ValueError("row_idx and col_idx must be >= 0")
        if row_idx >= len(self.data):
            raise IndexError("row_idx out of range")
        if col_idx >= len(self.data[row_idx]):
            raise IndexError("col_idx out of range")
        self.data[row_idx][col_idx] = value
        self._normalize_data()

    @staticmethod
    def _display_width(value: str) -> int:
        try:
            from prompt_toolkit.utils import get_cwidth
            return get_cwidth(value)
        except Exception:
            return len(value)

    def _resolve_terminal_width(self) -> Optional[int]:
        if self.terminal_width is not None:
            return int(self.terminal_width)
        try:
            from prompt_toolkit.application.current import get_app
            app = get_app()
            if app is not None and getattr(app, "output", None) is not None:
                return app.output.get_size().columns
        except Exception:
            pass
        try:
            return shutil.get_terminal_size((120, 20)).columns
        except Exception:
            return None

    def _rows(self) -> List[List[str]]:
        rows = [list(map(str, self.header))]
        for row in self.data:
            rows.append([str(cell) for cell in row])
        return rows

    def _compute_col_widths(self, rows: List[List[str]]) -> List[int]:
        if not rows:
            return []
        col_count = len(rows[0])
        widths = [0] * col_count
        for row in rows:
            for i in range(col_count):
                widths[i] = max(widths[i], self._display_width(row[i]))
        return widths

    def _resolve_wrap(self, col_widths: List[int]) -> Optional[int]:
        if not self.wrap or not col_widths:
            return None
        term_width = self._resolve_terminal_width()
        if term_width is None:
            return None
        col_count = len(col_widths)
        sep_width = self.data_seq_len * max(0, col_count - 1)
        total_width = self.data_indent + sep_width + sum(col_widths)
        if total_width <= term_width:
            return None
        wrap_idx = self.wrap_col_idx
        if wrap_idx is None:
            wrap_idx = col_widths.index(max(col_widths))
        if wrap_idx < 0 or wrap_idx >= len(col_widths):
            return None
        other_width = sum(col_widths) - col_widths[wrap_idx]
        available = term_width - self.data_indent - sep_width - other_width
        target = max(self.wrap_min_width, available)
        if target >= col_widths[wrap_idx]:
            return None
        col_widths[wrap_idx] = target
        return wrap_idx

    def _wrap_cell(self, text: str, width: int) -> List[str]:
        if width <= 0:
            return [text]
        lines: List[str] = []
        parts = text.split("\n")
        for idx, part in enumerate(parts):
            lines.extend(self._wrap_segment(part, width))
            if idx < len(parts) - 1:
                lines.append("")
        return lines or [""]

    def _wrap_segment(self, text: str, width: int) -> List[str]:
        if text == "":
            return [""]
        lines: List[str] = []
        current = ""
        current_width = 0
        for ch in text:
            ch_width = self._display_width(ch)
            if current and current_width + ch_width > width:
                lines.append(current)
                current = ch
                current_width = ch_width
            else:
                current += ch
                current_width += ch_width
        if current or not lines:
            lines.append(current)
        return lines

    def _pad(self, text: str, width: int) -> str:
        padding = width - self._display_width(text)
        if padding <= 0:
            return text
        return text + (" " * padding)

    def print_line(self, row: Sequence[Any]) -> str:
        rows = self._rows()
        col_widths = self._compute_col_widths(rows)
        wrap_idx = self._resolve_wrap(col_widths)
        row_cells = list(map(str, row))
        if len(row_cells) < len(col_widths):
            row_cells.extend([""] * (len(col_widths) - len(row_cells)))
        elif len(row_cells) > len(col_widths):
            row_cells = row_cells[:len(col_widths)]
        return "\n".join(self._render_row(row_cells, col_widths, wrap_idx))

    def _render_row(self, row: List[str], col_widths: List[int], wrap_idx: Optional[int]) -> List[str]:
        cell_lines: List[List[str]] = []
        for i, cell in enumerate(row):
            if wrap_idx is not None and i == wrap_idx:
                cell_lines.append(self._wrap_cell(cell, col_widths[i]))
            else:
                cell_lines.append([cell])
        max_lines = max(len(lines) for lines in cell_lines) if cell_lines else 0
        rendered: List[str] = []
        for line_idx in range(max_lines):
            parts = []
            for col_idx, lines in enumerate(cell_lines):
                value = lines[line_idx] if line_idx < len(lines) else ""
                parts.append(self._pad(value, col_widths[col_idx]))
            rendered.append(" " * self.data_indent + (" " * self.data_seq_len).join(parts))
        return rendered

    def _render_header_sep(self, col_widths: List[int]) -> str:
        parts = [self.header_seq * width if width > 0 else "" for width in col_widths]
        return " " * self.data_indent + (" " * self.data_seq_len).join(parts)

    def print_data(self):
        rows = self._rows()
        col_widths = self._compute_col_widths(rows)
        wrap_idx = self._resolve_wrap(col_widths)
        lines: List[str] = []
        for row_idx, row in enumerate(rows):
            lines.extend(self._render_row(row, col_widths, wrap_idx))
            if row_idx == 0:
                lines.append(self._render_header_sep(col_widths))
        return "\n".join(lines)

    def print_table(self):
        if str(self.title) != "":
            title = self.print_title() + "\n\n"
            table_str = title + self.print_data()
        else:
            table_str = self.print_data()
        return "\n" + table_str + "\n" if self.header_footer else table_str

    def print_title(self):
        title_str = str(self.title)
        if title_str != "":
            if not title_str[0:1].isupper():
                title_str = title_str[0:1].upper() + title_str[1:].lower()
            title_line = " " * self.title_indent + title_str
            seq_line = " " * self.title_indent + self.title_seq * len(title_str)
            return "\n".join([title_line, seq_line])

    def __str__(self):
        return self.print_table()
