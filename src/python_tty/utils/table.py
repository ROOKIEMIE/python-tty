import copy


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
    def __init__(self, header: [], data: [[]], title="",
                 title_indent=0, data_indent=4, data_seq_len=4,
                 title_seq="=", header_seq="-", header_footer=True):
        self.title = title
        self.title_indent = title_indent
        self.data_indent = data_indent
        self.data_seq_len = data_seq_len
        self.title_seq = title_seq
        self.header_seq = header_seq
        self.header_footer = header_footer
        self.header = copy.deepcopy(header)
        self.data = copy.deepcopy(data)
        self._padding_data()
        self._format_header()
        self._merge_data()
        self._padding_max_width()

    def _padding_data(self):
        table_header_item_num = len(self.header)
        for i in range(len(self.data)):
            row = self.data[i]
            if len(row) < table_header_item_num:
                self.data[i].append("")
            elif len(row) > table_header_item_num:
                self.data[i] = row[:table_header_item_num]

    def _format_header(self):
        for i in range(len(self.header)):
            cell = self.header[i]
            self.header[i] = str(cell)[0:1].upper() + str(cell)[1:]

    def _merge_data(self):
        data = []
        header = []
        for cell in self.header:
            header.append(HeaderCell(cell, self.header_seq))
        data.append(header)
        for row in self.data:
            line = []
            for cell in row:
                line.append(Cell(cell))
            data.append(line)
        self.data = data

    def _padding_max_width(self):
        max_widths = [len(cell) for cell in self.header]
        for i in range(len(self.data)):
            for j in range(len(self.data[i])):
                max_width = max_widths[j]
                cell = self.data[i][j]
                if cell.data_width > max_width:
                    max_widths[j] = cell.data_width
        for i in range(len(self.data)):
            for j in range(len(self.data[i])):
                max_width = max_widths[j]
                cell = self.data[i][j]
                if cell.data_width < max_width:
                    cell.update_max_width(max_width - cell.data_width)

    def print_row(self, row: []):
        cells = []
        seqs = []
        for cell in row:
            if isinstance(cell, HeaderCell):
                seqs.append(cell.get_seq_str())
            cells.append(str(cell))
        if len(seqs) > 0:
            return " "*self.data_indent + (" " * self.data_seq_len).join(cells),\
                " "*self.data_indent + (" " * self.data_seq_len).join(seqs)
        else:
            return " "*self.data_indent + (" " * self.data_seq_len).join(cells), None

    def print_data(self):
        lines = []
        for row in self.data:
            line, seq = self.print_row(row)
            lines.append(line)
            if seq is not None:
                lines.append(seq)
        return "\n".join(lines)

    def print_title(self):
        title_str = str(self.title)
        if title_str != "":
            if not title_str[0:1].isupper():
                title_str = title_str[0:1].upper() + title_str[1:].lower()
            title_line = " "*self.title_indent + title_str
            seq_line = " "*self.title_indent + self.title_seq*len(self.title)
            return "\n".join([title_line, seq_line])

    def __str__(self):
        if str(self.title) != "":
            title = self.print_title() + "\n\n"
            table_str = title + self.print_data()
        else:
            table_str = self.print_data()
        return "\n" + table_str + "\n" if self.header_footer else table_str
